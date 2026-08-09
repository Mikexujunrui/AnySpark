"""
anyspark.align.skillgen — 叙事技巧生成器（S54：文风提炼 → skill 候选）。

主人设计（DESIGN §12.17 延续 + 实测经验）：
- 场景：作者喜欢某篇小说的文风 → 导入原文（斗破苍穹等）→ 提炼成可执行的
  叙事技巧 skill（name/description/content/example/tags 五段式）
- 坑（主人实测）：LLM 生成 skill 时天然倾向**描述性语言**（"文风大气磅礴"
  "节奏明快"）——这类抽象评价对模型写作零指导价值（怎么写出"大气磅礴"？
  模型不知道）。
- 对策（主人拍板）：**最好用的是 ① 负面性 ② 直接案例**：
  - 负面约束："不要铺垫环境再推进"（负面清单最好执行）
  - 直接案例：必须**摘录自输入原文**（真实文本），不是 LLM 编造
- prompt 里硬性禁止抽象描述（"文风XX""描写细腻"类词），强制可执行形式

机制硬编码（提炼流程/输出 schema/解析），内容自然语言（技法文本/案例）。
"""

from __future__ import annotations

import json
import re

from anyspark.core import Message

# 提炼提示（S54b：引导而非禁止——不强制负面，不硬禁抽象；强调可执行性）
# S67b：借鉴 creative-writing-skills（haowjy）——①维度扩充（8 类，先识别不硬凑）
# ②复现测试（tic vs 风格）③简洁自检（Brevity test）④LLM 默认腔负面参照（找差异点）
GENERATE_PROMPT = """你是小说文风提炼器。给定一部小说的正文片段，提炼出**可执行**的写作技法（skill）。

【什么对写作最有指导价值】
- 对写作者（和写作模型）来说，最能直接照着做的是：
  ① 负面约束：「不要XXX」（明确禁止什么写法，比如不要铺垫环境再推进）
  ② 直接案例：摘录原文的一句话/一个片段 + 一句"为什么这样写有效"
- 概括性认知（如"文风简洁直接"）可以作为背景理解，但如果只有这种抽象概括，
  写作者仍然不知道具体怎么做——所以每条技法都要尽量落到可执行的层面。

【先识别维度，不硬凑】
- 先看这段文本里**哪些维度真正独立变化、有辨识度**，再从下面 8 类里选对应维度提炼，
  不必凑满——某维度在这段文本里没有特点就不要硬造技法：
  1. 句式/节奏：短句还是长句、铺陈还是直给、句间关系、重复/排比的使用
  2. 用词：口语还是书面、形容词密度、动词选择、意象/比喻的习惯
  3. 对白：直给信息还是潜台词、人物说话方式、对白与内心/动作的穿插
  4. 描写取舍：环境/动作/心理各占多少、详略、何时省略
  5. 内心独白深度：直接想法/间接想法/意识流的启用时机与密度
  6. 情感表达方式：情绪是身体化（痛觉/动作/感官）还是直接命名（"他很愤怒"）
  7. 感官细节：偏爱哪个感官通道（视觉/听觉/触觉/嗅觉）、细节密度
  8. 信息投放：新信息是直接交代还是透过主角的感知/反应间接流露

【复现测试（tic vs 风格）】
- 每条技法提炼前问自己：**原作者会不会想让我复现它？**
- 会 → 提炼成技法（这是风格）；不会（无意识的毛病/口癖/笔误）→ 不要提炼。

【案例要求】
- example 尽量逐字摘录自给定正文（真实原文）——真实样例比抽象描述有用得多；
  若确实找不到合适摘录，可以用"类似："自拟一句示范。

【简洁自检】
- 每条技法应能**一次读完就内化**：需要边写边查的过度规定是失败的；
  控制 content 在 2-3 句，去掉形容词堆砌，只留可操作的动作。

【LLM 默认腔反面参照】
- 多数 AI 写作有固定默认腔（信息倾倒式交代、情绪直接命名、句式平稳无变化、
  把话说满不留白、每一处都解释到位）。**原文里避开这些默认腔的地方，
  恰恰是最该提炼的差异化技法**——提炼时优先抓这些差异点。

【输出格式】（严格 JSON 数组，不要其它文字）：
[{"name": "技法名（具体可执行，如'短句直给式推进'）", "description": "一句话索引", "content": "技法说明（负面约束/正面做法，尽量落到句式/用词/节奏），2-3 句", "example": "原文摘录或自拟示范 + 一句为何有效", "tags": "适用场景，逗号分隔，如'打斗,高潮'", "target": "writing或main（写作层技法用writing；章节结构/类型组织指导用main；两者都影响用both）"}]

给定正文：
"""

