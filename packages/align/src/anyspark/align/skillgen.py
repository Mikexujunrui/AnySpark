"""
anyspark.align.skillgen — 叙事技巧生成器（S54：文风提炼 → skill 候选）。

设计决策（DESIGN §12.17 延续 + 实测经验）：
- 场景：作者喜欢某篇小说的文风 → 导入原文（斗破苍穹等）→ 提炼成可执行的
  叙事技巧 skill（name/description/content/example/tags 五段式）
- 坑（实测）：LLM 生成 skill 时天然倾向**描述性语言**（"文风大气磅礴"
  "节奏明快"）——这类抽象评价对模型写作零指导价值（怎么写出"大气磅礴"？
  模型不知道）。
- 对策（决策记录）：**最好用的是 ① 负面性 ② 直接案例**：
  - 负面约束："不要铺垫环境再推进"（负面清单最好执行）
  - 直接案例：必须**摘录自输入原文**（真实文本），不是 LLM 编造
- prompt 里硬性禁止抽象描述（"文风XX""描写细腻"类词），强制可执行形式

机制硬编码（提炼流程/输出 schema/解析），内容自然语言（技法文本/案例）。
"""

from __future__ import annotations

import logging
import re

from anyspark.core import Message
from anyspark.core.jsonutil import parse_json_array

logger = logging.getLogger("anyspark.align.skillgen")


def _classify_model_error(exc: Exception) -> str:
    """S113：把模型调用异常分类成用户可读的原因（拆书/提炼诊断用）。"""
    msg = str(exc)
    low = msg.lower()
    if "data_inspection_failed" in msg or "inappropriate content" in low:
        return "书内容可能含敏感内容，被模型服务内容审核拦截（该段无法提炼）"
    if "invalid_api_key" in msg or "authenticationerror" in low or "401" in msg:
        return "API Key 无效或未配置（请检查 data/.env 的 DEEPSEEK_API_KEY）"
    if "rate limit" in low or "429" in msg:
        return "请求过于频繁被限流（请稍后重试）"
    if "connection" in low or "timeout" in low or "network" in low:
        return f"网络/连接异常：{msg[:120]}"
    return f"{type(exc).__name__}: {msg[:150]}"


def _summarize_errors(reasons: list[str], limit: int = 3) -> str:
    """S113：汇总分段失败原因（去重 + 截断，last_error 透出用）。"""
    if not reasons:
        return "未知原因（各段模型调用均无输出）"
    seen: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.append(r)
    return "；".join(seen[:limit]) + (
        f"（共 {len(reasons)} 段失败）" if len(reasons) > limit else ""
    )


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
[{"name": "技法名（具体可执行，如'短句直给式推进'）", "description": "一句话索引", "content": "技法说明（负面约束/正面做法，尽量落到句式/用词/节奏），2-3 句", "example": "原文摘录或自拟示范 + 一句为何有效", "tags": "适用场景，逗号分隔，如'打斗,高潮'", "type": "writing或main（写作层技法用writing；章节结构/类型组织指导用main；两者都影响用both）"}]

给定正文：
"""

# 主循环视角的类型/结构指导生成提示（S58：type=main 的类型 skill）
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
[{"name": "指导名（如'爽文先压制再爆发'）", "description": "一句话索引", "content": "结构/类型/节奏/组织的可执行指导，2-3 句", "example": "原文结构示例或自拟示范 + 一句为何有效", "tags": "适用场景，逗号分隔，如'爽文,节奏'", "type": "main（主循环指导）"}]

给定正文：
"""

# 整本书拆解提示（S78：拆书 → 融合成一本一个「书名」skill）
# 用途：把一部参考书拆解成一份完整方法论 skill——name=书名（写作时按书名点名引用），
# content=多维融合（文风/节奏/结构/人设/对白/信息投放/钩子），分小节，全部可执行。
# 与 GENERATE_PROMPT 的区别：那个是单章/单维度提炼 N 条技法；拆书是把整本书的
# 写法融合成一份（参考书 = 引用单位 = skill 粒度，注入时一次点名拿到整本方法论）。
GENERATE_PROMPT_BOOK = """你是小说拆书器。给定一部小说的代表性原文片段（开篇/中段/高潮拼接），
把**整本书的写法**拆解并融合成**一份**完整的方法论 skill（不是多条候选——一份就够）。

【参考书 = 引用单位】
- 这条 skill 的 name = 书名。将来写作时用户说"按这本书的风格写"，就是点名这一条。
- 所以它必须是整本书写法的完整画像，而不是其中某几条技法。

【拆解维度】（按原文实际特点取舍，没特点的维度不强写）：
  1. 文风/句式：长短句习惯、铺陈还是直给、重复/排比、用词（口语/书面/形容词密度/动词）
  2. 节奏节拍：快慢交替、高潮频率与间隔、每几章一个小高潮、情绪起伏点
  3. 结构组织：类型惯例（如爽文先压制再爆发）、开篇怎么立钩子、主线/支线怎么推进
  4. 人设塑造：主角/配角怎么立起来、金手指/成长线的设计逻辑
  5. 对白：直给还是潜台词、说话方式、对白与动作/内心的穿插
  6. 信息投放：新信息直接交代还是透过感知/反应间接流露、悬念/伏笔怎么埋怎么收
  7. 爽点/钩子设计：情绪兑现点、退婚流/三年之约这类长效钩子的设计逻辑

【可执行要求】
- 每小节给：负面约束（不要XXX）+ 正面做法（怎么做）+ 原文摘录案例（为什么这样有效）。
- 案例必须逐字摘录自给定原文片段；找不到合适摘录写"（无合适摘录）"，禁止自拟编造。
- 拒绝抽象概括（"文风爽快"是无效的）——必须落到能照着写的动作。
- content 会较长（500-1500 字），这是整本书方法论，值得；但每句仍要可执行。

【description 要求】一句话给主循环索引："书名：风格标签/类型标签，核心特点"，
如"斗破苍穹：玄幻爽文——退婚流开局/三年之约钩子/压制-爆发节奏/金手指升级线"。

【输出格式】（严格 JSON 数组，单元素，不要其它文字）：
[{"name": "书名", "description": "一句话索引", "content": "分小节整本方法论", "example": "原文代表性摘录 + 一句为何有效", "tags": "类型标签，逗号分隔，如'玄幻,爽文,升级流'", "type": "both（文风给写作、结构给主循环，两种都要）"}]

给定代表性原文片段：
"""

