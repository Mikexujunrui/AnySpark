"""
多章毒化对比实验（S58）：同一会话连续写 3 章——A 累积历史 vs C 每章干净写作。

背景（主人核心体感）：同会话多次写作累积毒化——第 1 章统一，后面章节开始矛盾、
前面要求失效。v3 证明单次 A/B/C 接近；本实验验证**跨轮次**毒化是否出现，
以及 C（每章干净写作调用）是否免疫。

设计：
- 前文：哈利波特第 1-3 章（真实素材，连贯基线）
- 任务：连续写第 4/5/6 章开头（各 ~400 字）
- A 累积：第 N 章上下文 = 前 N-1 章全文 + 工具噪声堆叠 + 任务（模拟同会话累积）
- C 干净：每章只给 意图 + 最近章结尾（干净写作调用，不背历史）

判分：每章 LLM 裁判（连贯/文笔/聚焦/幻觉/定位）。看跨章趋势：
A 若第 4→5→6 章连贯/聚焦下滑、幻觉上升 = 毒化出现；C 稳定 = 干净写作免疫。

成本：flash，6 次生成 + 6 次判分 ≈ 2 元。

用法：uv run python -m benchmarks.context_compare.multi_chapter
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from benchmarks.compare.baseline import BareLLM

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "out" / "multi_chapter"

HP3 = (ROOT / "benchmarks" / "writing" / "hp" / "first3.txt").read_text(encoding="utf-8")

# 三章的写作意图（gold 剧情方向）
INTENTS = [
    "第4章 钥匙保管员：海格带哈利去对角巷，首次见到巫师世界——破釜酒吧、对角巷、古灵阁取钱、魔杖店（奥利凡德）。",
    "第5章 对角巷之后：哈利回到德思礼家，开学前等待——猫头鹰海德薇送来霍格沃茨来信，姨父藏信、追信到礁石小屋，海格再次出现。",
    "第6章 从9¾站台出发：哈利在国王十字车站找不到站台，海格提醒穿墙而过，登上霍格沃茨特快，火车上遇见罗恩·韦斯莱。",
]

SYSTEM = (
    "你是小说写作智能体。严格根据意图与上下文撰写正文，具体、有画面感、杜绝空泛总结。"
    "只输出正文本身，不要解释、不要工具调用、不要标注。"
)

# 工具噪声模板（模拟同会话累积的工具调用记录）
def _noise(n: int) -> str:
    lines = []
    for i in range(n):
        lines.append(
            f"[工具调用 {i + 1}] graph_query(query='哈利波特'):\n"
            "  实体：哈利·波特（角色）/ 霍格沃茨（地点）/ 海格（角色）\n"
            f"[工具调用 {i + 1}b] read_chapter(title='第{i % 3 + 1}章'):\n"
            "  （章节内容……过程信息）\n"
        )
    return "\n".join(lines)


JUDGE = (
    "你是小说质量审查员。下面给出【上一章结尾】【待审文本】【章节定位】。\n"
    "评估四项并输出严格 JSON：\n"
    '{"hallucination": "与设定/前文矛盾的新事实（有则写具体，无则空串）", '
    '"coherence": 1-5（与上一章结尾衔接自然度）, '
    '"prose": 1-5（文笔）, '
    '"focus": 1-5（是否紧扣本章意图、有无跑题）}\n'
)


def judge(llm: BareLLM, text: str, prev: str, intent: str) -> dict[str, object]:
    user = (
        f"【章节定位】\n{intent[:200]}\n\n【上一章结尾】\n{prev[-600:]}\n\n"
        f"【待审文本】\n{text[:3000]}"
    )
    out = _chat_retry(llm, JUDGE, user)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return {"raw": out}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"raw": out}


def _chat_retry(llm: BareLLM, system: str, user: str, tries: int = 3) -> str:
    """chat 带空返回重试（flash 偶发空响应，重试兜底）。"""
    for attempt in range(tries):
        text = llm.chat(system, user)
        if text.strip():
            return text
        print(f"  （空响应，重试 {attempt + 1}/{tries}）")
    return text


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    llm = BareLLM(temperature=0.7, max_tokens=2048)
    results: dict[str, object] = {}

    # ---------- A 累积：同会话连续写 3 章 ----------
    print("=== A 累积模式（同会话，历史累积）===")
    a_chapters: list[str] = []
    a_judges: list[dict[str, object]] = []
    for i, intent in enumerate(INTENTS):
        prev_text = "\n\n".join(a_chapters) if a_chapters else HP3[:8000]
        prompt = (
            f"{SYSTEM}\n\n（历史工具调用记录）\n{_noise(10)}\n\n"
            f"【已写章节（前文累积）】\n{prev_text[-9000:]}\n\n"
            f"【本章意图】{intent}\n\n【任务】写本章开头 400 字左右。"
        )
        text = _chat_retry(llm, SYSTEM, prompt)
        a_chapters.append(text)
        (OUT / f"A_ch{i + 1}.md").write_text(text, encoding="utf-8")
        prev_anchor = a_chapters[-2] if len(a_chapters) > 1 else HP3[-1500:]
        j = judge(llm, text, prev_anchor, intent)
        a_judges.append(j)
        print(f"  第{i + 1}章完成（judge={j}）")
    results["A_cumulative"] = a_judges

    # ---------- C 干净：每章独立写作调用 ----------
    print("=== C 干净模式（每章独立干净写作）===")
    c_chapters: list[str] = []
    c_judges: list[dict[str, object]] = []
    for i, intent in enumerate(INTENTS):
        prev_anchor = c_chapters[-1] if c_chapters else HP3[-1500:]
        prompt = (
            f"{SYSTEM}\n\n【本章意图】{intent}\n"
            f"【最近章节结尾】\n{prev_anchor}\n\n【任务】写本章开头 400 字左右。"
        )
        text = _chat_retry(llm, SYSTEM, prompt)
        c_chapters.append(text)
        (OUT / f"C_ch{i + 1}.md").write_text(text, encoding="utf-8")
        j = judge(llm, text, prev_anchor, intent)
        c_judges.append(j)
        print(f"  第{i + 1}章完成（judge={j}）")
    results["C_clean"] = c_judges

    (OUT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== 汇总 ===")
    for mode, judges in results.items():
        print(f"\n{mode}:")
        for i, j in enumerate(judges):
            print(
                f"  第{i + 1}章: 连贯={j.get('coherence')} 文笔={j.get('prose')} "
                f"聚焦={j.get('focus')} 幻觉={j.get('hallucination') or '无'}"
            )


if __name__ == "__main__":
    run()
