"""
上下文形态对比实验（S55）：1M 窗口下，上下文"脏/净/分离"对写作质量的影响。

背景（主人假设）：长上下文（尤其含大量工具调用噪声）→ 注意力稀疏 → 幻觉。
实验验证：同样 1M 窗口下，
  A 现状全量（含工具噪声）
  B 干净视图（过滤工具噪声：对话+注入+最近章+意图）
  C 完全分离（主循环概括意图 → 独立写作调用）
哪个写作质量更好、幻觉更少。

成本控制：全用 flash（1 元/百万输入）；素材用"工具噪声模板 + 真实章节"构造
代表性脏上下文（非真 40 万字，控成本）；每组 2 次生成；判分用 flash。

用法：uv run python -m benchmarks.context_compare.run
产物：benchmarks/context_compare/out/（各生成 + 判分 JSON）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from benchmarks.compare.baseline import BareLLM

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "out"

# 素材：哈利波特前 3 章（连贯基线）+ 第 4 章开头（gold 对照）
HP3 = (ROOT / "benchmarks" / "writing" / "hp" / "first3.txt").read_text(encoding="utf-8")
HP4_GOLD = (ROOT / "benchmarks" / "assets" / "hp_philosophers_stone.txt").read_text(
    encoding="utf-8"
)


# 工具噪声模板（模拟 Agent 循环里堆积的过程信息——真实链路常见形态）
def _tool_noise(n: int) -> str:
    lines = []
    for i in range(n):
        lines.append(
            f"[工具调用 {i + 1}] graph_query(query='哈利波特'):\n"
            "  实体：哈利·波特（角色，孤儿，住在女贞路）/ 霍格沃茨（地点，魔法学校）\n"
            "  关系：哈利 —姨父家→ 德思礼一家\n"
            f"[工具调用 {i + 1}b] read_chapter(title='第{i % 3 + 1}章'):\n"
            "  （章节全文内容摘要……此处为过程信息，与当前写作任务无关）\n"
        )
    return "\n".join(lines)


# 图谱注入（正常链路会注入的"已固化事实"）
GRAPH_FACTS = """# 已固化事实（知识图谱）
- 哈利·波特（角色）：孤儿，额头有闪电形伤疤，住在德思礼家，11 岁收到霍格沃茨入学信
- 霍格沃茨（地点）：魔法学校，9¾ 站台，对角巷，分院帽
- 海格（角色）：霍格沃茨猎场看守，高大，替邓布利多送信
- 邓布利多（角色）：霍格沃茨校长
- 麦格教授（角色）：变形课教授"""

# 文笔 skill（干净视图会注入的叙事技巧）
WRITING_SKILLS = """# 叙事技巧（内容）
【镜头感与视角】把叙事当作镜头：情绪爆点给近景特写，场景转换给远景氛围。
【对白机锋】对白不直给信息，每句话负载潜台词与立场。
【节奏控制】紧张处短句，舒缓处长句，整章有起伏。"""

SYSTEM_BASE = (
    "你是小说写作智能体。你要直接写故事正文，具体、有画面感，杜绝空泛总结。"
    "只输出正文本身，不要解释、不要工具调用、不要标注。"
)

# 写作意图 + 当前进度定位（v2 起：三组都带，避免设计坑）
INTENT = "第 4 章开头：哈利已经 11 岁，即将得知自己身世。海格从礁石小屋救出哈利，带他离开，告诉他巫师身份，准备送他入学信。"
PROGRESS_NOTE = "【当前进度】已写完第 3 章（哈利在礁石小屋）。现在续写**第 4 章开头**（哈利 11 岁，不是婴儿时期）。"


# ---------------------------------------------------------------------------
# 三组上下文构造
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# v3：信息量对等——B 用「素材（含工具查询结果）+ 剔噪声（无调用记录）」
# 主人划分：工具查询结果=素材（保留），工具调用记录本身=噪声（剔）
# ---------------------------------------------------------------------------
def _tool_results_as_material(n: int) -> str:
    """素材：工具查询结果内容（保留——写作可参考的设定/事实）。"""
    lines = []
    for i in range(n):
        lines.append(
            "[工具 graph_query 成功] 实体：哈利·波特（角色，孤儿，住在女贞路，11 岁）/ "
            "海格（角色，猎场看守）/ 霍格沃茨（地点，魔法学校，9¾站台）/ "
            "邓布利多（校长）/ 麦格教授（变形课教授）\n"
            "[工具 read_chapter 成功] 第3章结尾：海格在暴雨中破门，告诉哈利他是巫师，"
            "约定送他去霍格沃茨。\n"
        )
    return "\n".join(lines)


def build_Bv3_clean() -> str:
    """B 精选视图：系统 + 图谱 + 工具结果素材 + 前3章全文 + 进度 + 意图（无调用记录噪声）。"""
    return (
        f"{SYSTEM_BASE}\n\n{GRAPH_FACTS}\n\n"
        f"（工具查询结果素材）\n{_tool_results_as_material(3)}\n\n"
        f"【已写章节（前 3 章全文）】\n{HP3[:8000]}\n\n"
        f"{PROGRESS_NOTE}\n\n【写作意图】{INTENT}\n\n"
        f"【任务】续写第 4 章开头 500 字左右。"
    )


def main_v3(repeats: int = 3) -> None:
    """v3：A(全量含记录噪声) vs Bv3(同素材剔记录噪声) vs C(分离)。"""
    OUT.mkdir(parents=True, exist_ok=True)
    llm = BareLLM(temperature=0.7, max_tokens=2048)
    agg: dict[str, list[dict[str, object]]] = {}
    for rep in range(repeats):
        print(f"\n=== v3 第 {rep + 1} 轮 ===")
        a_text = llm.chat(SYSTEM_BASE, build_A_noise())
        (OUT / f"v3_A_{rep + 1}.md").write_text(a_text, encoding="utf-8")
        agg.setdefault("A_full", []).append(judge(llm, a_text, HP3[-1500:], GRAPH_FACTS))
        print(f"A 完成（rep {rep + 1}）")
        b_text = llm.chat(SYSTEM_BASE, build_Bv3_clean())
        (OUT / f"v3_B_{rep + 1}.md").write_text(b_text, encoding="utf-8")
        agg.setdefault("B_clean", []).append(judge(llm, b_text, HP3[-1500:], GRAPH_FACTS))
        print(f"B 完成（rep {rep + 1}）")
        plan_prompt, write_prompt = build_C_separated()
        intent = llm.chat("你是小说主循环规划器。", plan_prompt)
        c_prompt = write_prompt.replace("（此处填充主循环产出）", intent)
        c_text = llm.chat(SYSTEM_BASE, c_prompt)
        (OUT / f"v3_C_{rep + 1}.md").write_text(c_text, encoding="utf-8")
        agg.setdefault("C_separated", []).append(judge(llm, c_text, HP3[-1500:], GRAPH_FACTS))
        print(f"C 完成（rep {rep + 1}）")
    summary: dict[str, object] = {}
    for k, judges in agg.items():
        coh = [float(j.get("coherence", 0) or 0) for j in judges]
        pro = [float(j.get("prose", 0) or 0) for j in judges]
        foc = [float(j.get("focus", 0) or 0) for j in judges]
        hall = [j.get("hallucination") or "" for j in judges]
        pos = [j.get("position") or "" for j in judges]
        summary[k] = {
            "repeats": len(judges),
            "avg_coherence": round(sum(coh) / len(coh), 1),
            "avg_prose": round(sum(pro) / len(pro), 1),
            "avg_focus": round(sum(foc) / len(foc), 1),
            "hallucination": [h for h in hall if h],
            "position_errors": [p for p in pos if p],
        }
    print("\n=== v3 汇总（均值）===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / "summary_v3.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 三组上下文构造（v2：三组都带进度定位 + 写作意图，只差上下文形态）
# ---------------------------------------------------------------------------
def build_A_noise() -> str:
    """A 现状全量：系统 + 图谱 + 工具噪声堆叠 + 前 3 章全文 + 进度 + 意图 + 任务。"""
    return (
        f"{SYSTEM_BASE}\n\n{GRAPH_FACTS}\n\n"
        f"（对话历史中的工具调用记录）\n{_tool_noise(20)}\n\n"
        f"【已写章节（前 3 章全文）】\n{HP3[:8000]}\n\n"
        f"{PROGRESS_NOTE}\n\n【写作意图】{INTENT}\n\n"
        f"【任务】续写第 4 章开头 500 字左右。"
    )


def build_B_clean() -> str:
    """B 干净视图：系统 + 图谱 + 最近章结尾 + 文笔 skill + 进度 + 意图 + 任务。"""
    return (
        f"{SYSTEM_BASE}\n\n{GRAPH_FACTS}\n\n{WRITING_SKILLS}\n\n"
        f"{PROGRESS_NOTE}\n【写作意图】{INTENT}\n"
        f"【最近章节结尾】\n{HP3[-1500:]}\n\n"
        f"【任务】续写第 4 章开头 500 字左右。"
    )


def build_C_separated() -> tuple[str, str]:
    """C 完全分离：主循环先概括意图（步骤1），写作调用只收意图+最近章+skill（步骤2）。

    返回 (主循环 prompt, 写作调用 prompt)。"""
    plan_prompt = (
        "你是小说主循环规划器。基于前 3 章内容，为第 4 章开头产出**写作意图**"
        "（3-5 句：场景、人物状态、氛围、要推进的情节）。不要写正文。\n\n"
        f"{PROGRESS_NOTE}\n【前 3 章】\n{HP3[:6000]}\n\n【图谱】\n{GRAPH_FACTS}"
    )
    write_prompt = (
        f"{SYSTEM_BASE}\n\n{WRITING_SKILLS}\n\n"
        f"{PROGRESS_NOTE}\n"
        "【写作意图】（由主循环规划提供）\n"
        "（此处填充主循环产出）\n"
        f"【最近章节结尾】\n{HP3[-1500:]}\n\n"
        "【任务】严格按意图续写第 4 章开头 500 字左右。"
    )
    return plan_prompt, write_prompt


# ---------------------------------------------------------------------------
# 判分（LLM 裁判）
# ---------------------------------------------------------------------------
JUDGE_SYSTEM = (
    "你是小说质量审查员。下面给出【设定清单】【上一章结尾】【待审文本】。\n"
    "评估四项并输出严格 JSON：\n"
    '{"position": "时间点/场景定位是否正确（待审文本应写哈利 11 岁、在礁石小屋/女贞路被海格接走，'
    '"绝不是婴儿时期夜放德思礼家门口——若写错时间点如实指出）", '
    '"hallucination": "是否出现与设定/前文矛盾的新事实（有则写具体矛盾，无则空串）", '
    '"coherence": 1-5（与上一章结尾的衔接自然度）, '
    '"prose": 1-5（文笔：具体性/画面感/节奏，形容词滥用扣分）, '
    '"focus": 1-5（是否紧扣任务与写作意图，有无跑题/泛化）}\n'
)


def judge(llm: BareLLM, text: str, prev: str, facts: str) -> dict[str, object]:
    user = (
        f"【设定清单】\n{facts[:1500]}\n\n【上一章结尾】\n{prev[-800:]}\n\n"
        f"【待审文本】\n{text[:4000]}"
    )
    out = llm.chat(JUDGE_SYSTEM, user)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return {"raw": out}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"raw": out}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    llm = BareLLM(temperature=0.7, max_tokens=2048)
    results: dict[str, object] = {}

    # --- A 现状全量 ---
    a_prompt = build_A_noise()
    a_text = llm.chat(SYSTEM_BASE, a_prompt)
    (OUT / "A_full.md").write_text(a_text, encoding="utf-8")
    results["A_full"] = {
        "input_tokens": llm.tokens_of(a_prompt),
        "judge": judge(llm, a_text, HP3[-1500:], GRAPH_FACTS),
    }
    print(f"A 完成（输入 {results['A_full']['input_tokens']} token）")

    # --- B 干净视图 ---
    b_prompt = build_B_clean()
    b_text = llm.chat(SYSTEM_BASE, b_prompt)
    (OUT / "B_clean.md").write_text(b_text, encoding="utf-8")
    results["B_clean"] = {
        "input_tokens": llm.tokens_of(b_prompt),
        "judge": judge(llm, b_text, HP3[-1500:], GRAPH_FACTS),
    }
    print(f"B 完成（输入 {results['B_clean']['input_tokens']} token）")

    # --- C 完全分离 ---
    plan_prompt, write_prompt = build_C_separated()
    intent = llm.chat("你是小说主循环规划器。", plan_prompt)  # 主循环概括
    c_prompt = write_prompt.replace("（此处填充主循环产出）", intent)
    c_text = llm.chat(SYSTEM_BASE, c_prompt)
    (OUT / "C_separated.md").write_text(c_text, encoding="utf-8")
    (OUT / "C_intent.md").write_text(intent, encoding="utf-8")
    results["C_separated"] = {
        "input_tokens_plan": llm.tokens_of(plan_prompt),
        "input_tokens_write": llm.tokens_of(c_prompt),
        "intent": intent,
        "judge": judge(llm, c_text, HP3[-1500:], GRAPH_FACTS),
    }
    print(
        f"C 完成（plan {results['C_separated']['input_tokens_plan']} + "
        f"write {results['C_separated']['input_tokens_write']} token）"
    )

    (OUT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== 结果 ===")
    for k, v in results.items():
        j = v.get("judge", {})
        print(
            f"{k}: 输入{v.get('input_tokens')} token | 幻觉={j.get('hallucination') or '无'} "
            f"| 连贯={j.get('coherence')} 文笔={j.get('prose')} 聚焦={j.get('focus')}"
        )


if __name__ == "__main__":
    main()


def main_multi(repeats: int = 3) -> None:
    """多轮重复版：A/B/C 各 repeats 次，取均值（控成本：flash）。"""
    OUT.mkdir(parents=True, exist_ok=True)
    llm = BareLLM(temperature=0.7, max_tokens=2048)
    agg: dict[str, dict[str, object]] = {}
    for rep in range(repeats):
        print(f"\n=== 第 {rep + 1} 轮 ===")
        # A
        a_text = llm.chat(SYSTEM_BASE, build_A_noise())
        (OUT / f"A_full_{rep + 1}.md").write_text(a_text, encoding="utf-8")
        agg.setdefault("A_full", []).append(judge(llm, a_text, HP3[-1500:], GRAPH_FACTS))  # type: ignore[arg-type]
        print(f"A 完成（rep {rep + 1}）")
        # B
        b_text = llm.chat(SYSTEM_BASE, build_B_clean())
        (OUT / f"B_clean_{rep + 1}.md").write_text(b_text, encoding="utf-8")
        agg.setdefault("B_clean", []).append(judge(llm, b_text, HP3[-1500:], GRAPH_FACTS))  # type: ignore[arg-type]
        print(f"B 完成（rep {rep + 1}）")
        # C
        plan_prompt, write_prompt = build_C_separated()
        intent = llm.chat("你是小说主循环规划器。", plan_prompt)
        c_prompt = write_prompt.replace("（此处填充主循环产出）", intent)
        c_text = llm.chat(SYSTEM_BASE, c_prompt)
        (OUT / f"C_separated_{rep + 1}.md").write_text(c_text, encoding="utf-8")
        (OUT / f"C_intent_{rep + 1}.md").write_text(intent, encoding="utf-8")
        agg.setdefault("C_separated", []).append(judge(llm, c_text, HP3[-1500:], GRAPH_FACTS))  # type: ignore[arg-type]
        print(f"C 完成（rep {rep + 1}）")
    # 汇总均值
    summary: dict[str, object] = {}
    for k, judges in agg.items():
        coh = [float(j.get("coherence", 0) or 0) for j in judges]  # type: ignore[union-attr]
        pro = [float(j.get("prose", 0) or 0) for j in judges]  # type: ignore[union-attr]
        foc = [float(j.get("focus", 0) or 0) for j in judges]  # type: ignore[union-attr]
        hall = sum(1 for j in judges if j.get("hallucination"))  # type: ignore[union-attr]
        summary[k] = {
            "repeats": len(judges),
            "avg_coherence": round(sum(coh) / len(coh), 1),
            "avg_prose": round(sum(pro) / len(pro), 1),
            "avg_focus": round(sum(foc) / len(foc), 1),
            "hallucination_count": hall,
        }
    print("\n=== 汇总（均值）===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