# 剧情模式模板生成提示（S69：从书提炼剧情模式 → 模板库）
# 用途：给探索的"剧情模式模板"——DESIGN 机制 6 的四要素元数据（粒度/位置/功能/
# 可变参数），探索的 template 来源据此派生方向（S68 已接线真实模板注入）。
# 与 GENERATE_PROMPT_MAIN 的区别：main=给主循环看的组织指导（决策指令）；
# plot=给探索看的模式模板（"怎么用能变出什么"，模板是起点变体才是目标）。
# 输入为**多章/全书片段**（跨章结构归纳，单章提不到剧情模式）。
GENERATE_PROMPT_PLOT = """你是小说剧情模式提炼器。给定一部小说的**多章片段**，提炼出**可复用剧情模式模板**。

【什么对探索最有指导价值】
- 提炼的是**结构层的剧情模式**（跨章组织方式），不是句子/用词技法（那是文风提取的事）：
  ① 开篇钩子：故事/章节怎么开场立钩子（什么悬念/代价/身份设定）
  ② 冲突升级：冲突怎么逐步升级（间隔、台阶、爆点在哪）
  ③ 章节衔接：章末怎么留钩子、跨章怎么保持张力
  ④ 情感节拍：情绪起伏的分布（铺垫→谷底→爆发→余波）
  ⑤ 收束方式：高潮怎么处理、结局/悬念怎么收
- 每个模式要写明**可变参数**（模板中可替换的位置）——探索派生方向时靠变体，不是照搬。

【复现测试】
- 提炼前问自己：这是这本书**有辨识度的剧情组织方式**，还是通用套路？
  通用套路不要提炼（如"主角成长变强"人人都会）；有辨识度的组织方式才提炼。

【跨章要求】
- 输入是多章片段：先看整体结构再提炼，案例要引用具体章节位置
  （如"第1章埋身世钩子，第3章才揭示"），不是单句摘录。

【简洁自检】
- 每条模板 description 应能**一次读完就内化**：2-4 句，去掉形容词，只留结构动作。

【输出格式】（严格 JSON 数组，不要其它文字）：
[{"name": "模板名（具体可执行，如'护送式旅程·双线交汇'）", "description": "剧情模式说明（结构/冲突/节拍，含可变参数位置），2-4 句", "granularity": "粒度：全书/卷/章/场景/段落 之一", "position": "位置：开局/发展/高潮/结局 之一", "function": "功能：铺垫/主线/悬念/爽点/情感 之一", "params": ["可变参数1", "可变参数2"]}]

给定多章片段：
"""


# 剧情模式提炼提示（骨架笔记版，S127：拆书双落——骨架笔记 → 剧情模式 plot 子条）
# 与 GENERATE_PROMPT_PLOT 的区别：输入不是多章正文，而是骨架扫描的结构笔记
# （跨卷机关/主角目的/阶段/开篇收尾——已基于标题轨迹归纳好全局关系），
# 从全局结构直接提炼可复用剧情模式；输出同样四要素元数据（探索派生方向用）。
GENERATE_PROMPT_PLOT_FROM_SKELETON = """你是小说剧情模式提炼器。给定一部小说的**结构分析笔记**
（基于全书章节标题轨迹分析得出，含跨卷叙事机关/主角最终目的/剧情大阶段/开篇与收尾设计），
提炼出**可复用剧情模式模板**（给探索派生方向用）。

【什么对探索最有指导价值】
- 结构笔记里的**跨卷机关**往往就是最高价值的剧情模式（如时间回环/双线并行/真相逐层揭示）
- 提炼的是**结构层的剧情模式**（跨章组织方式），不是句子/用词技法：
  ① 开篇钩子：故事怎么开场立钩子（什么悬念/代价/身份设定）
  ② 冲突升级：冲突怎么逐步升级（间隔、台阶、爆点在哪）
  ③ 章节衔接：章末怎么留钩子、跨章怎么保持张力
  ④ 情感节拍：情绪起伏的分布（铺垫→谷底→爆发→余波）
  ⑤ 收束方式：高潮怎么处理、结局/悬念怎么收
- 每个模式要写明**可变参数**（模板中可替换的位置）——探索派生方向靠变体，不是照搬

【复现测试】
- 提炼前问自己：这是这本书**有辨识度的剧情组织方式**，还是通用套路？
  通用套路不要提炼（如"主角成长变强"）；有辨识度的组织方式才提炼。

【简洁自检】
- 每条模板 description 应能**一次读完就内化**：2-4 句，去掉形容词，只留结构动作。

【输出格式】（严格 JSON 数组，不要其它文字）：
[{"name": "模板名（具体可执行，如'时间回环·宿命闭环'）", "description": "剧情模式说明（结构/冲突/节拍，含可变参数位置），2-4 句", "granularity": "粒度：全书/卷/章/场景/段落 之一", "position": "位置：开局/发展/高潮/结局 之一", "function": "功能：铺垫/主线/悬念/爽点/情感 之一", "params": ["可变参数1", "可变参数2"]}]

结构分析笔记如下：
"""


