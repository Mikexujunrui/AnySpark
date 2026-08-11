"""
anyspark.server.schemas — Pydantic 请求/响应模型 + SSE/时间辅助（S80 拆分）。

从 app.py 搬移（行为零变化）：78 个请求/响应模型 + _sse_frame + _now_iso_rec。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户输入")
    conversation_id: str | None = None
    book_id: str = "main"  # 项目 id（叙事树/简介/设定档按项目隔离）
    system_prompt: str | None = None
    temperature: float = 0.7
    agency_level: int | None = None  # 能动级别 0-4（覆盖当前档位；缺省用已存档位）
    # 增强按需装配（S15："你要什么再装什么"——默认关的增强，点亮才挂）
    enable_search: bool = False  # 网络搜索工具按需注册（默认关：写作主链路不背考据能力）
    enable_extras: bool = False  # S32 扩展工具（read_material）按需点亮；S63 check_text 退役
    enable_domain: bool = True  # S48-P2 领域工具（图谱查证/伏笔登记/计划推进/设定查证）默认开
    enable_codex: bool = False  # S48-P5 代码扩展 run_code（沙箱，默认关：安全按需点亮）
    enable_workflow: bool = False  # S59 工作流 agent 工具（list/run/status/generate）默认关
    enable_play: bool = False  # S65 互动推演 agent 工具（play_start/choose/status/export）默认关
    extract_graph: bool = True  # 章节落盘后图谱抽取（默认开保持现状；可关省 token）
    skip_inject: list[str] = []  # 细粒度跳过注入：manual/graph/agency/bias/plot 子集
    # S58b 上下文模式：auto(默认=干净,不继承场景记忆)/continue(显式继承场景记忆+计划)/fresh(同auto)
    # 主人偏好：默认不继承——新任务/探索不受上次对话干扰；跨会话续写时显式 continue
    context_mode: str = "auto"  # auto | continue | fresh
    # S47 运行时模型选择：缺省用注册表当前激活模型；thinking 覆盖该模型默认思考强度
    model_id: str | None = None  # 指定用哪个已配置模型（未配置/不存在 → 400）
    thinking: str | None = None  # 思考强度覆盖：off/low/medium/high/xhigh/max（None=用模型配置）


class ModelIn(BaseModel):
    """S47 模型配置写入（新增或更新；id 缺省由 name 生成 slug）。"""

    id: str | None = None
    name: str
    base_url: str | None = None  # 缺省用 env 默认端点（DEEPSEEK_BASE_URL）
    model: str  # 模型名（如 deepseek-v4-flash / deepseek-v4-pro）
    api_key: str | None = None  # 缺省用 env DEEPSEEK_API_KEY
    context_window: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    thinking: str | None = None  # off/low/medium/high/xhigh/max（None=交模型默认）


class ConversationRenameIn(BaseModel):
    """会话重命名请求。"""

    title: str


class RoleCardIn(BaseModel):
    """S48-P4 角色卡（卡片/角色卡-{name}.md）。"""

    name: str
    content: str


class ToolUpdateIn(BaseModel):
    """S49 扩展工具更新（改后自动回 draft 重新批准）。"""

    name: str | None = None
    description: str | None = None
    params_json: str | None = None
    code: str | None = None


class ToolRegisterIn(BaseModel):
    """S48-P4/B 扩展工具登记（Agent 或用户提交，人工批准后生效）。"""

    name: str  # 工具名（唯一，agent 可见）
    description: str  # 工具描述（agent 判断何时调用用）
    params_json: str = "[]"  # 参数定义 JSON 数组
    code: str  # Python 代码：def run(args: dict) -> str


class RolePlayIn(BaseModel):
    """S48-P4 角色推演请求。"""

    role: str  # 角色名（角色卡文件名 + 图谱实体）
    scenario: str  # 推演场景（自然语言）
    n: int = 4  # 推演路数（2-6）


class PlayCreateIn(BaseModel):
    """S65 互动推演：创建会话（扮演角色从场景切入）。"""

    role: str  # 扮演的角色（须有角色卡）
    seed: str  # 切入场景（自然语言）
    book_id: str = "main"
    title: str = ""
    max_depth: int = 20  # 最大推演深度（默认 20）


class PlayChooseIn(BaseModel):
    """S65 互动推演：选择候选行动（option_id 与 custom_text 二选一）。"""

    option_id: str | None = None
    custom_text: str | None = None


class PlayBranchIn(BaseModel):
    """S65 互动推演：回溯分叉（回到指定节点重新生成候选行动）。"""

    node_id: str


class UncensorIn(BaseModel):
    """S70：破限模式开关（书籍级，写作自由度：不设题材禁区）。"""

    book_id: str = "main"
    enabled: bool = True


class CodexIn(BaseModel):
    """S48-P5 代码执行请求（沙箱安全）。"""

    code: str
    timeout: float = 10.0


class IngestIn(BaseModel):
    """S48-P3 消化上传区文件。mode：auto（自动判别）/ chapters（强制拆章）/ card（强制摘要卡）。"""

    filename: str
    mode: str = "auto"
    book_id: str = "main"  # S74：上传/消化按书隔离


class UploadIn(BaseModel):
    """S48 上传存档（base64 JSON，零新依赖）。"""

    filename: str
    data_b64: str
    book_id: str = "main"  # S74：上传区按书隔离  # base64 编码的文件内容


class ToolEvent(BaseModel):
    type: str
    payload: dict[str, Any]


class ChatResponse(BaseModel):
    conversation_id: str
    text: str
    turns: list[dict[str, Any]]
    events: list[ToolEvent]
    agency_declared: int | None = None  # AI 声明的档位（用户点选确认）


class ChapterOut(BaseModel):
    id: str
    book_id: str
    title: str
    content: str
    order_index: int
    updated_at: str
    versions: list[dict[str, Any]] = []  # 版本历史（content/note/saved_at）


class ChapterCreate(BaseModel):
    """F1：手动新建章节（空正文，order_index=末尾+1）。"""

    title: str
    book_id: str = "main"
    content: str = ""


class ChapterUpdate(BaseModel):
    """F2a：稿纸编辑器保存章节内容。"""

    content: str


class ManualEntryIn(BaseModel):
    content: str
    confidence: float = 0.5
    scope: str = "project"
    category: str = "style"  # S50：collab(协作)/style(文风)/habit(习惯)


class ManualEntryPatch(BaseModel):
    content: str | None = None
    locked: bool | None = None
    category: str | None = None


class BriefIn(BaseModel):
    """S58 项目智能体简介（给 AI 和用户看的项目总览，非读者简介）。"""

    content: str
    book_id: str = "main"


class BriefGenerateIn(BaseModel):
    """S58 从现有项目数据自动生成简介草案（人工确认后生效）。"""

    book_id: str = "main"


class StoryNodeIn(BaseModel):
    """S59 叙事树节点。"""

    content: str
    book_id: str = "main"
    parent_id: str | None = None
    kind: Literal["root", "main", "anchor", "candidate", "subplot", "loop"] = "candidate"
    chosen: bool = False


class StoryThreadIn(BaseModel):
    """S59 线进度（声明/升级一条线）。"""

    name: str
    book_id: str = "main"
    content: str = ""
    progress: str = ""
    role: str = "main"  # main/subplot/parallel
    node_id: str | None = None


class StoryThreadPatch(BaseModel):
    """S59 更新线进度/完成。"""

    progress: str | None = None
    status: str | None = None  # active/done


class SignalIn(BaseModel):
    kind: str  # accepted|modified|deleted|rejected|custom|negative
    content: str
    new_content: str | None = None
    context: str = ""


class ReconcileIn(BaseModel):
    """S53c 跨会话对账请求（可选限定书）。"""

    book_id: str = "main"


class ExploreIntentIn(BaseModel):
    seed: str


class ExploreCardsIn(BaseModel):
    seed: str
    intent_confirmed: dict[str, object]


class PathExploreIn(BaseModel):
    """S67 路径探索：叙事树节点之间串联（起点 A → 终点 B 的中间事件链候选）。"""

    from_desc: str = ""  # 起点描述（from_node_id 传入时自动取节点内容；两者至少其一）
    to_desc: str  # 终点描述
    from_node_id: str | None = None  # 叙事树起点节点（内容自动带入）
    to_node_id: str | None = None  # 叙事树终点节点
    constraints: list[str] = []  # 补充设定约束（与项目档案约束合并）
    book_id: str = "main"
    n: int = 4  # 路径数（2-6）
    archive_index: int | None = None  # 选中第几条写入叙事树（1-based，显式才落树）


class ExploreArchiveIn(BaseModel):
    card: dict[str, object]
    parent_node_id: str | None = None  # S59：叙事树父节点（探索分叉从哪长出）


class ExploreDimIn(BaseModel):
    """S50：探索维度（内容化，可增删改）。"""

    name: str


class ExploreDimPatch(BaseModel):
    enabled: bool


class CheckRequest(BaseModel):
    text: str
    target: str = "当前章节"
    chapter_order: int | None = None  # 时序校验：当前章节序号（校验时空倒置）
    line: str = "main"  # S29 多线叙事：当前写作的叙事线（时序校验按线比较）


class RuleRequest(BaseModel):
    rule: str
    text: str


class GraphTypeIn(BaseModel):
    """S50：实体类型（内容化，可增删改）。"""

    name: str


class GraphTypePatch(BaseModel):
    enabled: bool


class GraphEntityIn(BaseModel):
    """S72：手动登记/覆盖实体（幂等：同名实体字段全量覆盖，不动自动统计）。"""

    name: str
    entity_type: str = "设定"
    aliases: list[str] = []
    description: str = ""
    state: str = ""
    book_id: str = "main"


class GraphEntityPatch(BaseModel):
    """S72：局部编辑实体字段（只改传入字段，不改自动统计）。"""

    aliases: list[str] | None = None
    description: str | None = None
    state: str | None = None
    entity_type: str | None = None


class GraphRelationIn(BaseModel):
    """S72：手动登记关系（两端实体须存在）。"""

    from_name: str
    to_name: str
    rel_type: str
    description: str = ""
    book_id: str = "main"


class GraphRelationPatch(BaseModel):
    rel_type: str | None = None
    description: str | None = None


class GraphEventIn(BaseModel):
    """S72：手动登记事件。"""

    chapter_ref: str
    chapter_order: int = 0
    time_point: str
    label: str
    description: str = ""
    involved: list[str] = []
    book_id: str = "main"


class GraphEventPatch(BaseModel):
    time_point: str | None = None
    label: str | None = None
    chapter_ref: str | None = None
    chapter_order: int | None = None
    description: str | None = None
    involved: list[str] | None = None


class MaterialIn(BaseModel):
    text: str
    title: str = ""
    purpose: str = "fact"  # style|fact|both


class GraphExtractIn(BaseModel):
    chapter_ref: str
    text: str


class ReviewPanelRequest(BaseModel):
    """S65：拟人化评审团请求。chapter_ref 与 text 二选一（ref 优先）。"""

    chapter_ref: str = ""  # 章节标题（从 chapters 取正文）
    text: str = ""  # 直接评审文本
    book_id: str = "main"
    reviewer_ids: list[str] = []  # 空 = 全部激活评审员
    with_check: bool = True  # 注入 check 硬伤清单（逻辑审校用）
    with_foreshadow: bool = True  # 注入关键点图谱（伏笔审计员用）


class AgencyIn(BaseModel):
    level: int | None = None  # 兼容旧调用：排序位数字（0 起）
    level_id: str | None = None  # S35：档位记录 id（优先）


class AgencyLevelIn(BaseModel):
    """S35：新增/修改自定义档位。"""

    name: str
    description: str = ""
    temperature: float = 0.7


class AgencyGenerateIn(BaseModel):
    """S61 L3：自然语言描述 → 档位候选（人工确认后 /api/agency/add 生效）。"""

    description: str
    n: int = 3


class ManualDecayIn(BaseModel):
    """S61：活跃度衰减参数（DESIGN §12.18 元数据收敛）。"""

    days_high: int = 30  # high → medium 阈值（天）
    days_medium: int = 90  # medium → low 阈值（天）


class BatchRewriteIn(BaseModel):
    """S40：批量改写（全书变换）——多章统一指令改写。"""

    chapter_ids: list[str]
    instruction: str


class BatchReviewIn(BaseModel):
    """S40：批量审读——多章检测网审读。"""

    chapter_ids: list[str]


class WorldSettingIn(BaseModel):
    """S41：设定档条目。"""

    content: str
    category: str = "世界观"
    name: str = ""
    book_id: str = "main"  # S74：设定档按书隔离（正典是书级内容）
    # S83 约束机制：is_constraint=1 为约束条目（写作/探索时注入）；
    # entities=逗号分隔关联实体名（空=全局约束）
    is_constraint: int = 0
    entities: str = ""


class WorldSettingPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    name: str | None = None
    is_constraint: int | None = None
    entities: str | None = None


class WorldSettingExtractIn(BaseModel):
    """S42：从图谱提炼设定草案（LLM 生成候选，作者逐条确认）。"""

    book_id: str = "main"


class SettingCategoryIn(BaseModel):
    """S50：设定档类别（内容化，可增删改）。"""

    name: str


class SettingCategoryPatch(BaseModel):
    enabled: bool


class WritingSkillIn(BaseModel):
    """S50：叙事技巧（skill 式内容载体）。"""

    name: str
    description: str = ""
    content: str
    example: str = ""  # 具体情形案例（提升文笔：样例比抽象指令有效）
    tags: str = ""  # 场景标签（逗号分隔，支撑按需选取）
    target: str = "writing"  # S57：writing(写作调用)/main(主循环)/both
    enabled: bool = True


class WritingSkillPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    example: str | None = None
    tags: str | None = None
    target: str | None = None
    enabled: bool | None = None


class SkillGenerateIn(BaseModel):
    """S54/S58：生成 skill 候选（人工确认后入库）。"""

    source_text: str = ""  # 待提炼正文（导入的小说/片段，真实原文；与 material_id 二选一）
    material_id: str | None = None  # S72：从资料库取原文（文风参考书 → skill 提炼链路）
    hint: str = ""  # 可选指引（如"侧重打斗文风"/"侧重爽文节奏"）
    max_items: int = 5
    mode: str = "writing"  # S58：writing（文风/叙事技法）/ main（类型/结构组织指导）


class TemplateGenerateIn(BaseModel):
    """S69：从书提炼剧情模式模板候选（人工确认后走 /api/templates/import 入库）。

    与 skill 生成的区别：输出模板四要素（粒度/位置/功能/可变参数），
    输入应为多章/全书片段（跨章结构归纳，单章提不到剧情模式）。
    """

    source_text: str  # 多章/全书片段（真实原文）
    hint: str = ""  # 可选指引（如"侧重悬疑递进"）
    max_items: int = 5


class ChapterPatchIn(BaseModel):
    """S44：定点编辑操作列表。"""

    operations: list[dict[str, Any]]


class ImpactIn(BaseModel):
    """S45：影响分析（连锁修改）——改某章（涉及实体）→ 受影响下游章节。"""

    chapter_order: int
    entities: list[str] | None = None


class WorkflowIn(BaseModel):
    """S59：工作流定义写入（模板入库）。模块级（S13 坑：函数内定义 ForwardRef 失败）。"""

    name: str
    description: str = ""
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]] = []
    layout: dict[str, dict[str, float]] = {}  # S76：画布节点坐标（可选，空=自动布局）


class WorkflowGenerateIn(BaseModel):
    """S59：AI 生成工作流（描述目标 → 草稿，人工确认转正）。"""

    goal: str


class WorkflowRunIn(BaseModel):
    """S59：运行工作流（绑定书，快照冻结）。"""

    book_id: str = "main"


class ChapterPlanIn(BaseModel):
    """S46：剧情计划条目。"""

    chapter_order: int
    title: str = ""
    content: str = ""


class StoryLayoutPos(BaseModel):
    """S76：叙事树单节点手动坐标。"""

    node_id: str
    x: float
    y: float


class StoryLayoutIn(BaseModel):
    """S76：叙事树布局批量保存。"""

    book_id: str = "main"
    positions: list[StoryLayoutPos]


class ChapterPlanPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None


class BiasIn(BaseModel):
    content: str
    source: str = "ai"


class DirectionIn(BaseModel):
    prompt: str
    context: str = ""  # 可选：章节摘要/设定约束


class CandidatesIn(BaseModel):
    prompt: str
    context: str = ""
    n: int = 3


class RewriteIn(BaseModel):
    text: str
    mode: str = "balanced"  # subtle|balanced|bold


class WrapupIn(BaseModel):
    chapter_id: str


class TemplateIn(BaseModel):
    name: str
    description: str
    granularity: str = "章"
    position: str = "发展"
    function: str = "主线"
    params: list[str] = []


class PlotIn(BaseModel):
    settings: str = ""  # 作品设定/种子（可选，缺省用已写章节）


class PlotPatchIn(BaseModel):
    status: str | None = None  # open|resolved
    attention: str | None = None  # care|ignore（用户标注在意/不需要）
    priority: str | None = None  # S31: must（剧情钩子，必须回收）| soft（细节线索）
    resolved_chapter: str | None = None  # S31: 回收章节


class PlotItemIn(BaseModel):
    """S31：主动登记一个关键点/伏笔（作者/AI 声明，非 LLM 生成）。"""

    content: str = Field(..., min_length=1)
    category: str = "伏笔"
    chapter_ref: str = ""
    priority: str = "soft"  # must=剧情钩子（作者承诺必须回收）/ soft=细节线索
    planted_order: int = 0  # S31 老龄化：登记时的章节序号（开放时长 = 当前章 - planted_order）


class CancelIn(BaseModel):
    conversation_id: str | None = None  # 空=取消最近活跃会话（新会话 id 客户端未知）


class SteerIn(BaseModel):
    conversation_id: str  # 目标会话（必须正在运行才能插话）
    message: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# 应用装配


# 默认写作系统提示（真实写作指令）
DEFAULT_SYSTEM = (
    "你是 AnySpark 小说写作智能体。你要直接写故事正文。"
    "写正文前用 list_chapters 查看章节列表；如需保持连贯，"
    "只需 read 最近的 1-2 章，不要读取全部历史章节"
    "（更早的内容由【已固化事实】注入提供）。"
    "若章节内容已在本轮对话历史或【已固化事实】注入中，直接基于它们，不要重复读取。"
    "写正文可用 write_chapter 保存。"
    "正文要具体、有画面感，杜绝空泛总结。"
    # S56（C 架构）：意图模式——主循环决策+精选参考，正文由干净写作调用生成（防累积毒化）
    "长会话/连续写作时优先用意图模式：先确认本章要写什么（场景/人物状态/氛围/推进点），"
    "把需要的设定事实或原文片段摘录进 references（原样引用，不要概括），"
    "然后调 write_chapter(title, intent=…, references=…)，正文由写作引擎生成。"
    # S43：DEFAULT_SYSTEM 回归极简（只留行为底线）——写作技巧类规则已抽为内容载体
    # （WritingSkill：镜头感/对白机锋/节奏控制等叙事技巧，见【叙事技巧】注入块），不再堆行为守则
    "首要目标是把正文写出来并落盘，不要为了准备而反复调用与当前任务无关的工具。"
    "仅当用户给的任务方向不明确（种子含糊、无明确脉络、不知往哪个方向写）时，"
    "先调用 explore_direction 生成方向建议并在回复中列出询问用户选择；方向明确时直接写。"
    # S62b：一致性护栏（只防与已写内容的冲突，不限制叙事手法）——
    # 切视角/跳场景/倒叙/留白是合法表达，自由发挥；只约束时间点与命名两件事
    "【一致性】只约束与已写内容的冲突，不限制叙事手法（切视角/跳场景/倒叙自由）："
    "时间：不虚构可能与全文冲突的具体日期；确需具体日期（倒计时/跨章线索）时"
    "先 search_chapters 检索'几月/几日'类引用匹配，冲突则用模糊表达（'几天后'）。"
    "命名：写到已出现的人物/地点时，用其既有名称（不确定时 graph_query 确认，"
    "图谱为准）——同一地点不因视角/场合换名。场景切换/视角切换自由，无需交代。"
)


def _sse_frame(event: str, data: dict[str, Any]) -> str:
    """SSE 帧：event: <type>\ndata: <json>\n\n（core 事件协议 → 传输层）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _now_iso_rec() -> str:

    return datetime.now(UTC).isoformat()