# 主循环视角的类型/结构指导生成提示（S58：target=main 的类型 skill）
# 用途：给主循环看的叙事组织指导——不是句子技法（那是写作调用看的），
# 而是结构/类型/节奏/组织层面的决策指导。
GENERATE_PROMPT_MAIN = """你是小说结构分析器。给定一部小说的正文片段，提炼出**给主循环看的叙事组织指导**（skill）。

【什么对规划最有指导价值】
- 这是给"写作主循环"（负责决策：这本/这章怎么组织、何时推进、何时探索）看的，
  不是给"写句子"看的。所以提炼的是**结构/类型/节奏/组织**层面的决策指导：
  ① 类型惯例：「这类小说通常如何组织」（如"爽文：先压制再爆发，每3-5章一个小高潮"）
  ② 节奏节拍：「本片段体现的节拍结构」（如"铺垫→冲突→余波，情绪起伏点在哪"）
  ③ 组织规则：「主循环规划时该遵守什么」（如"开篇先立金手指再展开主线"）
  ④ 探索信号：「何时该跳出模板探索」（如"当读者熟悉该套路时，用反套路制造新意"）
- 不要提炼句子/用词技法（那是写作调用的事）——聚焦"怎么写这一段的结构"。

【案例要求】
- example 尽量引用给定正文的实际结构（如"第X段先压制，第Y段爆发"），或自拟结构示范。

【输出格式】（严格 JSON 数组，不要其它文字）：
[{"name": "指导名（如'爽文先压制再爆发'）", "description": "一句话索引", "content": "结构/类型/节奏/组织的可执行指导，2-3 句", "example": "原文结构示例或自拟示范 + 一句为何有效", "tags": "适用场景，逗号分隔，如'爽文,节奏'", "target": "main（主循环指导）"}]

给定正文：
"""


def _parse_skills(raw: str) -> list[dict[str, str]]:
    """宽容解析模型输出的 skill JSON 数组（去围栏/取数组/过滤空）。"""
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, str]] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "")).strip()
        content = str(d.get("content", "")).strip()
        if not name or not content:
            continue
        out.append(
            {
                "name": name,
                "description": str(d.get("description", "")).strip(),
                "content": content,
                "example": str(d.get("example", "")).strip(),
                "tags": str(d.get("tags", "")).strip(),
                "target": (
                    str(d.get("target", "writing")).strip()
                    if str(d.get("target", "")).strip() in ("writing", "main", "both")
                    else "writing"
                ),
            }
        )
    return out


class SkillGenerator:
    """skill 生成器：原文 → 可执行 skill 候选（真实 LLM，无工具单次调用）。

    S58：mode 区分——writing（文风/叙事技巧，target=writing）/
    main（类型/结构指导，target=main，给主循环看）。
    """

    def __init__(self, model: object) -> None:
        self._model = model

    def generate(
        self,
        source_text: str,
        hint: str = "",
        max_items: int = 5,
        mode: str = "writing",
    ) -> list[dict[str, str]]:
        """从原文提炼 skill 候选。

        source_text：待提炼的正文（导入的小说章节/片段，真实原文）。
        hint：可选指引（如"侧重打斗文风"/"侧重爽文节奏"），追加到提示。
        mode：S58——writing（文风/叙事技法）/ main（类型/结构组织指导，主循环看）。
        """
        if not source_text.strip():
            return []
        prompt = GENERATE_PROMPT_MAIN if mode == "main" else GENERATE_PROMPT
        prompt += f"\n{source_text[:6000]}\n"
        if hint.strip():
            prompt += f"\n额外指引：{hint.strip()}\n"
        prompt += f"\n提炼最多 {max_items} 条，输出 JSON 数组。"
        output = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        cands = _parse_skills(output.text)[:max_items]
        # 模式一致性：main 模式的候选强制 target=main（防模型漏标）
        if mode == "main":
            for c in cands:
                c["target"] = "main"
        return cands

    def generate_main(
        self,
        source_text: str,
        hint: str = "",
        max_items: int = 5,
    ) -> list[dict[str, str]]:
        """S58：类型/结构指导生成（target=main，给主循环看）。"""
        return self.generate(source_text, hint, max_items, mode="main")


def render_skill_candidates(candidates: list[dict[str, str]]) -> str:
    """把候选渲染成可读文本（供确认/展示）。"""
    if not candidates:
        return "（无有效候选）"
    lines: list[str] = []
    for i, c in enumerate(candidates, 1):
        lines.append(f"{i}. 【{c['name']}】")
        if c.get("description"):
            lines.append(f"   索引：{c['description']}")
        lines.append(f"   技法：{c['content']}")
        if c.get("example"):
            lines.append(f"   案例：{c['example']}")
        if c.get("tags"):
            lines.append(f"   标签：{c['tags']}")
    return "\n".join(lines)