# 拆书抽样（S106：12MB 整本书提炼修复——原实现只取开头 20000 字符 ≈ 1.6%）
# 对齐 GENERATE_PROMPT_BOOK 设计意图「开篇/中段/高潮拼接」：全文均匀抽段分别拆解 → 归并
_BOOK_SAMPLES = 16  # 抽样段数（覆盖全书，成本 = 16 次提炼 + 1 次归并）
_BOOK_WINDOW = 12000  # 每段取的连续字符窗口（喂模型前再限 20000）


MERGE_PROMPT_BOOK = """你是小说拆书汇总器。以下是同一本书多个代表段分别拆解出的方法论片段
（各段已按 7 维度拆过，存在重复/冲突/各自侧重）。
把 N 段融合成**一份**完整、去重、自洽的整本书方法论 skill（name=书名）。

规则：
- 合并重复维度（取最完整/最具体的表述），保留各段独有特征（开篇文风/中段节奏/结尾钩子逻辑都要覆盖）
- 冲突时以出现频率高者为准，罕见的章节特征标注「（部分章节）」
- 拒绝空洞概括——每句仍须落到可执行动作（负面约束 + 正面做法 + 原文摘录案例）
- 案例必须逐字摘录自给定原文片段；找不到写"（无合适摘录）"，禁止自拟编造
- 输出 JSON 数组（仅一条）：[{"name": 书名, "description": 一句话索引, "content": 融合后完整方法论, "tags": "文风,结构,节奏"}]

以下为各段拆解结果：
"""

# 骨架扫描 prompt（S114：全书机关发现——只看章节标题轨迹，不看正文）
# 实测（猎手准则 367 万字）：仅凭 1281 章标题就发现「循环/重开/时间机器」机制 +
# 主角最终目的（创造新世界）——抽样+局部提炼结构上做不到的全局关系，标题轨迹可见。
SKELETON_PROMPT = """你是小说结构分析师。以下是《{book_name}》的全书骨架：全部章节标题（无正文）。
请基于骨架证据（章节标题的走向、重复出现的关键词、主题变化）分析：

1. **跨卷叙事机关**：这本书有没有独特的结构设计（如时间回环、双线并行、多重视角、
   真相逐层揭示、结局反转开头）？请给出支撑的章节标题证据（引用具体章名）。
2. **主角最终目的**：从标题轨迹推断，主角的最终目标/全书主线钩子是什么？
3. **剧情大阶段**：全书分几个大阶段，各自的主题和转折点（以章为界）？
4. **开篇与收尾设计**：开篇怎么立钩子，结局怎么收，首尾有什么呼应？

要求：必须基于骨架推理并引用具体章节标题；无法从标题确定的内容明确说"标题看不出来"。
不要编造、不要臆测正文内容。请用中文分点回答。

骨架如下：
"""

# 定点精读 prompt（S114：从骨架笔记定位机关章 → 精读原文 → 提炼架构技法 skill）
# 防案例幻觉（实测教训）：必须**先给原文、后提问**，不得预先告知答案——
# 实验版先告诉模型"主角经历被过去的自己安排"，模型编造了"神国墙壁"等原文不存在的细节。
REFINE_PROMPT = """你是小说拆书器。以下是《{book_name}》的若干关键章节原文（可能不连续，是全书不同位置的代表）。
另附一份**结构分析师基于章节标题的推断**（仅供参考——可能在原文成立，也可能不成立）。
请通读原文，找出这本书**最独特的架构级叙事设计**——跨章节/跨全书的叙事机关
（时间循环/世界重置、宿命闭环、双线并行、多重视角、真相逐层揭示、结局反转开头等）。

规则：
- **优先提炼全书级/跨章节的叙事机关**（价值高于段落级技法），可输出 1-3 条
- 附带的标题推断可作线索，但**必须用原文验证**：原文有支撑证据才提炼，原文不支持就忽略
- 只提炼**原文中实际存在**、有原文证据支撑的设计；不要臆测
- 提炼成**可执行的叙事技法 skill**（可迁移到任何故事的设计方法，不是本书剧情复述）
- content 给出：负面约束（不要XXX）+ 正面做法（分步设计），可执行，150-400 字
- example 必须**逐字摘录自给定原文**（引用原句，可标注出处章号）；找不到合适摘录写"（无合适摘录）"，**禁止编造或改写原文**

输出（严格 JSON 数组，可多条）：
[{{"name": "技法名", "description": "一句话索引", "content": "...", "example": "原文摘录 + 一句为何有效", "tags": "适用题材,逗号分隔", "type": "main"}}]

关键章节原文如下：
"""

