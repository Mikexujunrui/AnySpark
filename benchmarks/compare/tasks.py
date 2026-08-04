"""
compare.tasks — 三个长程对比任务（同一任务 × AnySpark vs 裸 LLM）。

公平性：
- 两个系统拿到相同的种子/设定/偏好输入（用户输入变量被控制）
- 任务都是长程（多章/多轮）——AnySpark 的卖点是"长期协作不翻车"
- 单次生成不占优的事实被承认：本对比聚焦一致性/遵守/成本，不测"第一句多惊艳"
"""

from __future__ import annotations

from pathlib import Path

from benchmarks.compare.baseline import BareLLM
from benchmarks.compare.score import (
    count_dashes,
    judge_name_drifts,
    judge_setting_violations,
)
from benchmarks.unit.core import ApiClient

GOLD = Path(__file__).resolve().parent.parent / "unit" / "gold"

# 任务 A：哈利波特前三章设定清单（从 gold 摘要拼出，双方同输入）
HP_SETTINGS = (
    "哈利·波特是男婴/男孩，父母莉莉和詹姆被伏地魔杀害，他额头有闪电形伤疤。"
    "他寄养在姨妈佩妮·德思礼家（女贞路4号），住在楼梯下的碗柜里。"
    "佩妮是莉莉的姐姐；弗农·德思礼是姨父；达力·德思礼是表哥（不是兄弟）。"
    "邓布利多是白发老教授；海格是巨人；麦格教授会变猫。"
    "伏地魔（神秘人）杀哈利失败后失踪。哈利收到霍格沃茨魔法学校的信。"
)

# 任务 B：原创种子（双方同输入，连写 3 章）
SEED_B = "一个信号维修工在废弃灯塔里发现一本记录未来天气的日记，日记里有一页写着他的死期。"

# 任务 C：偏好
PREFERENCE_C = "叙事中禁止使用破折号（——）"


# ---------------------------------------------------------------------------
# 任务 A：设定忠实度（写第 4 章，核对 6 条 gold 设定违规）
# ---------------------------------------------------------------------------
def run_task_a(api: ApiClient, bare: BareLLM, judge: BareLLM) -> dict:
    prompt = f"基于以下设定续写第 4 章（约 400 字），不得违反任何设定：\n{HP_SETTINGS}\n第 4 章："
    # 裸 LLM：单次输出
    bare_text = bare.chat("你是小说续写者。严格遵循设定。", prompt)
    # AnySpark：走 /api/chat 写章节（系统会自动图谱/说明书注入）
    any_text = _anyspark_write(api, "第四章 续写", "你是小说续写者。严格遵循我给出的设定，续写第 4 章约 400 字，用 write_chapter 保存。设定如下：" + HP_SETTINGS)
    return {
        "bare": {
            "text": bare_text,
            "violations": judge_setting_violations(judge, HP_SETTINGS, bare_text),
            "tokens": bare.tokens_of(bare_text),
        },
        "anyspark": {
            "text": any_text,
            "violations": judge_setting_violations(judge, HP_SETTINGS, any_text),
            "tokens": bare.tokens_of(any_text),
        },
    }


