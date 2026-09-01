"""anyspark.server.genres — 文体 profile 注册表（S247，DESIGN §12.48）。

动机（缺陷 D1）：小说语境固化在 prompt 层——写作引擎人设/拆解维度/学习审查
关注点都按小说措辞写死，学术/报告类文本只能硬套。本模块把"按体裁变化的
自然语言内容"收敛为 profile 数据；机制（写作调用/检测/拆解管线）不分文体。

设计约束：
- profile 是**内容**（自然语言），不是机制——新增文体=加一条数据，不改代码路径
- fiction 为缺省回退：人设/要求句与 S246 前行为逐字一致（存量项目零变化）
- 存储不在此处：文体归属项目，权威在工作区文件（workspace.read_genre，
  P1 文件权威哲学）；工具层运行时读取（支持中途切文体，非装配时快照）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenreProfile:
    """一个文体的差异化自然语言内容（机制共用，内容按文体切换）。"""

    name: str
    label: str
    # 写作引擎（tools_writing._clean_write）：人设句 + 要求句
    engine_persona: str
    engine_requirements: str
    # 拆解维度（S248：skillgen 拆书/拆论文共用管线，维度按文体切换）
    decomposition_dimensions: str
    # 学习审查关注点（tasks.review_for_learning：拼在审查文本前，空串=不加）
    learning_hint: str = ""


FICTION = GenreProfile(
    name="fiction",
    label="小说（虚构写作）",
    engine_persona="你是 AnySpark 小说写作引擎。严格根据【写作意图】与【写作参考】撰写正文。",
    engine_requirements="要求：具体、有画面感、杜绝空泛总结；直接输出正文，不要解释。",
    decomposition_dimensions=(
        "从以下七个维度拆解本章写法：①文风（句式/词汇/比喻密度）②节奏（场景切换与"
        "快慢交替）③结构（开场钩子/转折/收束方式）④人设呈现（言行如何塑造人物）"
        "⑤对白（潜台词/信息量/个性化）⑥信息投放（读者知道什么/何时知道）⑦钩子"
        "（章末悬念与期待管理）。"
    ),
)
ACADEMIC = GenreProfile(
    name="academic",
    label="学术（论文/综述）",
    engine_persona=(
        "你是 AnySpark 学术写作引擎。严格根据【写作意图】与【写作参考】撰写正文"
        "（论文/综述/学位论文章节）。"
    ),
    engine_requirements=(
        "要求：论述严谨、术语准确、论断有据（无出处的断言不写）；直接输出正文，不要解释。"
    ),
    decomposition_dimensions=(
        "从以下七个维度拆解本文写法：①研究问题（问题定义与动机陈述方式）②方法与数据"
        "（方法描述的可复现性、数据来源交代）③贡献与结论（贡献如何主张、结论如何回应"
        "问题）④论证链（论点-证据-推理的衔接方式）⑤结构与组织（章节分工与过渡衔接）"
        "⑥表达规范（术语一致性、句式客观性、时态语态习惯）⑦文献使用（引用密度与"
        "位置、综述与评述的配比）。"
    ),
    learning_hint="（本文本为学术写作：重点关注术语/格式偏好、论证与引用习惯、规范类要求。）",
)
REPORT = GenreProfile(
    name="report",
    label="报告（申报书/策划/公文）",
    engine_persona=(
        "你是 AnySpark 报告写作引擎。严格根据【写作意图】与【写作参考】撰写正文"
        "（申报书/策划案/报告）。"
    ),
    engine_requirements=("要求：结构清晰、要点明确、语言凝练有说服力；直接输出正文，不要解释。"),
    decomposition_dimensions=(
        "从以下七个维度拆解本文写法：①目标主张（要说服谁、诉求是什么）②结构与板块"
        "（章节划分逻辑与读者动线）③论据组织（数据/案例/先例的使用方式）④说理策略"
        "（痛点-方案-收益的推进方式）⑤表达风格（正式度、口号化程度、术语密度）"
        "⑥信息密度（每段承载的要点数、清单化程度）⑦行动引导（请求/安排/承诺的收束方式）。"
    ),
    learning_hint="（本文本为报告/申报类写作：重点关注格式框架偏好、表述口径、评审方要求。）",
)

_BUILTIN: dict[str, GenreProfile] = {p.name: p for p in (FICTION, ACADEMIC, REPORT)}


def get_profile(name: str | None) -> GenreProfile:
    """按名称取文体 profile；未知/缺省回退 fiction（存量行为不变）。"""
    return _BUILTIN.get((name or "fiction").strip().lower(), FICTION)