# S114 拆书三层参数
_MIN_CHAPTERS = 5  # 章节数低于此 → 回退字符均匀抽样（S106 原逻辑）
_PER_VOL = 4  # 每卷选 4 章（首/25%/75%/尾）
_MAX_SELECT = 24  # 选章上限（拆解批数 = ceil(24/4) = 6 批）
_BATCH_SIZE = 4  # 每批拼 4 整章（≈1.2 万字/批）
_MAX_SKELETON_TITLES = 2000  # 骨架扫描标题上限
_REFINE_LIMIT = 6  # 定点精读章节上限（机关章）+ 首尾 2 = 8 章
_REFINE_CHARS = 4000  # 每章精读截断字符

# 机关关键词（骨架笔记提到则定位其原文直接揭示段落，保证回环揭示点在精读片段）
_MECHANISM_KEYWORDS = (
    "回到过去",
    "时间循环",
    "时间回环",
    "时间机器",
    "重启",
    "坏档",
    "重开",
    "造物主",
    "时间线",
    "轮回",
    "改变过去",
    "世界重置",
)

# 章节/卷标记（行首匹配防正文误切）
_CHAPTER_LINE_RE = re.compile(r"^第[0-9一二三四五六七八九十百千]+章\s*([^\n]*)", re.MULTILINE)
_HEADER_LINE_RE = re.compile(r"^【([^】]{1,40})】\s*$", re.MULTILINE)
_VOL_LINE_RE = re.compile(r"第[一二三四五六七八九十百千0-9]+卷\s*([^\n]*)")
_CHAPTER_NUM_RE = re.compile(r"第\s*(\d{1,5})\s*(?:[-~至到]\s*(\d{1,5}))?\s*章")


def _parse_chapters(text: str) -> list[tuple[str, str]]:
    """解析章节结构 → [(标题, 正文)]。优先【标题】行（书库格式），回退"第X章"行。

    无结构（< _MIN_CHAPTERS 章）返回 []——调用方回退字符均匀抽样。
    """
    patterns = (_HEADER_LINE_RE, _CHAPTER_LINE_RE)
    for pat in patterns:
        matches = list(pat.finditer(text))
        if len(matches) < _MIN_CHAPTERS:
            continue
        out: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            title = m.group(1).strip() or f"第{i + 1}章"
            out.append((title, text[m.end() : end].strip()))
        return out
    return []


def _select_structural_chapters(chapters: list[tuple[str, str]]) -> list[int]:
    """按卷分层选代表章索引：每卷 首/25%/75%/尾 + 全书首尾。

    卷边界 = 章标题或章正文开头含"第X卷"标记（书库格式：卷标记成独立章，
    标题即卷名；txt 格式：卷标记常在章首）。卷标记 < 3 个 → 回退全局均匀选章
    （实测与卷分层效果近似，且不依赖卷解析正确性）。
    """
    n = len(chapters)
    if n <= _MAX_SELECT:
        return list(range(n))  # 书不大 → 全选
    vol_idx = [
        i
        for i, (title, body) in enumerate(chapters)
        if _VOL_LINE_RE.search(title) or _VOL_LINE_RE.search(body[:500])
    ]
    if len(vol_idx) >= 3:
        selected: list[int] = []
        bounds = [*vol_idx, n]
        for k in range(len(vol_idx)):
            a, b = bounds[k], bounds[k + 1]
            m = b - a
            if m <= 0:
                continue
            idxs = sorted({a, a + int(m * 0.25), a + int(m * 0.75), b - 1})
            selected.extend(i for i in idxs if a <= i < b)
    else:
        # 全局均匀（留 2 个名额给首尾章，防截断丢失）
        selected = [int(i * n / (_MAX_SELECT - 2)) for i in range(_MAX_SELECT - 2)]
    # 强制含全书首尾章（不因截断丢失）
    selected = sorted(set([0, n - 1, *selected]))[:_MAX_SELECT]
    return selected


def _build_batches(
    chapters: list[tuple[str, str]], selected: list[int], batch_size: int = _BATCH_SIZE
) -> list[str]:
    """选中整章按原顺序拼批（批内同卷、叙事相邻，章节边界完整）。"""
    batches: list[str] = []
    for i in range(0, len(selected), batch_size):
        chunk = selected[i : i + batch_size]
        parts = [f"【{chapters[j][0]}】\n{chapters[j][1]}\n" for j in chunk]
        batches.append("\n".join(parts))
    return batches