# ---------------------------------------------------------------------------
# 任务 B：长书一致性（原创种子连写 5 章——上下文遗忘在长程中发生）
# ---------------------------------------------------------------------------
def run_task_b(api: ApiClient, bare: BareLLM, judge: BareLLM) -> dict:
    n = 5
    # 裸 LLM：分 n 次写，每次把前文拼入 user 消息（模拟裸 LLM 的上下文用法）
    bare_ctx = ""
    bare_chapters: list[str] = []
    for i in range(n):
        history = f"\n\n已写章节：\n{bare_ctx}" if bare_ctx else ""
        chapter = bare.chat(
            "你是小说写作者。保持角色名、地名、时间线连贯一致。",
            f"写第{i+1}章（约250字）。种子：{SEED_B}{history}\n第{i+1}章：",
        )
        bare_chapters.append(chapter)
        bare_ctx += f"\n【第{i+1}章】\n{chapter}"

    # AnySpark：n 次 /api/chat 写章节（图谱自动抽取+注入；评分用落盘正文）
    any_chapters: list[str] = []
    for i in range(n):
        title = f"对比B-第{i+1}章"
        _anyspark_write(
            api,
            title,
            f"请写第{i+1}章（约250字），基于种子：{SEED_B}。前文要连贯，保持角色和地名一致。",
        )
        chs = api.get("/api/chapters")
        body = ""
        if isinstance(chs, list):
            for c in chs:
                if c.get("title") == title:
                    body = str(c.get("content", ""))
        any_chapters.append(body)

    def _join(chs: list[str]) -> str:
        return "\n".join(chs)

    bare_drifts = judge_name_drifts(judge, bare_chapters[0], bare_chapters[2])
    any_drifts = judge_name_drifts(judge, any_chapters[0], any_chapters[2])
    return {
        "bare": {
            "chapters": bare_chapters,
            "drifts": bare_drifts,
            "tokens": bare.tokens_of(_join(bare_chapters)),
        },
        "anyspark": {
            "chapters": any_chapters,
            "drifts": any_drifts,
            "tokens": bare.tokens_of(_join(any_chapters)),
        },
    }


# ---------------------------------------------------------------------------
# 任务 C：偏好跨轮记忆（第 1 章用户说偏好；第 2 章不再重复——测系统是否记住）
# ---------------------------------------------------------------------------
def run_task_c(api: ApiClient, bare: BareLLM, judge: BareLLM) -> dict:
    # 裸 LLM：第 1 章 prompt 说偏好；第 2 章不再说（裸 LLM 无记忆，会忘）
    ch1_bare = bare.chat(
        f"你是小说写作者。{PREFERENCE_C}",
        f"写第1章（约250字）。种子：{SEED_B}\n第1章：",
    )
    ch2_bare = bare.chat(
        "你是小说写作者。",
        f"写第2章（约250字），延续第1章。\n第1章：\n{ch1_bare}\n第2章：",
    )
    bare_text = ch1_bare + ch2_bare

    # AnySpark：说明书记录偏好（=用户确认过的长期偏好）；第 2 章不再重复
    api.post("/api/manual", {"content": PREFERENCE_C, "scope": "project", "confidence": 1.0})
    ch1 = _anyspark_write(api, "对比C-第1章", f"请写第1章（约250字），基于种子：{SEED_B}。{PREFERENCE_C}")
    ch2 = _anyspark_write(api, "对比C-第2章", f"请写第2章（约250字），基于种子：{SEED_B}。延续第1章。")
    any_text = ch1 + ch2
    return {
        "bare": {"text": bare_text, "dash_count": count_dashes(bare_text), "tokens": bare.tokens_of(bare_text), "dash_ch1": count_dashes(ch1_bare), "dash_ch2": count_dashes(ch2_bare)},
        "anyspark": {"text": any_text, "dash_count": count_dashes(any_text), "tokens": bare.tokens_of(any_text), "dash_ch1": count_dashes(ch1), "dash_ch2": count_dashes(ch2)},
    }


# ---------------------------------------------------------------------------
# AnySpark 侧公共：让 AI 用 write_chapter 落盘，评分用落盘正文（非 AI 回复）
# ---------------------------------------------------------------------------
def _anyspark_write(api: ApiClient, title: str, instruction: str) -> str:
    last_text = ""
    for _attempt in range(2):
        resp = api.post(
            "/api/chat",
            {
                "message": f"{instruction} 请用 write_chapter 保存为《{title}》。",
                "skip_inject": ["manual", "bias", "mood"],
            },
        )
        last_text = str(resp.get("text", ""))
        # 评分用落盘的章节正文（title 模糊匹配容忍 AI 的变体命名）
        chs = api.get("/api/chapters")
        if isinstance(chs, list):
            for c in chs:
                t = str(c.get("title", ""))
                if t == title or t in title or title in t or title[:4] in t:
                    body = str(c.get("content", ""))
                    if body:
                        return body
    # 后备：AI 直接输出正文而没落盘时，用其回复（真实产出）
    if len(last_text) > 50:
        return last_text
    return ""