def _extract_chapter_nums(note: str) -> list[tuple[int, int]]:
    """从结构笔记提取章节号引用（"第85章" / "第85-90章" / "第85到90章"）。"""
    return [
        (int(m.group(1)), int(m.group(2) or m.group(1))) for m in _CHAPTER_NUM_RE.finditer(note)
    ]


def _locate_mechanism_passages(
    chapters: list[tuple[str, str]], note: str, window: int = 1600
) -> list[str]:
    """骨架笔记提到的机关关键词 → 在原文定位直接揭示段落。

    骨架扫描给的是"标题轨迹推断"（如时间循环/世界重置），但回环的直接揭示
    （"想要回到过去""世界重启"）常在章的中后部，笔记引用的章头未必覆盖——
    按关键词定位这些段落强制纳入精读片段，让模型看到证据后提炼技法。
    """
    kws = [kw for kw in _MECHANISM_KEYWORDS if kw in note]
    out: list[str] = []
    for kw in kws:
        for _t, body in chapters:
            i = body.find(kw)
            if i >= 0:
                start = max(0, i - window // 3)
                out.append(f"【关键词「{kw}」定位段】\n{body[start : i + window]}")
                break
    return out


# 精读示例机器校验（S114：防案例幻觉兜底——实测"先原文后提问"仍会编造，
# 需硬校验：example 中引号内长句必须逐字出现在精读片段，否则清空）
_EXAMPLE_QUOTE_RE = re.compile(r'[“"『]([^”"』]{8,80})[”"』]')


def _sanitize_examples(cands: list[dict[str, str]], source: str) -> list[dict[str, str]]:
    """案例真实性机器校验：example 中引号内长句必须在 source（精读片段）逐字出现。

    不满足 → 清空 example 并记日志（宁缺毋滥：编造案例会误导写作模型）。
    """
    for c in cands:
        ex = str(c.get("example", ""))
        if not ex or ex == "（无合适摘录）":
            continue
        quoted = _EXAMPLE_QUOTE_RE.findall(ex)
        if not quoted:
            continue  # 无引号句（自述性案例）不判
        bad = [q for q in quoted if q not in source]
        if bad:
            logger.warning(
                "架构技法案例疑似编造，已清空 example: %s -> %r", c.get("name"), bad[0][:30]
            )
            c["example"] = "（无合适摘录）"
    return cands


def _sample_blocks(text: str, n: int, window: int) -> list[str]:
    """整本书均匀抽 n 段：每段起点 = i*total/n，取其后连续 window 字符。

    书小于 n*window 时整体一次返回（老路径）；否则覆盖开篇/中段/结尾。
    """
    total = len(text)
    if total <= n * window:
        return [text]
    return [text[i * total // n : i * total // n + window] for i in range(n)]


def _parse_skills(raw: str) -> list[dict[str, str]]:
    """宽容解析模型输出的 skill JSON 数组（R1 收敛到 core.jsonutil）。

    S127：type 键替代 target（PLAN-SKILL-UNIFY 阶段 1）——兼容读模型仍输出
    target 的情况（旧 prompt 缓存），两者都收；合法值 writing/main/plot/both。
    """
    data = parse_json_array(raw)
    if data is None:
        return []
    out: list[dict[str, str]] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "")).strip()
        content = str(d.get("content", "")).strip()
        if not name or not content:
            continue
        raw_type = str(d.get("type", "") or d.get("target", "")).strip()
        out.append(
            {
                "name": name,
                "description": str(d.get("description", "")).strip(),
                "content": content,
                "example": str(d.get("example", "")).strip(),
                "tags": str(d.get("tags", "")).strip(),
                "type": raw_type if raw_type in ("writing", "main", "plot", "both") else "writing",
            }
        )
    return out


def _parse_templates(raw: str) -> list[dict[str, str]]:
    """宽容解析剧情模式模板候选（JSON 数组，含四要素元数据）。

    与 _parse_skills 共用提取逻辑，但校验四要素：granularity/position/function
    限制在默认分类集内（防模型乱填；未知值回落默认），params 归一为逗号串。
    """
    data = parse_json_array(raw)
    if data is None:
        return []
    valid_gr = ("全书", "卷", "章", "场景", "段落")
    valid_pos = ("开局", "发展", "高潮", "结局")
    valid_fn = ("铺垫", "主线", "悬念", "爽点", "情感")
    out: list[dict[str, str]] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "")).strip()
        description = str(d.get("description", "")).strip()
        if not name or not description:
            continue
        params = d.get("params", []) or []
        if isinstance(params, str):
            params = [p.strip() for p in params.split(",") if p.strip()]
        elif not isinstance(params, list):
            params = []
        out.append(
            {
                "name": name,
                "description": description,
                "granularity": str(d.get("granularity", "章")).strip()
                if str(d.get("granularity", "")).strip() in valid_gr
                else "章",
                "position": str(d.get("position", "发展")).strip()
                if str(d.get("position", "")).strip() in valid_pos
                else "发展",
                "function": str(d.get("function", "主线")).strip()
                if str(d.get("function", "")).strip() in valid_fn
                else "主线",
                "params": ",".join(str(p).strip() for p in params if str(p).strip()),
            }
        )
    return out


class SkillGenerator:
    """skill/模板 生成器：原文 → 可执行候选（真实 LLM，无工具单次调用）。

    S58：mode 区分——writing（文风/叙事技巧，type=writing）/ main
    （类型/结构指导，type=main，给主循环看）/ plot（S69：剧情模式模板，
    四要素元数据，给探索的 template 来源派生方向）。
    S127：target 语义并入 type（PLAN-SKILL-UNIFY 阶段 1）——候选输出 type 键。
    """

    def __init__(self, model: object) -> None:
        self._model = model
        # S113：最近一次提炼失败的诊断信息（供调用方透出给用户可读原因）。
        # generate_book 分段提炼时每段独立 try，全部失败也不抛异常——
        # 若吞掉原因，用户只看到「提炼失败（无有效候选）」而不知真因
        # （如内容被模型审核拦截 / key 无效 / 限流）。
        self.last_error = ""

    def generate(
        self,
        source_text: str,
        hint: str = "",
        max_items: int = 5,
        mode: str = "writing",
    ) -> list[dict[str, str]]:
        """从原文提炼候选。

        source_text：待提炼的正文（导入的小说章节/片段，真实原文）。
        hint：可选指引（如"侧重打斗文风"/"侧重爽文节奏"），追加到提示。
        mode：S58——writing（文风/叙事技法）/ main（类型/结构组织指导，主循环看）/\n        plot（S69：剧情模式模板，四要素元数据，给探索用）。
        """
        if not source_text.strip():
            return []
        if mode == "plot":
            # S69：剧情模式需要跨章结构归纳——输入窗口比单章文风提炼更大
            prompt = GENERATE_PROMPT_PLOT + f"\n{source_text[:12000]}\n"
            if hint.strip():
                prompt += f"\n额外指引：{hint.strip()}\n"
            prompt += f"\n提炼最多 {max_items} 条模板，输出 JSON 数组。"
            output = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)],
                [],
            )
            return _parse_templates(output.text)[:max_items]
        if mode == "book":
            # S78：拆书——整本书多维拆解融合成一份「书名」skill（输入窗口取大，覆盖多章）
            prompt = GENERATE_PROMPT_BOOK + f"\n{source_text[:20000]}\n"
            if hint.strip():
                prompt += f"\n额外指引：{hint.strip()}\n"
            output = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)],
                [],
            )
            cands = _parse_skills(output.text)[:1]
            for c in cands:
                c["type"] = "both"  # 拆书方法论：文风给写作、结构给主循环
            return cands
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
        # 模式一致性：main 模式的候选强制 type=main（防模型漏标）
        if mode == "main":
            for c in cands:
                c["type"] = "main"
        return cands

    def generate_book(
        self, source_text: str, hint: str = "", book_name: str = ""
    ) -> list[dict[str, str]]:
        """S106+S114+S127：拆书（整本书）——三层提炼 + 剧情模式双落。

        ① 微观技法（_generate_book_micro）：结构感知选章（按卷分层整章拼批）→
           分批拆解 → 归并成一份「书名」skill（name=书名，一次点名拿到整本写法）
        ② 骨架扫描（_scan_skeleton）：卷+章标题（无正文）→ 全书结构笔记
           （跨卷叙事机关/主角目的/阶段——抽样+局部提炼结构上抓不到的全局关系）
        ③ 定点精读（_refine_architecture）：从笔记定位机关章 → 精读原文
           （先原文后提问，防案例幻觉）→ 提炼架构技法 skill（type=main）
        ④ 剧情模式（_derive_plot_from_skeleton，S127 双落）：骨架笔记 → 剧情模式
           plot 子条（type=plot，四要素扩展元数据）——骨架笔记一鱼两吃：
           既定位机关章（③），又派生剧情模式（④），拆书一次产出整包各 type 子条。

        book_name：书名（注入 prompt，修复 name=书名引用单位的准确性；
        缺省空串=不注入，回退旧行为）。
        无章节结构（< _MIN_CHAPTERS 章）回退字符均匀抽样（S106 原逻辑）。
        """
        if not source_text.strip():
            return []
        self.last_error = ""
        chapters = _parse_chapters(source_text)
        if len(chapters) < _MIN_CHAPTERS:
            return self._generate_book_uniform(source_text, hint, book_name)
        micro = self._generate_book_micro(chapters, hint, book_name)
        if not micro:
            # 微观全失败（可能被审核拦截/key 无效/限流）——last_error 已在微观内汇总
            return []
        note = self._scan_skeleton(chapters, book_name)
        arch = self._refine_architecture(chapters, note, book_name)
        # S127 双落：骨架笔记 → 剧情模式 plot 子条（骨架笔记空则跳过）
        plot = self._derive_plot_from_skeleton(note, book_name)
        result = micro + arch + plot
        for c in result:
            c.setdefault("type", "both")
        return result

    def _book_label(self, book_name: str) -> str:
        """书名注入标签（name=书名引用单位的准确性）。"""
        return f"（本书：《{book_name.strip()}》）" if book_name.strip() else ""

    def _generate_book_uniform(
        self, source_text: str, hint: str = "", book_name: str = ""
    ) -> list[dict[str, str]]:
        """S106 原逻辑（保留为无章节结构书的回退路径）：字符均匀抽样 + 归并。"""
        samples = _sample_blocks(source_text, _BOOK_SAMPLES, _BOOK_WINDOW)
        partials: list[str] = []
        fallback: list[dict[str, str]] = []
        # S113：收集各段失败原因（分类汇总，供 last_error 透出）
        err_reasons: list[str] = []
        label = self._book_label(book_name)
        for i, sample in enumerate(samples, 1):
            prompt = (
                GENERATE_PROMPT_BOOK + f"\n{label}（代表段 {i}/{len(samples)}）\n{sample[:20000]}\n"
            )
            if hint.strip():
                prompt += f"\n额外指引：{hint.strip()}\n"
            try:
                output = self._model.respond(  # type: ignore[attr-defined]
                    [Message(role="system", content=prompt)],
                    [],
                )
                cands = _parse_skills(output.text)[:1]
                if cands:
                    partials.append(f"【代表段 {i}】\n{cands[0].get('content', '')}")
                    if not fallback:
                        fallback = cands  # 归并失败时的降级：第一段结果
                else:
                    reason = f"段{i}: 模型输出解析失败（非 skill JSON）"
                    err_reasons.append(reason)
                    logger.warning(
                        "拆书提炼段 %d: 输出解析失败（前 80 字: %r）", i, output.text[:80]
                    )
            except Exception as exc:
                reason = _classify_model_error(exc)
                err_reasons.append(f"段{i}: {reason}")
                logger.warning("拆书提炼段 %d 失败: %s", i, reason)
        if not partials:
            # S113：全部失败——汇总原因透出（不静默）
            self.last_error = _summarize_errors(err_reasons)
            return []
        self.last_error = ""
        merge_prompt = MERGE_PROMPT_BOOK + f"{label}\n" + "\n\n".join(partials) + "\n"
        try:
            merged = _parse_skills(
                self._model.respond(  # type: ignore[attr-defined]
                    [Message(role="system", content=merge_prompt)], []
                ).text
            )[:1]
        except Exception as exc:
            logger.warning("拆书归并失败，降级用第一段: %s", _classify_model_error(exc))
            merged = []
        final = merged or fallback
        for c in final:
            c["type"] = "both"  # 拆书方法论：文风给写作、结构给主循环
        return final

    def _generate_book_micro(
        self,
        chapters: list[tuple[str, str]],
        hint: str = "",
        book_name: str = "",
    ) -> list[dict[str, str]]:
        """S114 微观技法层：按卷分层选整章 → 拼批 → 分批拆解 → 归并成书名方法论。

        与 S106 均匀抽样的区别：抽样单位从"字符窗口"变"整章"（章节边界完整，
        章末钩子可见），且按卷分层（每卷首/中/尾都覆盖，不靠均匀碰运气）。
        """
        selected = _select_structural_chapters(chapters)
        batches = _build_batches(chapters, selected)
        partials: list[str] = []
        fallback: list[dict[str, str]] = []
        err_reasons: list[str] = []
        label = self._book_label(book_name)
        for i, bt in enumerate(batches, 1):
            prompt = GENERATE_PROMPT_BOOK + f"\n{label}（代表批 {i}/{len(batches)}，整章）\n{bt}\n"
            if hint.strip():
                prompt += f"\n额外指引：{hint.strip()}\n"
            try:
                output = self._model.respond(  # type: ignore[attr-defined]
                    [Message(role="system", content=prompt)],
                    [],
                )
                cands = _parse_skills(output.text)[:1]
                if cands:
                    partials.append(f"【代表批 {i}】\n{cands[0].get('content', '')}")
                    if not fallback:
                        fallback = cands
                else:
                    reason = f"批{i}: 模型输出解析失败（非 skill JSON）"
                    err_reasons.append(reason)
                    logger.warning("拆书批 %d: 输出解析失败（前 80 字: %r）", i, output.text[:80])
            except Exception as exc:
                reason = _classify_model_error(exc)
                err_reasons.append(f"批{i}: {reason}")
                logger.warning("拆书批 %d 失败: %s", i, reason)
        if not partials:
            self.last_error = _summarize_errors(err_reasons)
            return []
        self.last_error = ""
        merge_prompt = MERGE_PROMPT_BOOK + f"{label}\n" + "\n\n".join(partials) + "\n"
        try:
            merged = _parse_skills(
                self._model.respond(  # type: ignore[attr-defined]
                    [Message(role="system", content=merge_prompt)], []
                ).text
            )[:1]
        except Exception as exc:
            logger.warning("拆书归并失败，降级用第一批: %s", _classify_model_error(exc))
            merged = []
        final = merged or fallback
        for c in final:
            c["type"] = "both"
        return final

    def _derive_plot_from_skeleton(self, note: str, book_name: str = "") -> list[dict[str, str]]:
        """S127 拆书双落：骨架笔记 → 剧情模式 plot 子条（type=plot）。

        与定点精读（_refine_architecture）共用骨架笔记：那个提炼架构机关技法
        （type=main，主循环规划）；这里提炼剧情模式模板（type=plot，探索
        派生方向）——四要素元数据（granularity/position/function/params）存
        ext 扩展 JSON，机制校验枚举回落默认（复用 _parse_templates）。
        失败/空笔记返回 []（不影响拆书主产出）。
        """
        if not note.strip():
            return []
        name = book_name.strip() or "本书"
        prompt = (
            GENERATE_PROMPT_PLOT_FROM_SKELETON + f"\n（本书：《{name}》 结构笔记）\n{note[:6000]}\n"
        )
        try:
            out = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)], []
            )
        except Exception as exc:
            logger.warning("拆书剧情模式提炼失败: %s", _classify_model_error(exc))
            return []
        cands = _parse_templates(out.text)
        # 剧情模式 → plot skill：四要素进 ext（扩展字段），content 保留模式说明
        import json as _json

        result: list[dict[str, str]] = []
        for c in cands:
            # _parse_templates 把 params 归一为逗号串；ext 里还原成列表（阶段 2 探索消费）
            params = [p.strip() for p in c["params"].split(",") if p.strip()]
            result.append(
                {
                    "name": c["name"],
                    "description": c["description"],
                    "content": f"剧情模式：{c['description']}",
                    "example": "",
                    "tags": "剧情模式",
                    "type": "plot",
                    "ext": _json.dumps(
                        {
                            "granularity": c["granularity"],
                            "position": c["position"],
                            "function": c["function"],
                            "params": params,
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return result

    def _scan_skeleton(self, chapters: list[tuple[str, str]], book_name: str = "") -> str:
        """S114 骨架扫描：全部章标题（无正文）→ 结构笔记（机关/目的/阶段）。

        失败返回 ""（调用方跳过定点精读，仅保留微观方法论）。
        """
        n = len(chapters)
        titles = [t for t, _ in chapters]
        if n > _MAX_SKELETON_TITLES:
            step = n / _MAX_SKELETON_TITLES
            titles = [titles[int(i * step)] for i in range(_MAX_SKELETON_TITLES - 1)] + [titles[-1]]
        skeleton = "\n".join(f"第{i + 1}章 {t}" for i, t in enumerate(titles))
        name = book_name.strip() or "本书"
        prompt = SKELETON_PROMPT.format(book_name=name) + skeleton
        try:
            out = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)], []
            )
            return str(out.text).strip()
        except Exception as exc:
            logger.warning("拆书骨架扫描失败: %s", _classify_model_error(exc))
            return ""

    def _refine_architecture(
        self,
        chapters: list[tuple[str, str]],
        note: str,
        book_name: str = "",
    ) -> list[dict[str, str]]:
        """S114 定点精读：从结构笔记提取机关章号 → 精读原文 → 架构技法 skill。

        防案例幻觉：精读 prompt 先给原文、后中立提问（不预先告知答案），
        example 强制逐字摘录。type 统一 main（架构机关给主循环规划用）。
        """
        if not note.strip():
            return []
        nums = _extract_chapter_nums(note)
        idxs: set[int] = set()
        for a, b in nums:
            for k in range(a, min(b, a + 4) + 1):
                if 1 <= k <= len(chapters):
                    idxs.add(k - 1)
        idxs.add(0)
        idxs.add(len(chapters) - 1)
        # 机关章（笔记引用的）排最前，首尾章兜底放最后（防精读注意力偏首章）
        ref_idx = sorted(i for i in idxs if 0 < i < len(chapters) - 1)
        ordered = ([*ref_idx, 0, len(chapters) - 1])[:_REFINE_LIMIT]
        if len(ordered) < 2:
            return []
        parts = []
        for i in ordered:
            t, body = chapters[i]
            parts.append(f"【第{i + 1}章 {t}】\n{body[:_REFINE_CHARS]}")
        # 骨架笔记提到的机关关键词 → 原文直接揭示段落（放最前，保证回环证据可见）
        passages = _locate_mechanism_passages(chapters, note)
        excerpt = "\n\n".join([*passages, *parts])
        name = book_name.strip() or "本书"
        prompt = REFINE_PROMPT.format(book_name=name)
        # 骨架笔记作线索（截断，标注需原文验证）——防精读注意力偏首章/缺机关章
        note_head = note.strip()[:2500]
        prompt += f"\n【结构分析师的标题推断（仅供参考，需原文验证）】\n{note_head}\n\n"
        prompt += excerpt
        try:
            out = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)], []
            )
        except Exception as exc:
            logger.warning("拆书定点精读失败: %s", _classify_model_error(exc))
            return []
        cands = _parse_skills(out.text)
        for c in cands:
            c["type"] = "main"  # 架构机关给主循环
        return _sanitize_examples(cands, excerpt)

    def generate_main(
        self,
        source_text: str,
        hint: str = "",
        max_items: int = 5,
    ) -> list[dict[str, str]]:
        """S58：类型/结构指导生成（type=main，给主循环看）。"""
        return self.generate(source_text, hint, max_items, mode="main")

    def generate_plot(
        self,
        source_text: str,
        hint: str = "",
        max_items: int = 5,
    ) -> list[dict[str, str]]:
        """S69：剧情模式模板生成（四要素元数据，给探索用）。"""
        return self.generate(source_text, hint, max_items, mode="plot")


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
