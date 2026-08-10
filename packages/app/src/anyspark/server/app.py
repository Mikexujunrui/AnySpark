"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from anyspark.align import (
    AgencyStore,
    BiasStore,
    ManualEntry,
    ManualStore,
    MemoryStore,
    MindPlanner,
    PreferenceExtractor,
    SessionSummarizer,
    SignalCollector,
    SignalStore,
    SkillGenerator,
    StoryPlanStore,
    StoryThreadStore,
    StoryTreeStore,
    WorldSettingStore,
    WritingSkillStore,
    build_agency_block,
    build_agency_gen_prompt,
    build_agency_suggest_prompt,
    build_learning_review_prompt,
    build_reconcile_prompt,
    parse_agency_declaration,
    parse_agency_gen_result,
    parse_agency_suggest_result,
    parse_learning_review_result,
    parse_reconcile_result,
    render_plan,
    render_settings,
    render_skill_index,
)
from anyspark.check import compile_rule, compile_with_model, run_review
from anyspark.core import (
    Agent,
    CancellationToken,
    Conversation,
    Message,
    Model,
    RetryingModel,
    ToolRegistry,
)
from anyspark.explore import (
    DimensionStore,
    DirectionCard,
    IntentUnderstander,
    ProjectArchive,
    run_exploration,
    run_roleplay,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.models import DEFAULT_BASE_URL, DeepSeekModel
from anyspark.models.registry import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ModelConfig,
    ModelProvider,
    ModelRegistry,
    slugify,
)
from anyspark.play import PlayEngine, PlayStore
from anyspark.review import ReviewPanel
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.recorder import RunRecorder
from anyspark.server.stats import compute_stats
from anyspark.server.toolkit import ToolContext, build_toolkit
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
)
from anyspark.server.tools_writing import UNCENSORED_PROMPT
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
    ExternalLibrary,
    MaterialDigestor,
    MaterialStore,
    PlotGenerator,
    PlotResolver,
    PlotStore,
)
from anyspark.workflow import (
    NodeResult,
    RunContext,
    WorkflowDef,
    WorkflowEngine,
    WorkflowGenerator,
    WorkflowStore,
    wait_approval,
)

# 数据根：项目 data/（gitignored，绝不入库）
PROJECT_ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "anyspark.db"

# S55 #3 注入块分层缓存：stable 块（跨请求不变）按签名缓存，volatile 块每次组装。
# 签名=底层数据内容（任何增删改 → 签名变 → 缓存失效），避免长会话重复渲染。
_skill_cache: dict[str, str] = {}  # 签名 → 索引块（S60：只存索引，内容靠 skill_lookup 按需）

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


# ---------------------------------------------------------------------------
# Pydantic 请求/响应模型
# ---------------------------------------------------------------------------
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


class UploadIn(BaseModel):
    """S48 上传存档（base64 JSON，零新依赖）。"""

    filename: str
    data_b64: str  # base64 编码的文件内容


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


# 图谱实体 CRUD（前端手动维护）
class EntityCreateIn(BaseModel):
    name: str
    entity_type: str
    aliases: list[str] = []
    description: str = ""


class EntityPatchIn(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    aliases: list[str] | None = None
    description: str | None = None
    state: str | None = None


# 图谱关系 CRUD
class RelationCreateIn(BaseModel):
    from_name: str
    to_name: str
    rel_type: str
    description: str = ""
    chapter_ref: str = ""


class RelationPatchIn(BaseModel):
    rel_type: str | None = None
    description: str | None = None


# 图谱事件 CRUD
class EventCreateIn(BaseModel):
    label: str
    time_point: str = ""
    chapter_ref: str = ""
    chapter_order: int = 0
    description: str = ""
    involved: list[str] = []


class EventPatchIn(BaseModel):
    label: str | None = None
    time_point: str | None = None
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


class WorldSettingPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    name: str | None = None


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

    source_text: str  # 待提炼正文（导入的小说/片段，真实原文）
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
# ---------------------------------------------------------------------------
def _now_iso_rec() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def build_app(
    model: Model | None = None,
    db_path: str | Path | None = None,
    workspace: Workspace | None = None,
) -> FastAPI:
    """装配后端应用。

    - model: 真实 DeepSeekModel（默认）；测试可注入 fake model（实现 core.Model 协议）
    - db_path: 默认 data/anyspark.db；测试可注入临时路径
    - workspace: S48 工作区（默认 data/workspace）；测试可注入临时路径隔离
    """
    load_dotenv(PROJECT_ROOT / ".env")
    setup_logging()

    real_db = db_path or DB_PATH
    store = SqliteConversationStore(real_db)
    # S48 工作区化：每项目一路径（上传/章节/卡片），章节 md 文件为权威
    # 默认与 db 配对隔离（防测试污染全局）：未显式注入时——
    #   默认 db → data/workspace；临时 db → db 同目录 workspace；:memory: → 临时目录
    if workspace is None:
        if real_db == ":memory:":
            import tempfile

            workspace = Workspace(root=Path(tempfile.mkdtemp()))
        elif db_path is None:
            workspace = Workspace()
        else:
            workspace = Workspace(root=Path(real_db).parent / "workspace")
    chapters = ChapterStore(real_db)
    ext_tools = ExtensionToolStore(real_db)  # S48-P4/B：扩展工具注册表（人工批准生效）
    # S49 会话运行记录：与 db 配对隔离（同 workspace 逻辑——防测试污染全局 records）
    if real_db == ":memory:":
        import tempfile as _tf

        recorder = RunRecorder(root=Path(_tf.mkdtemp()))
    elif db_path is None:
        recorder = RunRecorder()
    else:
        recorder = RunRecorder(root=Path(real_db).parent / "records")
    manual = ManualStore(real_db)
    signals = SignalStore(real_db)
    archive = ProjectArchive(real_db)
    dim_store = DimensionStore(real_db)  # S50 探索维度内容化（可增删改）
    materials = MaterialStore(real_db)
    templates_external = ExternalLibrary(real_db)
    plots = PlotStore(real_db)
    # 活跃会话的取消令牌（S21：/api/chat/cancel 可中断正在跑的 Agent）
    _active_tokens: dict[str, CancellationToken] = {}
    # 活跃会话的 Agent 实例（S25：/api/chat/steer 运行中插话用）——chat/chat_stream
    # 启动时注册、结束时注销；steer 端点据此把插话消息投入 steer_queue。
    _active_agents: dict[str, Agent] = {}
    _active_lock: threading.Lock = threading.Lock()

    # 后台任务队列 + 独立 worker（S21 修 BackgroundTasks 共享线程池排队缺陷）：
    # 图谱抽取/伏笔回收/信号提炼不占请求线程池，请求立即返回、后台串行处理。
    # 任务负载类型（S28 扩展）：("chapter", title, content, order) 图谱抽取/伏笔回收；
    # ("refine",) 信号→说明书提炼；("batch_rewrite", batch_id, ids, instruction) 批量改写；
    # ("batch_review", batch_id, ids) 批量审读（S40）。
    @dataclass
    class BgTask:
        """后台任务（S62：取代元组魔法派发——kind 字段 + 类型化负载，新增任务类型只加一条）。"""

        kind: str  # chapter|refine|skill_drafts|summarize|batch_rewrite|batch_review
        title: str = ""
        content: str = ""
        order: int = 0
        line: str = "main"
        conv_id: str = ""
        batch_id: str = ""
        ids: list[str] = field(default_factory=list)
        instruction: str = ""

    _bg_queue: queue.Queue[BgTask] = queue.Queue()  # 后台任务队列（S28/S40）
    # S40 批量任务状态（内存会话级）：id → {status, done, total, results}
    _batches: dict[str, dict[str, Any]] = {}
    _batch_lock: threading.Lock = threading.Lock()

    def _run_batch_rewrite(batch_id: str, chapter_ids: list[str], instruction: str) -> None:
        """批量改写：逐章 LLM 按指令改写 → upsert（覆盖前旧版进版本历史）。"""
        batch = _batches.get(batch_id)
        if not batch:
            return
        for cid in chapter_ids:
            try:
                assert model is not None  # 真实装配必有模型
                ch = chapters.get(cid)
                if ch is None:
                    batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
                else:
                    prompt = (
                        "按用户指令改写以下章节。保持剧情走向/人物/设定/时间线一致，"
                        "只按指令调整（风格/情节/表达）。直接输出改写后的完整正文。\n"
                        f"【指令】{instruction}\n【原章】\n{ch.content}\n【改写后正文】"
                    )
                    out = model.respond([Message(role="user", content=prompt)], [])
                    new_text = (out.text or "").strip()
                    if new_text:
                        chapters.upsert(
                            "main", ch.title, new_text, ch.order_index, ch.narrative_line
                        )
                        batch["results"].append(
                            {"id": cid, "title": ch.title, "ok": True, "chars": len(new_text)}
                        )
                    else:
                        batch["results"].append(
                            {"id": cid, "title": ch.title, "ok": False, "error": "空输出"}
                        )
            except Exception as exc:
                batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
            batch["done"] += 1
        batch["status"] = "done"

    def _run_batch_review(batch_id: str, chapter_ids: list[str]) -> None:
        """批量审读：逐章检测网审读，汇总报告。"""
        batch = _batches.get(batch_id)
        if not batch:
            return
        for cid in chapter_ids:
            try:
                ch = chapters.get(cid)
                if ch is None:
                    batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
                else:
                    report = run_review(model, ch.title, ch.content[:20000])
                    batch["results"].append(
                        {
                            "id": cid,
                            "title": ch.title,
                            "ok": True,
                            "hard": report.hard_count,
                            "report": report.render(),
                        }
                    )
            except Exception as exc:
                batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
            batch["done"] += 1
        batch["status"] = "done"

    def _bg_worker() -> None:
        while True:
            try:
                task = _bg_queue.get()
                if task.kind == "chapter":
                    _extract_chapter("main", task.title, task.content, task.order, task.line)
                elif task.kind == "refine":
                    _refine_from_signals()
                elif task.kind == "skill_drafts":
                    _refine_skill_drafts()
                elif task.kind == "summarize":
                    _summarize_conversation(task.conv_id)
                elif task.kind == "batch_rewrite":
                    _run_batch_rewrite(task.batch_id, task.ids, task.instruction)
                elif task.kind == "batch_review":
                    _run_batch_review(task.batch_id, task.ids)
                else:
                    logger.warning("后台任务未知 kind: %r", getattr(task, "kind", task))
            except Exception as exc:
                logger.warning("后台任务异常: %s", exc)
            finally:
                _bg_queue.task_done()

    threading.Thread(target=_bg_worker, daemon=True).start()

    def _refine_from_signals() -> None:
        """S28：信号 → 偏好提炼 → 说明书（后台异步，不阻塞用户操作）。

        修复对齐闭环缺口：此前 /api/signals 只记录信号，说明书永不自动更新
        （PreferenceExtractor 存在但从未在 API 层接线）——用户操作无法变成
        写作约束，T7"修改率↓/说明书累积"的机制前提缺失。
        """
        try:
            recent = signals.recent(limit=20)
            if not recent:
                return
            # 最近对话（任意会话，取最近 10 条）作为提炼上下文
            dialogue = store.recent_messages(10)
            entries = preference_extractor.extract(dialogue, recent, max_items=3)
            existing = {e.content for e in manual.list("project", "main")}
            added = 0
            for e in entries:
                if e.content in existing:
                    continue
                # S55 合并式新增：同主题条目合并（治碎片），不重复堆窄条目
                _, did_merge = manual.merge_add(e)
                if not did_merge:
                    added += 1
            if added:
                logger.info("信号提炼: +%d 条新说明书条目", added)
        except Exception as exc:
            logger.warning("信号提炼失败(不影响主链路): %s", exc)

    def _refine_skill_drafts() -> None:
        """S54 B/C：心智联动 + 信号驱动 → 生成 skill 候选草稿（人工确认生效）。

        B 心智联动：manual 有 style 偏好（如"喜欢白话文风"）但没有对应 skill →
          用偏好作 hint 调 SkillGenerator 生成候选草稿。
        C 信号驱动：信号/对话里体现的稳定写法 → 提炼成候选草稿。

        产出只进 skill_drafts（未生效），人工确认后转正进 writing_skills——
        对齐 tools_extensions 的"人工批准生效"哲学（S32 实证：错误内容进上下文污染主链路）。
        """
        try:
            # 素材：style 偏好条目 + 最近修改/接受信号（体现用户认可写法）
            manual_entries = manual.list("project", "main")
            style_prefs = [e.content for e in manual_entries if e.category == "style"][:3]
            recent = signals.recent(limit=20)
            signal_texts = [s.content for s in recent if s.kind in ("accepted", "modified")][:5]
            source_material = "\n".join(style_prefs + signal_texts).strip()
            if not source_material:
                return
            hint = ""
            if style_prefs:
                hint = f"用户文风偏好：{'；'.join(style_prefs)}"
            candidates = skill_generator.generate(source_material, hint, max_items=3)
            added = 0
            for c in candidates:
                r = skills.add_draft(
                    name=c["name"],
                    description=c["description"],
                    content=c["content"],
                    example=c["example"],
                    tags=c["tags"],
                    target=c.get("target", "writing"),  # S57
                    source="mental",  # mental(心智联动) 或 signal(信号驱动) 统一落草稿
                )
                if r:
                    added += 1
            if added:
                logger.info("skill 草稿提炼: +%d 条（待确认）", added)
        except Exception as exc:
            logger.warning("skill 草稿提炼失败(不影响主链路): %s", exc)

    def _summarize_conversation(conv_id: str) -> None:
        """S53c ② 归档后分析：会话结束后台把对话摘要成场景记忆（双轨提炼之摘要器轨）。

        承担跨会话延续性（进行到哪/做过哪些决定），供下轮会话开头展示（④）。
        仅对"有实质内容的会话"归档（用户消息累计 ≥40 字），避免短测试/琐碎对话
        烧 token；失败不阻塞主链路。
        """
        try:
            msgs = store.messages(conv_id)
            user_chars = sum(len(m.content or "") for m in msgs if m.role == "user")
            if len(msgs) < 3 or user_chars < 40:  # 空会话/琐碎对话不归档
                return
            summarizer.summarize(msgs, book_id="main")
            logger.info("会话归档摘要: conv=%s 消息%d 条", conv_id, len(msgs))
        except Exception as exc:
            logger.warning("会话归档摘要失败(不影响主链路): %s", exc)

    mind_planner = MindPlanner(manual)  # S50 心智模型=会话规划器（不从写作循环注入）
    signal_collector = SignalCollector(signals)
    # S47 运行时模型：注册表（持久化多配置）+ 动态 Provider——
    # 默认装配 RetryingModel(ModelProvider(registry))，所有组件跟随当前激活配置；
    # 测试可注入 fake model（实现 core Model 协议），走共享分支不受影响。
    # 注意：必须在任何依赖 model 的组件（summarizer/plot/提炼器等）之前初始化。
    models = ModelRegistry(real_db)
    provider = ModelProvider(models)
    model = model or RetryingModel(provider)
    memory_store = MemoryStore(real_db)  # S53c ② 场景记忆（项目档案延续性层）
    story_tree = StoryTreeStore(real_db)  # S59 叙事树（分叉路径模型）
    story_threads = StoryThreadStore(real_db)  # S59 线进度（映射锚）
    summarizer = SessionSummarizer(model, memory_store)  # ② 归档摘要器（真实 LLM）
    plot_generator = PlotGenerator(model)  # 依赖 model，须在其初始化之后
    plot_resolver = PlotResolver(model)  # 伏笔自动回收（S17：章节落盘后台识别揭开）
    preference_extractor = PreferenceExtractor(model)  # S28：信号→说明书提炼（后台）
    skill_generator = SkillGenerator(model)  # S54：文风提炼→skill 候选（人工确认生效）
    # 知识图谱（S7：AI 事实源）
    graph = GraphStore(real_db)
    graph_extractor = GraphExtractor(model, types=graph.types_for("main"))  # S50：类型集内容化
    graph_injector = GraphInjector(graph)
    graph_verifier = GraphVerifier(graph)
    # token 预算 + 两阶段压缩（S8：长书上下文刚需；S26：预算按模型窗口配置——
    # 窗口 64K 时预算 ~45K，不再 12K 硬编码导致长书频繁压缩）
    _window = getattr(getattr(model, "inner", model), "context_window", 65536)
    budget = TokenBudget(
        budget=int(_window * 0.7),
        summarize=make_summarizer(model),
    )
    # 能动性协议（机制 2）+ AI 倾向档案（S9）
    agency = AgencyStore(real_db)
    bias = BiasStore(real_db)
    settings = WorldSettingStore(real_db)  # S41 设定档（作者正典）
    skills = WritingSkillStore(real_db)  # S50 叙事技巧（skill 式内容载体）
    plans = StoryPlanStore(real_db)  # S46 剧情计划（计划→执行）

    # S59 工作流扩展包（可选增强，默认关）：结构化流程（顺序/分支/循环）+
    # 断点恢复 + AI 生成（草稿→人工确认转正）。runner 由组合根注入：
    # agent 节点=干净单次 LLM 调用；script 节点=确定性函数（read/review）；
    # approval=等待人工。
    workflow_store = WorkflowStore(real_db)
    workflow_generator = WorkflowGenerator(model)
    # S65 互动推演（独立扩展包 anyspark-play）：扮演角色多轮选择推进的推演树
    # S65：拟人化评审团面板（系统评审员随包分发 + 用户自定义覆盖 data/reviewers/）
    review_panel = ReviewPanel()
    try:
        review_panel.add_dir(DATA_DIR / "reviewers")
    except Exception as _rpe:  # 用户目录损坏不影响服务启动
        logger.warning("加载用户评审员失败: %s", _rpe)
    play_store = PlayStore(real_db)

    def _wf_run_agent(ctx: RunContext, node: Any) -> NodeResult:
        """agent 节点：干净单次 LLM 调用（无对话历史/工具记录——对齐 S56 干净写作）。

        变量插值：instruction/system_prompt 中的 {{var}} 从上游节点输出解析
        （如 {{chapter_text}} = 前序 read_chapter 脚本的产出）——真实链路暴露的
        接缝：AI 生成的流程若不插值，agent 拿不到章节内容。
        """
        instruction = _wf_resolve(str(node.params.get("instruction") or ""), ctx)
        system = _wf_resolve(str(node.params.get("system_prompt") or ""), ctx)
        # 便捷注入：params.chapter_title 指定章节时自动附带正文
        chapter_title = str(node.params.get("chapter_title") or "")
        if chapter_title:
            ch = next(
                (c for c in chapters.list_by_book(ctx.book_id) if c.title == chapter_title),
                None,
            )
            if ch is not None:
                instruction = f"【章节正文】\n{ch.content[:8000]}\n\n{instruction}"
        messages: list[Any] = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=instruction))
        out = model.respond(messages, [])
        text = (out.text or "").strip()
        if not text:
            return NodeResult(error="agent 节点空输出")
        usage = getattr(out, "usage", None)
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return NodeResult(output=text, token_usage=tokens)

    def _wf_resolve(text: str, ctx: RunContext) -> str:
        """把 {{var}} 占位符替换为上游节点输出（缺失保留原样）。"""
        import re

        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            val = ctx.results.get(key, "")
            return str(val) if val else f"{{{{{key}}}}}"

        return re.sub(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}", _repl, text)

    def _wf_run_script(ctx: RunContext, node: Any) -> NodeResult:
        """script 节点：确定性函数（内置白名单）。"""
        fn = str(node.params.get("function") or "")
        if fn == "noop":
            # 无操作（AI 生成流程常用来做循环体出口占位）
            return NodeResult(output=str(node.params.get("output_key") or "done"))
        if fn == "read_chapter":
            title = str(node.params.get("chapter_title") or "")
            chs = chapters.list_by_book(ctx.book_id)
            ch = next((c for c in chs if c.title == title), None)
            if ch is None:
                # 模糊匹配（AI 生成标题可能不精确——真实链路暴露）：
                # ① 双向包含 ② 提取双方"第X章"片段做章号匹配
                def _chapter_no(t: str) -> str:
                    import re as _re

                    m = _re.search(r"第\s*([0-9一二三四五六七八九十百]+)\s*章", t)
                    return m.group(1) if m else ""

                t_no = _chapter_no(title)
                for c in chs:
                    if title and (title in c.title or c.title in title):
                        ch = c
                        break
                    if t_no and _chapter_no(c.title) == t_no:
                        ch = c
                        break
            if ch is None:
                return NodeResult(
                    error=f"章节不存在: {title}（可用章节: "
                    + ", ".join(c.title for c in chs[:8])
                    + "）"
                )
            return NodeResult(output=ch.content)
        if fn == "review_chapter":
            title = str(node.params.get("chapter_title") or "")
            ch = next((c for c in chapters.list_by_book(ctx.book_id) if c.title == title), None)
            if ch is None:
                return NodeResult(error=f"章节不存在: {title}")
            report = run_review(model, ch.title, ch.content[:20000])
            return NodeResult(output=f"硬伤数: {report.hard_count}\n" + report.render())
        if fn == "list_chapters":
            chs = chapters.list_by_book(ctx.book_id)
            if not chs:
                return NodeResult(output="（无章节）")
            return NodeResult(output="\n".join(f"{c.order_index}. {c.title}" for c in chs))
        if fn == "write_chapter":
            """写回章节：参数 chapter_title + content（或 {{var}} 引用上游改写结果）。

            content 缺失时取 params.text_key（缺省 'rewritten'）对应的上游输出——
            AI 生成的流程常用：改写 agent 输出 rewritten → write_chapter 脚本落盘。
            """
            title = str(node.params.get("chapter_title") or "")
            content = str(node.params.get("content") or "")
            if not content:
                text_key = str(node.params.get("text_key") or "rewritten")
                content = str(ctx.results.get(text_key, ""))
            if not title:
                return NodeResult(error="write_chapter 缺 chapter_title")
            if not content.strip():
                return NodeResult(error="write_chapter 无内容（检查 text_key 上游输出）")
            try:
                chs = chapters.list_by_book(ctx.book_id)
                ch = next((c for c in chs if c.title == title), None)
                if ch is None:
                    order = len(chs) + 1
                    chapters.upsert(ctx.book_id, title, content, order)
                else:
                    chapters.upsert(ctx.book_id, title, content, ch.order_index)
                # 双写落盘（工作区 md 权威，与 write_chapter 工具一致）
                try:
                    order = ch.order_index if ch else (len(chs) + 1)
                    workspace.write_chapter(ctx.book_id, order, title, content)
                except Exception:
                    pass  # 库镜像已更新，落盘失败不阻断
                return NodeResult(output=f"已写回章节: {title}")
            except Exception as exc:
                return NodeResult(error=f"写回失败: {exc}")
        return NodeResult(error=f"未注册的 script 函数: {fn}")

    def _wf_run_approval(ctx: RunContext, node: Any) -> NodeResult:
        """approval 节点：抛等待信号（任务置 waiting_approval，人工 approve 后续跑）。"""
        wait_approval()
        return NodeResult(output="approved")

    def _wf_runner(ctx: RunContext, node: Any) -> NodeResult:
        if node.kind == "agent":
            return _wf_run_agent(ctx, node)
        if node.kind == "script":
            return _wf_run_script(ctx, node)
        if node.kind == "approval":
            return _wf_run_approval(ctx, node)
        return NodeResult(error=f"未知节点类型: {node.kind}")

    def _wf_judge(prompt: str, ctx: RunContext) -> bool:
        """model 型条件：自然语言问题 → 模型判断 yes/no。

        真实链路暴露：模型答"否/不通过"时旧逻辑误判。强制输出 是/否 首字判定，
        明确否定词优先级（避免"没有硬伤"被"有"字误判）。
        """
        out = model.respond(
            [
                Message(
                    role="system",
                    content="你只判断一个条件是否成立。必须严格以单个字'是'或'否'开头回答，不要解释。",
                ),
                Message(role="user", content=prompt),
            ],
            [],
        )
        text = (out.text or "").strip()
        if not text:
            return False
        first = text[0]
        # 否定词优先（'不'/'没'/'无'/'否' 开头 → False；'是'/'通' 开头 → True）
        if first in ("不", "没", "无", "否", "非"):
            return False
        if first in ("是", "通", "可", "同", "y", "Y", "t", "T"):
            return True
        # 兜底：整句包含强肯定词且无否定词
        lower = text.lower()
        has_pos = any(w in lower for w in ("yes", "true", "通过", "可以", "同意"))
        has_neg = any(w in lower for w in ("no", "false", "不是", "不通过", "没有", "无法"))
        return has_pos and not has_neg

    workflow_engine = WorkflowEngine(workflow_store, _wf_runner, model_judge=_wf_judge)
    # S65：play 引擎（树存储 + LLM 生成；角色卡加载复用 explore load_role_card）
    play_engine = PlayEngine(play_store, model, workspace, graph)

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发期；前端 Vite dev server 在此端口
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        """全局兜底：未捕获异常打 ERROR 日志（含 traceback）再返回 500——
        此前 _make_agent 等 try 块外的异常静默 500 零日志，排查无据。"""
        logger.exception("未捕获异常: %s %s", request.method, request.url.path, exc_info=exc)
        return Response(status_code=500, content="Internal Server Error")

    def _make_agent(
        system_prompt: str,
        temperature: float,
        book_id: str = "main",
        agency_level: int | None = None,
        enable_search: bool = False,
        enable_extras: bool = False,
        enable_domain: bool = True,
        enable_codex: bool = False,
        enable_workflow: bool = False,
        enable_play: bool = False,
        skip_inject: set[str] | None = None,
        context_mode: str = "auto",
        model_id: str | None = None,
        thinking: str | None = None,
        context: str = "",
    ) -> Agent:
        # 心智规划提前（S56 C 架构）：style_prefs 供写作工具意图模式选文笔 skill
        # S61：context=本轮用户意图，心智块渐进式披露按相关动态选取
        if agency_level is None:
            session_plan = mind_planner.plan(
                book_id, base_agency=agency.get_current(book_id).order, context=context
            )
        else:
            session_plan = mind_planner.plan(book_id, context=context)
        # 工具装配（S52 抽出为独立模块 toolkit.build_toolkit——组合根接口化，
        # 与 HTTP 编排解耦；S62：依赖收敛为 ToolContext 单对象，签名稳定）
        registry = build_toolkit(
            ToolRegistry(),
            ToolContext(
                chapters=chapters,
                workspace=workspace,
                model=model,
                graph=graph,
                plots=plots,
                plans=plans,
                settings=settings,
                materials=materials,
                ext_tools=ext_tools,
                dim_store=dim_store,
                manual=manual,
                skills_store=skills,
                style_prefs=session_plan.style_prefs,
                workflow_store=workflow_store,
                workflow_engine=workflow_engine,
                workflow_generator=workflow_generator,
                play_engine=play_engine,
                review_panel=review_panel,
                # S68：探索注入真实模板库（L2+L3 合并，agent 的 explore_direction 消费）
                templates=[f"{t.name}：{t.description}" for t in templates_external.all()[:12]],
            ),
            enable_domain=enable_domain,
            enable_codex=enable_codex,
            enable_extras=enable_extras,
            enable_search=enable_search,
            # S59：工作流 agent 工具（默认关，enable_workflow 点亮）
            enable_workflow=enable_workflow,
            # S65：互动推演 agent 工具（默认关，enable_play 点亮）
            enable_play=enable_play,
        )
        # 能动级别：显式传入 > 心智规划建议 > 已存档位（S35：档位记录，温度入档）
        # S50：心智模型=会话规划器——S62 修正：启发式档位推断**不自动应用**
        # （对齐 S61"建议不自动应用，用户主权"；启发式关键词猜意图会误判，
        # 见 S61 实测"不要反复确认"的"确认"抵消"直接写"）。用户未显式指定时
        # 一律用已存档位；推断结果只经 /api/mind/agency-suggest 呈现供用户采纳。
        if agency_level is None:
            current = agency.get_current(book_id)
        else:
            levels = agency.list_levels()
            current = next(
                (lv for lv in levels if lv.order == int(agency_level)),
                agency.get_level(f"default-{int(agency_level)}") or agency.get_current(book_id),
            )
        eff_temp = current.temperature if temperature == 0.7 else temperature
        # S21 流式核心：不再构造 stream 模型——Agent 循环内部检测 respond_stream 流式；
        # 温度映射时重建模型（档位低=精确执行温度低）；测试 fake 走共享 model
        base_model = getattr(model, "inner", model)
        m: Model
        if model_id:
            # S47 请求级指定模型：按该配置构造（显式指定 > 当前激活）
            cfg = models.get(model_id)
            if cfg is None:
                raise ValueError(f"模型配置不存在: {model_id}")
            m = RetryingModel(
                DeepSeekModel(
                    base_url=cfg.base_url,
                    api_key=cfg.resolved_api_key(),
                    model=cfg.model,
                    temperature=eff_temp,
                    max_tokens=cfg.max_tokens,
                    context_window=cfg.context_window,
                    thinking=cfg.thinking if thinking is None else thinking,
                )
            )
        elif isinstance(base_model, ModelProvider):
            # S47 运行时模型：按当前激活配置 + 档位温度 + 思考强度覆盖构造
            m = RetryingModel(base_model.build(temperature=eff_temp, thinking=thinking))
        elif isinstance(base_model, DeepSeekModel) and eff_temp != 0.7:
            # 真实模型 + 能动性温度映射（档位低=精确执行温度低）
            m = RetryingModel(DeepSeekModel(temperature=eff_temp))
        else:
            m = model  # 共享 model（测试注入或默认真实）；温度由构造决定
        # 注入块装配：核心注入默认全开，skip_inject 可细粒度关闭（S15 增强按需）
        skip = skip_inject or set()
        # S58b context_mode（主人偏好：默认不继承场景记忆）：
        # - auto/fresh（默认干净）：不注入场景记忆/剧情计划——新任务/探索不被上次对话绑架
        # - continue（显式继承）：注入场景记忆 + 剧情计划——跨会话续写时显式打开
        # 心智习惯/世界事实（简介/设定档）始终保留（行为底线，非进程状态）。
        if context_mode != "continue":
            skip = skip | {"memory", "plan"}
        # 注入块装配（S62：表驱动重构——块定义收敛为 (key, 位置, 内容)，
        # 顺序/去留/优先级从 90 行 if 链变成可读数据；语义不变：
        # prepend 块（brief/collab 协作约定）置顶，其余按声明顺序追加）
        prepend_blocks: list[str] = []
        append_blocks: list[str] = []

        # 置顶块：项目简介（定调）→ 协作约定（怎么配合我）
        if "brief" not in skip:
            brief_block = workspace.read_brief(book_id)
            if brief_block:
                prepend_blocks.append(f"# 项目简介\n{brief_block}")
        if "manual" not in skip:
            collab_block = session_plan.collab_block()
            if collab_block:
                prepend_blocks.append(collab_block)

        # 追加块（按声明顺序 = 优先级）
        if "story" not in skip:
            tree_block = story_tree.render_tree(book_id)
            thread_block = story_threads.render_threads(book_id)
            nav = "\n\n".join(x for x in (tree_block, thread_block) if x)
            if nav:
                append_blocks.append(nav)
        # 能动性注入：当前档位（机制 2；职责边界：档位只管能动性，心智模型独立系统）
        if "agency" not in skip:
            agency_block = build_agency_block(current)
            if agency_block:
                append_blocks.append(agency_block)
        # AI 倾向档案注入（双向黑盒解法）
        if "bias" not in skip:
            bias_block = bias.render()
            if bias_block:
                append_blocks.append(bias_block)
        # 关键点图谱注入（T2 阶段 3：当前推进状态——哪些伏笔还开着/刚回收）
        # S31：注入时传当前章节数（老龄化：must 钩子标"已开放 N 章"，中性事实）
        if "plot" not in skip:
            plot_block = plots.render(book_id, current_order=len(chapters.list_by_book(book_id)))
            if plot_block:
                append_blocks.append(plot_block)
        # 设定档注入（S41 作者正典：人物卡/能力体系/世界观规则——与图谱互补）
        if "settings" not in skip:
            settings_block = render_settings(settings.list())
            if settings_block:
                append_blocks.append(settings_block)
        # S53 心智指导块：文风偏好 + 习惯（渐进式披露：只列关键条目，指导性保留）
        if "manual" not in skip:
            mind_block = session_plan.mind_block()
            if mind_block:
                append_blocks.append(mind_block)
        # S53c ④ 下轮展示学到：上次会话的场景记忆（跨会话延续性，归档过才注入）
        if "memory" not in skip:
            last_memory = memory_store.latest(book_id)
            if last_memory is not None:
                append_blocks.append("# 上次会话的延续（场景记忆）\n" + last_memory.content)
        # 叙事技巧注入（S50：索引常驻+内容按需；S55 #3 按 skills 内容签名缓存）
        # S60：主循环只注入全部技巧索引（target 不限——决策者需要看到全部可用
        # 技巧才能点名给写作调用）；完整内容靠 skill_lookup 按需 / write_chapter
        # 的 skills 参数点名（对齐图谱：内容按需查）。
        if "skills" not in skip:
            skill_sig = skills.revision()
            cached = _skill_cache.get(skill_sig)
            if cached is not None:
                skill_block = cached
            else:
                skill_block = render_skill_index(skills.list_skills(), target="")
                _skill_cache[skill_sig] = skill_block
                # 缓存防膨胀：超过 16 个签名清理最旧（长会话/多书场景安全阀）
                if len(_skill_cache) > 16:
                    oldest = next(iter(_skill_cache))
                    _skill_cache.pop(oldest, None)
            if skill_block:
                append_blocks.append(skill_block)
        # 剧情计划注入（S46：当前章+后续计划——AI 知道接下来写什么）
        if "plan" not in skip:
            plan_block = render_plan(plans.list())
            if plan_block:
                append_blocks.append(plan_block)

        # S70：破限模式（书籍级开关）——写作自由度：黑暗/暴力/敏感题材不设禁区。
        # 注入 agent 主循环（对话/写作全路径）+ write_chapter 干净调用（工具侧另注）。
        if workspace.is_uncensored(book_id):
            append_blocks.append(UNCENSORED_PROMPT)

        full_prompt = system_prompt
        if prepend_blocks:
            full_prompt = "\n\n".join(prepend_blocks) + "\n\n" + full_prompt
        if append_blocks:
            full_prompt = full_prompt + "\n\n" + "\n\n".join(append_blocks)
        return Agent(
            model=m,
            registry=registry,
            store=store,
            system_prompt=full_prompt,
            context_compressor=budget.compress,  # token 预算两阶段压缩（S8）
            persist_compression=True,  # S26：压缩结果回写 store（pi compaction entry 语义）
        )

    def _extract_chapter(
        book_id: str, title: str, content: str, order: int, line: str = "main"
    ) -> None:
        """章节落盘后自动：图谱抽取 + 伏笔自动回收（后台任务）。失败只记日志，绝不阻断写作。"""
        try:
            existing = [e.to_dict() for e in graph.list_entities(book_id)]
            ext = graph_extractor.extract(title, content, existing)
            graph.ingest_chapter(book_id, title, order, ext, line)
            logger.info(
                "图谱抽取完成: 《%s》 实体%d 关系%d 事件%d",
                title,
                len(ext.entities),
                len(ext.relations),
                len(ext.events),
            )
        except Exception as exc:  # 抽取失败不影响写作主链路
            logger.warning("图谱抽取失败(不影响写作): %s", exc)
        # 伏笔自动回收：本章揭开了哪些进行中的关键点（S17，独立 try 互不影响）
        try:
            resolved = plot_resolver.resolve(book_id, title, content, plots)
            if resolved:
                logger.info("伏笔自动回收: 《%s》 %s", title, "、".join(resolved))
        except Exception as exc:
            logger.warning("伏笔回收失败(不影响写作): %s", exc)
        # S55 #2 后台学习审查：本章揭示了什么新偏好/习惯 → 更新心智（轻量，失败不影响）
        try:
            _review_for_learning(book_id, title, content)
        except Exception as exc:
            logger.warning("学习审查失败(不影响写作): %s", exc)

    def _review_for_learning(book_id: str, title: str, content: str) -> None:
        """S55 #2 后台学习审查（借鉴 Hermes background_review）：

        章节落盘后，轻量 LLM 审查本章是否揭示了用户新偏好/习惯/雷区，
        有则 merge_add 进心智条目（合并式新增，治碎片）。隔离：只读快照，
        不碰主对话；失败不影响写作主链路。
        """
        try:
            entries = manual.list("project", book_id)
            prompt = build_learning_review_prompt(entries, f"章节：{title}\n\n{content[:1200]}")
            output = model.respond([Message(role="system", content=prompt)], [])
            found = parse_learning_review_result(output.text)
            added = 0
            for item in found:
                text = str(item.get("content", "")).strip()
                if not text:
                    continue
                _, did_merge = manual.merge_add(
                    ManualEntry(
                        content=text,
                        source="auto",
                        confidence=0.6,
                        activity="medium",
                        scope="project",
                        book_id=book_id,
                        category=item["category"],  # type: ignore[arg-type]
                    )
                )
                if not did_merge:
                    added += 1
            if found:
                logger.info("学习审查: 《%s》 提炼%d 条 合并/新增", title, len(found))
        except Exception as exc:
            logger.warning("学习审查失败(不影响写作): %s", exc)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name), "log": log_path()}

    # -----------------------------------------------------------------------
    # S58c 会话继承（参考 pi forkFrom：链条 parent 指针 + 复制源消息）
    # -----------------------------------------------------------------------
    @app.get("/api/conversations", response_model=list[dict[str, Any]])
    def list_conversations() -> list[dict[str, Any]]:
        """会话列表（含继承链条：parent_id/fork_point，可追溯）。"""
        convs = store.list_conversations()
        return [
            {
                "id": c.id,
                "created_at": c.created_at,
                "parent_id": c.parent_id,
                "fork_point": c.fork_point,
                "title": c.title,
                "message_count": len(store.messages(c.id)),
            }
            for c in reversed(convs)  # 新的在前
        ]

    @app.post("/api/conversations/{conv_id}/fork", response_model=dict[str, Any])
    def fork_conversation(conv_id: str, fork_point: str = "") -> dict[str, Any]:
        """S58c 继承派生：从当前会话创建继承它的新会话（链条可追溯）。

        新会话复制源会话消息（接着上次聊）+ parent_id 指向源会话；
        前端/agent 用它实现"继承并新开会话"。源不存在 → 404。
        """
        child = store.fork(conv_id, fork_point=fork_point or "从会话末尾继承")
        if child is None:
            raise HTTPException(status_code=404, detail=f"源会话不存在: {conv_id}")
        chain: list[str] = []
        cur: Conversation | None = child
        while cur is not None:
            chain.append(cur.id)
            cur = store.get(cur.parent_id) if cur.parent_id else None
        return {
            "conversation_id": child.id,
            "parent_id": child.parent_id,
            "fork_point": child.fork_point,
            "chain": chain,  # [新会话, 源, 源的源...] 继承链条
        }

    @app.put("/api/conversations/{conv_id}", response_model=dict[str, bool])
    def rename_conversation(conv_id: str, req: ConversationRenameIn) -> dict[str, bool]:
        """重命名会话。"""
        conv = store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        conv.title = req.title
        store.save(conv)
        return {"ok": True}

    @app.get("/api/conversations/{conv_id}/messages", response_model=list[dict[str, Any]])
    def get_conversation_messages(conv_id: str) -> list[dict[str, Any]]:
        """获取会话的全部消息（F4a：会话历史恢复）。"""
        conv = store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        msgs = store.messages(conv_id)
        return [{"role": m.role, "content": m.content} for m in msgs]

    @app.delete("/api/conversations/{conv_id}", response_model=dict[str, bool])
    def delete_conversation(conv_id: str) -> dict[str, bool]:
        """删除会话及其所有消息。"""
        conv = store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        store.delete(conv_id)
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S47 运行时模型配置：注册表 CRUD + 激活切换（换供应商/换模型/选思考强度）
    # -----------------------------------------------------------------------
    @app.get("/api/models", response_model=dict[str, Any])
    def list_models() -> dict[str, Any]:
        cfgs = models.list()
        active_id = next((c.id for c in cfgs if c.is_active), cfgs[0].id if cfgs else None)
        return {"active_id": active_id, "models": [c.to_dict() for c in cfgs]}

    @app.post("/api/models", response_model=dict[str, Any])
    def upsert_model(req: ModelIn) -> dict[str, Any]:
        """新增或更新模型配置（同 id 覆盖；id 缺省由 name 生成 slug）。"""
        from anyspark.models import validate_thinking

        try:
            validate_thinking(req.thinking)  # 非法思考强度 → 400（尽早暴露配置错误）
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cfg = ModelConfig(
            id=req.id or slugify(req.name),
            name=req.name,
            base_url=req.base_url or DEFAULT_BASE_URL,
            model=req.model,
            api_key=req.api_key,
            context_window=req.context_window or DEFAULT_CONTEXT_WINDOW,
            max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
            temperature=req.temperature or DEFAULT_TEMPERATURE,
            thinking=req.thinking,
        )
        saved = models.upsert(cfg)
        return {"ok": True, "model": saved.to_dict(), "active": saved.is_active}

    @app.delete("/api/models/{model_id}", response_model=dict[str, Any])
    def delete_model(model_id: str) -> dict[str, Any]:
        if not models.delete(model_id):
            raise HTTPException(status_code=400, detail="无法删除：至少保留一条配置，或配置不存在")
        return {"ok": True}

    @app.post("/api/models/{model_id}/activate", response_model=dict[str, Any])
    def activate_model(model_id: str) -> dict[str, Any]:
        """切换当前激活模型——所有组件（Agent/抽取/检测/探索/后台）即时跟随。"""
        cfg = models.activate(model_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"模型配置不存在: {model_id}")
        if cfg.context_window != _window:
            logger.warning(
                "模型窗口 %d != token 预算窗口 %d——重启后预算按新窗口生效（S26）",
                cfg.context_window,
                _window,
            )
        return {"ok": True, "active": cfg.to_dict()}

    @app.post("/api/chat/cancel")
    def cancel_chat(
        req: Annotated[CancelIn, Body()],
    ) -> dict[str, bool | str]:
        """协作式取消（S21）：中断正在跑的 Agent 循环（下个检查点生效）。

        conversation_id 为空时取消最近活跃的会话（新会话 id 由服务端生成，客户端未知）。
        """
        token = None
        if req.conversation_id:
            token = _active_tokens.get(req.conversation_id)
        elif _active_tokens:
            token = next(reversed(_active_tokens.values()), None)
        if token is not None:
            token.cancel()
            return {"ok": True}
        return {"ok": False, "reason": "会话未在运行"}

    @app.post("/api/chat/steer")
    def steer_chat(req: Annotated[SteerIn, Body()]) -> dict[str, bool | str]:
        """S25：运行中插话（对齐 pi Agent.steer）——消息在当前轮工具结果后、
        下一轮 LLM 前注入，写作时可中途说"别写太血腥"而不用取消重来。
        conversation_id 为空时取最近活跃会话（新会话 id 客户端可先于 turn_start 帧获得）。"""
        with _active_lock:
            if req.conversation_id:
                agent = _active_agents.get(req.conversation_id)
            elif _active_agents:
                agent = next(reversed(_active_agents.values()), None)
            else:
                agent = None
        if agent is None:
            return {"ok": False, "reason": "会话未在运行"}
        agent.steer(req.message)
        logger.info("steer 注入: msg=%s", req.message[:40])
        return {"ok": True}

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        """T7 验证指标（代理指标，纯 SQL 统计现有表，零新表）：修改率/提问率/完成率。"""
        return compute_stats(real_db)

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        # S47 请求级指定模型：不存在 → 400（不是 500）
        if req.model_id and models.get(req.model_id) is None:
            raise HTTPException(status_code=400, detail=f"模型配置不存在: {req.model_id}")
        # steering 防护（S21）：会话正在处理中时拒绝并发新消息，提示等待/取消
        if req.conversation_id and req.conversation_id in _active_tokens:
            raise HTTPException(
                status_code=409,
                detail="该会话正在处理中（可 POST /api/chat/cancel 中断后再发）",
            )
        logger.info("chat 请求: conv=%s len=%d", req.conversation_id or "(新)", len(req.message))
        events: list[ToolEvent] = []
        agent = _make_agent(
            req.system_prompt or DEFAULT_SYSTEM,
            req.temperature,
            book_id=req.book_id,
            agency_level=req.agency_level,
            enable_search=req.enable_search,
            enable_extras=req.enable_extras,
            enable_domain=req.enable_domain,
            enable_codex=req.enable_codex,
            enable_workflow=req.enable_workflow,
            enable_play=req.enable_play,
            skip_inject=set(req.skip_inject),
            context_mode=req.context_mode,
            model_id=req.model_id,
            thinking=req.thinking,
            # S61：本轮用户消息作为心智披露的上下文（按相关动态选取）
            context=req.message,
        )
        agent.events.on(
            "tool_call", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        agent.events.on(
            "tool_result", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        # 工具调用/结果写日志（排查用）
        agent.events.on("tool_call", lambda e: logger.info("工具调用: %s", e.payload.get("name")))
        agent.events.on(
            "tool_result",
            lambda e: logger.info("工具结果: %s ok=%s", e.payload.get("name"), e.payload.get("ok")),
        )

        # 无会话时显式创建，保证 conversation_id 可回传（多轮续写）
        conv_id = req.conversation_id
        if not conv_id:
            conv = agent.store.create()
            conv_id = conv.id

        # S49 运行记录：完整上下文+思维链落 data/records/<conv>/（修 bug/训练素材）
        recorder.attach(
            agent,
            conv_id,
            {
                "ts": _now_iso_rec(),
                "endpoint": "chat",
                "model": getattr(model, "model_name", "?"),
                "temperature": req.temperature,
                "agency_level": req.agency_level,
                "enable_domain": req.enable_domain,
                "enable_codex": req.enable_codex,
                "enable_workflow": req.enable_workflow,
                "enable_play": req.enable_play,
                "thinking": req.thinking,
                "model_id": req.model_id,
            },
        )
        # 协作式取消（S21 移植 pi 的 AbortSignal）：注册 token，/api/chat/cancel 可中断
        token = CancellationToken()
        _active_tokens[conv_id] = token
        with _active_lock:
            _active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
        try:
            turn = agent.run(req.message, conv_id, token)
        except Exception as exc:  # 记录并返回 500
            logger.exception("chat 执行异常: %s", exc)
            raise HTTPException(status_code=500, detail=f"执行失败: {exc}") from exc
        finally:
            _active_tokens.pop(conv_id, None)
            with _active_lock:
                _active_agents.pop(conv_id, None)
        if turn.error is not None:  # S22：模型调用失败/迭代上限（不再字符串匹配）
            logger.warning("chat 非正常结束: conv=%s error=%s", conv_id, turn.error)
            raise HTTPException(status_code=500, detail=turn.error)

        logger.info(
            "chat 完成: conv=%s 输出%d字 工具%d次", conv_id, len(turn.text), len(turn.tool_calls)
        )
        # S53c ② 归档后分析：会话结束后台摘要成场景记忆（不阻塞响应）
        _bg_queue.put(BgTask(kind="summarize", conv_id=conv_id))
        # 图谱抽取：写入章节后自动抽取入库（后台任务，不阻塞响应；失败不影响写作）
        # extract_graph 开关（S15）：默认开保持现状，可关省 token（手动 /api/graph/extract 兜底）
        if req.extract_graph:
            for wc in turn.tool_calls:
                if wc.name == "write_chapter":
                    title = str(wc.arguments.get("title", "")).strip()
                    content = str(wc.arguments.get("content", ""))
                    if title and content:
                        chs = chapters.list_by_book("main")
                        order = next((c.order_index for c in chs if c.title == title), len(chs))
                        logger.info("后台图谱抽取挂载: 《%s》", title)
                        line = str(wc.arguments.get("line", "main")).strip() or "main"
                        _bg_queue.put(
                            BgTask(
                                kind="chapter", title=title, content=content, order=order, line=line
                            )
                        )
        turns_payload = [{"text": turn.text, "tool_calls": [c.name for c in turn.tool_calls]}]
        # AI 档位声明解析（机制 2：AI 可声明，用户点选确认）
        declared = parse_agency_declaration(turn.text)
        return ChatResponse(
            conversation_id=conv_id,
            text=turn.text,
            turns=turns_payload,
            events=events,
            agency_declared=declared,
        )

    @app.post("/api/chat/stream")
    def chat_stream(req: ChatRequest) -> StreamingResponse:
        """SSE 流式：turn_start / text_delta / tool_call / tool_result / done / error。

        S8（模型局限弥补 + A 类硬编码 SSE 传输）：长文生成逐字流式，用户不等全量。
        事件帧格式：event: <type>\ndata: <json>\n\n（core 事件协议 → 传输层）。
        """
        events_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        def run_agent(agent: Agent, msg: str, conv_id: str) -> None:
            try:
                token = CancellationToken()
                _active_tokens[conv_id] = token
                with _active_lock:
                    _active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
                try:
                    turn = agent.run(msg, conv_id, token)
                finally:
                    _active_tokens.pop(conv_id, None)
                    with _active_lock:
                        _active_agents.pop(conv_id, None)
                # S53c ② 归档后分析：会话结束后台摘要成场景记忆（不阻塞 SSE done 帧）
                _bg_queue.put(BgTask(kind="summarize", conv_id=conv_id))
                # 图谱抽取：与 /api/chat 行为一致（write_chapter 落盘后自动抽取）
                # extract_graph 开关（S15）：默认开保持现状，可关省 token
                if req.extract_graph:
                    for wc in turn.tool_calls:
                        if wc.name == "write_chapter":
                            title = str(wc.arguments.get("title", "")).strip()
                            content = str(wc.arguments.get("content", ""))
                            if title and content:
                                chs = chapters.list_by_book("main")
                                order = next(
                                    (c.order_index for c in chs if c.title == title),
                                    len(chs),
                                )
                                # 后台队列处理（不阻塞 SSE 的 done 帧）
                                line = str(wc.arguments.get("line", "main")).strip() or "main"
                        _bg_queue.put(
                            BgTask(
                                kind="chapter", title=title, content=content, order=order, line=line
                            )
                        )
            except Exception as exc:  # 异常转 error 帧（不中断连接）
                logger.exception("chat/stream 执行异常: %s", exc)
                events_queue.put(("error", {"message": f"执行失败: {exc}"}))

        def gen() -> Any:
            # S47 请求级指定模型：不存在 → 400（SSE 里转 error 帧）
            if req.model_id and models.get(req.model_id) is None:
                events_queue.put(("error", {"message": f"模型配置不存在: {req.model_id}"}))
                yield (
                    "event: error\n"
                    + f"data: {json.dumps({'message': f'模型配置不存在: {req.model_id}'})}\n\n"
                )
                return
            agent = _make_agent(
                req.system_prompt or DEFAULT_SYSTEM,
                req.temperature,
                book_id=req.book_id,
                agency_level=req.agency_level,
                enable_search=req.enable_search,
                enable_extras=req.enable_extras,
                enable_domain=req.enable_domain,
                enable_codex=req.enable_codex,
                enable_workflow=req.enable_workflow,
                enable_play=req.enable_play,
                skip_inject=set(req.skip_inject),
                context_mode=req.context_mode,
                model_id=req.model_id,
                thinking=req.thinking,
                # S61：本轮用户消息作为心智披露的上下文
                context=req.message,
            )
            conv_id = req.conversation_id
            if not conv_id:
                conv = agent.store.create()
                conv_id = conv.id

            # S49 运行记录（流式）
            recorder.attach(
                agent,
                conv_id,
                {
                    "ts": _now_iso_rec(),
                    "endpoint": "chat_stream",
                    "model": getattr(model, "model_name", "?"),
                    "temperature": req.temperature,
                    "agency_level": req.agency_level,
                    "enable_domain": req.enable_domain,
                    "enable_codex": req.enable_codex,
                    "enable_workflow": req.enable_workflow,
                    "enable_play": req.enable_play,
                    "thinking": req.thinking,
                    "model_id": req.model_id,
                },
            )

            def on_event(e: Any) -> None:
                payload = e.payload
                # S25：turn_start 帧带 conversation_id——客户端尽早知道会话 id，运行中可 steer
                if e.type == "turn_start":
                    payload = {**payload, "conversation_id": conv_id}
                events_queue.put((e.type, payload))

            # S21 流式核心：Agent 内部流式（model.respond_stream），text_delta 事件转 SSE 帧
            agent.events.on("text_delta", lambda e: events_queue.put(("text_delta", e.payload)))
            for t in (
                "turn_start",
                "text",
                "tool_call",
                "tool_execution_start",  # S25：前端显示"正在执行…"
                "tool_execution_end",  # S25：前端显示耗时/结果
                "tool_result",
                "done",
                "error",
            ):
                agent.events.on(t, on_event)
            # Agent 循环在线程跑，事件经 queue 转 SSE 帧（同步生成器流式输出）
            threading.Thread(
                target=run_agent, args=(agent, req.message, conv_id), daemon=True
            ).start()
            while True:
                try:
                    etype, payload = events_queue.get(timeout=120)
                except queue.Empty:
                    yield _sse_frame("error", {"message": "流式超时（120s 无事件）"})
                    break
                if etype == "done":
                    yield _sse_frame("done", {"conversation_id": conv_id})
                    break
                if etype == "error":
                    yield _sse_frame("error", payload)
                    break
                yield _sse_frame(etype, payload)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/manual", response_model=list[dict[str, Any]])
    def list_manual(scope: str = "project") -> list[dict[str, Any]]:
        """说明书条目（scope=project|global）。"""
        entries = manual.list(scope, "main")  # type: ignore[arg-type]
        return [e.to_dict() for e in entries]

    @app.post("/api/manual", response_model=dict[str, Any])
    def add_manual(req: ManualEntryIn) -> dict[str, Any]:
        """新增说明书条目（用户手写）。"""
        scope = cast(Literal["project", "global"], req.scope)
        entry = ManualEntry(
            content=req.content,
            source="user",
            confidence=req.confidence,
            scope=scope,
            book_id="main",
            category=cast(
                Literal["collab", "style", "habit"],
                req.category if req.category in ("collab", "style", "habit") else "style",
            ),
        )
        manual.add(entry)
        # S54-B：新增 style 偏好 → 后台生成对应 skill 候选草稿（人工确认生效）
        if entry.category == "style":
            _bg_queue.put(BgTask(kind="skill_drafts"))
        return entry.to_dict()

    @app.patch("/api/manual/{entry_id}", response_model=dict[str, Any])
    def update_manual(entry_id: str, req: ManualEntryPatch) -> dict[str, Any]:
        """修改条目内容（锁定条目拒绝，用户主权）。"""
        entry = manual.update(entry_id, content=req.content, category=req.category)
        if entry is None:
            raise HTTPException(status_code=404, detail="条目不存在")
        if req.locked is not None:
            entry = manual.set_locked(entry_id, req.locked) or entry
        return entry.to_dict()

    @app.delete("/api/manual/{entry_id}")
    def delete_manual(entry_id: str) -> dict[str, bool]:
        manual.delete(entry_id)
        return {"ok": True}

    @app.post("/api/manual/decay", response_model=dict[str, object])
    def manual_decay(req: ManualDecayIn) -> dict[str, object]:
        """S61：活跃度衰减（DESIGN §12.18 元数据收敛：冷条沉没）。

        长时间未触达的未锁定条目自动降级（high→medium→low）；list() 已惰性执行，
        本端点提供显式触发与阈值覆盖。只降活跃度、不删内容（用户主权）。
        """
        n = manual.decay_stale(req.days_high, req.days_medium)
        entries = manual.list("project")
        low = [e.to_dict() for e in entries if e.activity == "low" and not e.locked]
        return {"decayed": n, "cold_entries": low, "note": "冷条目未自动删除，可手动删除"}

    # S58 项目智能体简介（给 AI 和用户看的项目总览，非读者简介）
    @app.get("/api/brief", response_model=dict[str, Any])
    def get_brief(book_id: str = "main") -> dict[str, Any]:
        """读项目简介（md 权威；未建档返回空 + 提示）。"""
        content = workspace.read_brief(book_id)
        return {"book_id": book_id, "content": content, "exists": bool(content)}

    @app.post("/api/brief", response_model=dict[str, Any])
    def save_brief(req: BriefIn) -> dict[str, Any]:
        """写项目简介（用户/前端可编辑，权威在 md 文件）。"""
        workspace.write_brief(req.book_id, req.content)
        return {"book_id": req.book_id, "content": req.content.strip(), "exists": True}

    @app.post("/api/brief/generate", response_model=dict[str, Any])
    def generate_brief(req: BriefGenerateIn) -> dict[str, Any]:
        """从现有项目数据自动生成简介草案（人工确认后写回）。

        素材：已固化设定约束 + 已选方向 + 设定档 + 当前进展（章节数/场景记忆）。
        真实 LLM 提炼成总览；失败返回空提示。
        """
        try:
            archive = ProjectArchive(real_db)
            constraints = archive.constraints(req.book_id)
            directions = archive.directions(req.book_id)[:5]
            settings_items = settings.list(req.book_id)
            ch_count = len(chapters.list_by_book(req.book_id))
            last_scene = memory_store.latest(req.book_id)
            parts = [
                "已固化设定约束：" + ("；".join(constraints) if constraints else "（无）"),
                "已选方向："
                + (
                    "; ".join(
                        f"{d.get('title', '')}: {d.get('summary', '')[:80]}" for d in directions
                    )
                    if directions
                    else "（无）"
                ),
                "设定档条目："
                + (
                    "; ".join(f"{s.name}" for s in settings_items[:10])
                    if settings_items
                    else "（无）"
                ),
                f"当前进展：已写 {ch_count} 章"
                + (f"；最近：{last_scene.content[:120]}" if last_scene else ""),
            ]
            prompt = (
                "你是小说项目简介生成器。根据下面的项目现状素材，生成一份『项目智能体简介』\n"
                "（给 AI 和用户看的协作总览，不是读者简介）。\n"
                "包含：一句话世界观 / 主线方向 / 主要角色 / 叙事基调 / "
                "已固化设定 / 当前进展 / 写作注意事项。\n"
                "用明确无歧义的自然语言，总长 300 字以内。\n\n素材：\n" + "\n".join(parts)
            )
            output = model.respond([Message(role="system", content=prompt)], [])
            draft = (output.text or "").strip()
            if not draft:
                return {"draft": "", "note": "生成失败（空输出）"}
            return {"draft": draft, "note": ""}
        except Exception as exc:
            return {"draft": "", "note": f"生成失败: {exc}"}

    @app.post("/api/signals")
    def record_signal(req: SignalIn) -> dict[str, Any]:
        """采集用户操作信号（接受/修改/删除/自定义等）；同时驱动能动性反馈调节。"""
        if req.kind == "accepted":
            sig = signal_collector.accepted(req.content, req.context)
            agency.adjust(+1)  # 接受=升级（档位上限 4）
        elif req.kind == "deleted":
            sig = signal_collector.deleted(req.content, req.context)
            agency.adjust(-1)  # 删除=降级（档位下限 0）
        elif req.kind == "rejected":
            sig = signal_collector.rejected(req.content, req.context)
            agency.adjust(-1)  # 拒绝=降级
        elif req.kind == "negative":
            # S53c ⑤ 实时负例：负例信号原文进 signals 表（不丢）——"是否构成雷区、
            # 雷区是什么"是内容判断，交给轮末提炼器 LLM（S62：删除正则机械落条目）
            sig = signal_collector.negative(req.content, req.context)
        elif req.kind == "custom":
            sig = signal_collector.custom(req.content, req.context)
        else:  # modified
            sig = signal_collector.modified(req.content, req.new_content or "", req.context)
        # S28：信号 → 后台提炼 → 说明书（异步，不阻塞操作；修复对齐闭环缺口）
        _bg_queue.put(BgTask(kind="refine"))
        # S54-C：信号驱动 → skill 候选草稿（后台，人工确认生效）
        _bg_queue.put(BgTask(kind="skill_drafts"))
        return sig.to_dict()

    @app.post("/api/mind/reconcile", response_model=dict[str, Any])
    def mind_reconcile(req: ReconcileIn) -> dict[str, Any]:
        """S53c ⑥ 跨会话对账：已沉淀条目 vs 最近行为信号 → 冲突/需更新提示（真实 LLM）。"""
        entries = manual.list("project", req.book_id)
        recent_signals = signals.recent(limit=30, book_id=req.book_id)
        if not entries:
            return {"results": [], "note": "无条目可对账"}
        prompt = build_reconcile_prompt(entries, recent_signals)
        try:
            output = model.respond([Message(role="system", content=prompt)], [])
            results = parse_reconcile_result(output.text)
            return {"results": results, "note": ""}
        except Exception as exc:  # 对账失败不影响主链路
            logger.warning("心智对账失败: %s", exc)
            return {"results": [], "note": f"对账失败: {exc}"}

    @app.post("/api/mind/agency-suggest", response_model=dict[str, object])
    def mind_agency_suggest(req: ReconcileIn) -> dict[str, object]:
        """S61 L2：AI 看心智（collab 条目）后建议档位（真实 LLM，语义判断）。

        与 MindPlanner 关键词启发式互补：启发式处理无 LLM/失败场景，L2 理解
        复杂协作偏好（如"你看着办但大事先问我"）。建议不自动应用（用户主权），
        采纳后走 POST /api/agency。
        """
        assert model is not None
        entries = manual.list("project", req.book_id)
        collab = [e for e in entries if e.category == "collab"]
        levels = agency.list_levels()
        # 启发式对照（始终返回，供前端展示规则推断）
        plan = mind_planner.plan(req.book_id, base_agency=agency.get_current(req.book_id).order)
        if not collab:
            return {
                "suggested_level": None,
                "reason": "暂无协作偏好条目（collab），先用规则推断",
                "note": "",
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }
        prompt = build_agency_suggest_prompt(collab, levels)
        try:
            output = model.respond([Message(role="system", content=prompt)], [])
            res = parse_agency_suggest_result(output.text)
            valid = next((lv for lv in levels if lv.id == res.get("level_id", "")), None)
            return {
                "suggested_level": valid.to_dict() if valid else None,
                "reason": res.get("reason", ""),
                "note": res.get("note", ""),
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }
        except Exception as exc:  # 建议失败不影响主链路
            logger.warning("档位建议失败: %s", exc)
            return {
                "suggested_level": None,
                "reason": f"建议失败: {exc}",
                "note": "",
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }

    @app.get("/api/mind/agency-suggest", response_model=dict[str, object])
    def mind_agency_heuristic() -> dict[str, object]:
        """S61 L2 只读通道：当前规则推断（不调 LLM，前端打开面板即可展示）。"""
        plan = mind_planner.plan("main", base_agency=agency.get_current("main").order)
        return {
            "heuristic_agency": plan.agency_level,
            "heuristic_reason": plan.reason,
            "collab_notes": plan.collab_notes,
        }

    @app.post("/api/explore/intent", response_model=dict[str, object])
    def explore_intent(req: ExploreIntentIn) -> dict[str, object]:
        """种子 → 概念卡 + 关键歧义点（意图理解）。"""
        understander = IntentUnderstander(model)
        return understander.understand(req.seed)

    @app.post("/api/explore/cards", response_model=list[dict[str, object]])
    def explore_cards(req: ExploreCardsIn) -> list[dict[str, object]]:
        """确认后的意图 → 方向卡 ×4（并行探索，三来源混合）。"""
        constraints = archive.constraints("main")
        # S68：探索注入真实模板库（L2+L3 合并；template 来源探索者消费，死库接线）
        templates = [f"{t.name}：{t.description}" for t in templates_external.all()[:12]]
        cards = run_exploration(
            model,
            req.seed,
            req.intent_confirmed,
            constraints,
            n_explorers=4,
            dimensions=dim_store.list_names(),  # S50：维度来自内容载体（可增删改）
            templates=templates,
        )
        return [c.to_dict() for c in cards]

    @app.post("/api/explore/path", response_model=dict[str, object])
    def explore_path_route(req: PathExploreIn) -> dict[str, object]:
        """路径探索（S67）：起点 A → 终点 B 的 N 条串联路径候选（叙事树节点之间）。

        三层探索粒度的中间层：大方向 explore → 桥梁 path → 场景内 play。
        输出作为参考（不直接写正文）；archive_index 显式传才落叙事树。
        """
        from anyspark.explore import explore_path

        from_desc, to_desc = req.from_desc, req.to_desc
        if req.from_node_id:
            node = story_tree.get(req.from_node_id)
            if node is None:
                raise HTTPException(status_code=404, detail=f"起点节点不存在：{req.from_node_id}")
            from_desc = node.content
        if not from_desc.strip():
            raise HTTPException(status_code=400, detail="需要 from_desc 或 from_node_id")
        if req.to_node_id:
            node = story_tree.get(req.to_node_id)
            if node is None:
                raise HTTPException(status_code=404, detail=f"终点节点不存在：{req.to_node_id}")
            to_desc = node.content
        constraints = archive.constraints(req.book_id) + req.constraints
        result = explore_path(model, from_desc, to_desc, constraints, n=req.n)
        if not result.paths:
            raise HTTPException(status_code=502, detail="路径探索失败（无有效候选）")
        paths = result.to_dict()["paths"]
        archived: dict[str, object] | None = None
        if req.archive_index is not None:
            idx = req.archive_index - 1
            if not (0 <= idx < len(paths)):
                raise HTTPException(status_code=400, detail=f"archive_index 越界（1-{len(paths)}）")
            if not req.from_node_id:
                raise HTTPException(
                    status_code=400, detail="落树需要 from_node_id（起点必须是叙事树节点）"
                )
            chosen = paths[idx]
            node_ids: list[str] = []
            cur_parent: str | None = req.from_node_id
            for ev in chosen["events"]:
                node = story_tree.add_node(
                    content=ev, book_id=req.book_id, parent_id=cur_parent, kind="candidate"
                )
                node_ids.append(node.id)
                cur_parent = node.id
            archived = {"node_ids": node_ids, "path": chosen}
        logger.info(
            "路径探索: %s → %s × %d 条%s",
            from_desc[:20],
            to_desc[:20],
            len(paths),
            "（已落树）" if archived else "",
        )
        return {"paths": paths, "archived": archived}

    @app.get("/api/explore/dims", response_model=list[dict[str, object]])
    def list_explore_dims() -> list[dict[str, object]]:
        """探索维度（内容化：可增删改/开关）。"""
        return dim_store.list_all()

    @app.post("/api/explore/dims", response_model=dict[str, object])
    def add_explore_dim(req: ExploreDimIn) -> dict[str, object]:
        d = dim_store.add(req.name)
        if d is None:
            raise HTTPException(status_code=409, detail=f"维度已存在: {req.name}")
        return d

    @app.patch("/api/explore/dims/{dim_id}", response_model=dict[str, object])
    def patch_explore_dim(dim_id: str, req: ExploreDimPatch) -> dict[str, object]:
        d = dim_store.set_enabled(dim_id, req.enabled)
        if d is None:
            raise HTTPException(status_code=404, detail="维度不存在")
        return d

    @app.delete("/api/explore/dims/{dim_id}", response_model=dict[str, bool])
    def delete_explore_dim(dim_id: str) -> dict[str, bool]:
        ok = dim_store.delete(dim_id)
        if not ok:
            raise HTTPException(status_code=404, detail="维度不存在")
        return {"ok": True}

    @app.post("/api/explore/archive", response_model=dict[str, object])
    def explore_archive(req: ExploreArchiveIn) -> dict[str, object]:
        """固化选中方向进项目档案 + 叙事树（S59：探索 = 树的生长器）。

        选中方向卡 → 存档 + 写入叙事树为当前主线节点（chosen），
        探索产生的分叉在树上留痕（其余候选由前端按需加为 candidate）。
        """
        c = req.card
        src: Literal["template", "grow", "user"]
        if c.get("source") == "grow":
            src = "grow"
        elif c.get("source") == "user":
            src = "user"
        else:
            src = "template"
        card = DirectionCard(
            title=str(c.get("title", "未命名方向")),
            summary=str(c.get("summary", "")),
            dimension=str(c.get("dimension", "情节驱动")),
            source=src,
            term=str(c.get("term", "")),
        )
        archived = archive.archive_direction(card)
        # S59：写入叙事树为主线节点（探索 = 树的生长）
        parent_id = req.parent_node_id or None
        node = story_tree.add_node(
            content=f"{card.title}：{card.summary[:60]}",
            book_id="main",
            parent_id=parent_id,
            kind="main",
            chosen=True,
        )
        archived["story_node_id"] = node.id
        return archived

    @app.get("/api/explore/archive", response_model=list[dict[str, object]])
    def explore_archive_list() -> list[dict[str, object]]:
        return archive.directions()

    @app.post("/api/check", response_model=dict[str, object])
    def check_text_route(req: CheckRequest) -> dict[str, object]:
        """多检测者审读正文（骨架检测项，并行）+ 图谱事实证据 + 时序校验（确定性规则）。"""
        report = run_review(model, req.target, req.text)
        # S7：图谱事实证据——文本涉及的已知实体/关系（检测网/用户比对设定冲突）
        evidence = graph_verifier.render_evidence("main", req.text)
        # S13：时序校验——截止当前章节时空点，提及未来才首现的实体=时空倒置
        # S29：按叙事线比较（跨线首现不误报，多线并行时间差正常）
        temporal = (
            graph_verifier.check_temporal("main", req.text, req.chapter_order, req.line)
            if req.chapter_order is not None
            else []
        )
        return {
            "target": report.target,
            "hard_count": report.hard_count,
            "graph_evidence": evidence,
            "temporal_warnings": temporal,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "evidence": f.evidence,
                    "suggestion": f.suggestion,
                    "source": f.source,
                }
                for f in report.findings
            ],
        }

    @app.post("/api/check/rule", response_model=dict[str, object])
    def check_rule_route(req: RuleRequest) -> dict[str, object]:
        """规则编译：用户自然语言规则 → 检测命中（内容判断交给模型，模板 fallback）。

        哲学（DESIGN §1）：用户规则"是什么意思"是内容判断 → LLM 编译；
        检测"怎么做"是过程 → 确定性执行器硬编码。模型/模板都识别不了时
        明确告知（不再静默丢弃）。
        """
        assert model is not None
        # LLM 编译（内容判断）→ 失败回退轻量模板（无 LLM 场景）
        compiled = compile_with_model(req.rule, model) or compile_rule(req.rule)
        if compiled is None:
            return {
                "ok": False,
                "description": "未能识别的规则：请用更具体的字面/结构描述（如'不要用破折号'）",
                "hits": [],
            }
        hits = compiled.checker(req.text)
        return {"ok": True, "description": compiled.description, "hits": hits}

    @app.get("/api/templates", response_model=list[dict[str, object]])
    def list_templates() -> list[dict[str, object]]:
        """模式库 L2+L3 合并（探索方向生成器）。"""
        return [t.to_dict() for t in templates_external.all()]

    @app.post("/api/templates/import", response_model=dict[str, object])
    def import_template(req: TemplateIn) -> dict[str, object]:
        """L3 外部模式库：导入自定义模板（自然语言+四要素，合并进探索库）。"""
        t = templates_external.import_template(
            req.name, req.description, req.granularity, req.position, req.function, req.params
        )
        return t.to_dict()

    @app.delete("/api/templates/{name}")
    def delete_template(name: str) -> dict[str, bool]:
        templates_external.delete(name)
        return {"ok": True}

    @app.post("/api/plot", response_model=list[dict[str, object]])
    def generate_plot(req: PlotIn) -> list[dict[str, object]]:
        """关键点图谱（T2 阶段 3 可选深入）：LLM 生成草案入库。"""
        points = plot_generator.generate("main", plots, req.settings)
        return [p.to_dict() for p in points]

    @app.get("/api/plot", response_model=list[dict[str, object]])
    def list_plot() -> list[dict[str, object]]:
        return [p.to_dict() for p in plots.list_points()]

    @app.patch("/api/plot/{plot_id}", response_model=dict[str, object])
    def update_plot_status(plot_id: str, req: PlotPatchIn) -> dict[str, object]:
        """更新关键点：状态/关注度/优先级/回收章节——操作即对齐信号。"""
        p = plots.update(
            plot_id,
            status=req.status,
            attention=req.attention,
            priority=req.priority,
            resolved_chapter=req.resolved_chapter,
        )
        if p is None:
            raise HTTPException(status_code=404, detail="关键点不存在")
        return p.to_dict()

    @app.post("/api/plot/item", response_model=dict[str, object])
    def add_plot_item(req: PlotItemIn) -> dict[str, object]:
        """S31：主动登记伏笔/关键点（作者或 AI 声明）——
        priority=must 表示这是作者对读者的主线承诺（剧情钩子，必须回收）；
        planted_order 记录登记时的章节序号（老龄化计算用）。"""
        p = plots.add(
            "main",
            req.category,
            req.content,
            req.chapter_ref,
            priority=req.priority,
            planted_order=req.planted_order,
        )
        return p.to_dict()

    @app.post("/api/plot/import-resolve")
    def resolve_all_plots() -> dict[str, int]:
        """S31：完整书导入归档——所有 open 伏笔标 resolved（书已写完，线索已揭开）。
        只报告归档数量，不输出回收率（伏笔管理烂不影响作品伟大性，不做质量评分）。"""
        n = plots.resolve_all("main")
        return {"resolved": n}

    @app.delete("/api/plot/{plot_id}")
    def delete_plot(plot_id: str) -> dict[str, bool]:
        plots.delete(plot_id)
        return {"ok": True}

    @app.post("/api/materials", response_model=dict[str, object])
    def add_material(req: MaterialIn) -> dict[str, object]:
        """上传材料 → 真实 LLM 消化成摘要卡 → 图谱关联 → 入库（原文保留）。"""
        purpose: Any = req.purpose if req.purpose in ("style", "fact", "both") else "fact"
        digestor = MaterialDigestor(model)
        card = digestor.digest(req.text, purpose=purpose)
        if req.title:
            card.title = req.title
        # 图谱关联（机制 10 补齐）：摘要卡角色/设定/术语 → 图谱实体
        names = [*card.characters, *card.key_settings, *card.terms]
        linked = graph.resolve_names("main", names)
        card.graph_entities = [e.id for e in linked]
        materials.save(card)
        return card.to_dict()

    @app.get("/api/materials", response_model=list[dict[str, object]])
    def list_materials() -> list[dict[str, object]]:
        return [m.to_dict() for m in materials.list()]

    @app.get("/api/materials/{material_id}", response_model=dict[str, object])
    def get_material(material_id: str) -> dict[str, object]:
        card = materials.get(material_id)
        if card is None:
            raise HTTPException(status_code=404, detail="材料不存在")
        return card.to_dict()

    @app.delete("/api/materials/{material_id}", response_model=dict[str, object])
    def delete_material(material_id: str) -> dict[str, object]:
        """删除资料。"""
        ok = materials.delete(material_id)
        if not ok:
            raise HTTPException(status_code=404, detail="材料不存在")
        return {"ok": True, "id": material_id}

    @app.get("/api/agency", response_model=dict[str, object])
    def get_agency() -> dict[str, object]:
        """能动档位（机制 2 + S35 记录集）：当前档位 + 全部档位（含自定义）。"""
        return {
            "current": agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in agency.list_levels()],
        }

    @app.post("/api/agency", response_model=dict[str, object])
    def set_agency(req: AgencyIn) -> dict[str, object]:
        """用户点选档位（level_id 优先；兼容旧 level 数字=排序位）。"""
        if req.level_id:
            lv = agency.set_current(req.level_id)
        elif req.level is not None:
            levels = agency.list_levels()
            target = next((x for x in levels if x.order == req.level), None)
            lv = agency.set_current(target.id) if target else None
        else:
            lv = None
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {"current": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.post("/api/agency/add", response_model=dict[str, object])
    def add_agency_level(req: AgencyLevelIn) -> dict[str, object]:
        """S35：新增自定义档位（全局，追加到末尾）。"""
        lv = agency.add_level(req.name, req.description, req.temperature)
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.post("/api/agency/generate", response_model=dict[str, object])
    def generate_agency(req: AgencyGenerateIn) -> dict[str, object]:
        """S61 L3：自然语言描述 → 档位候选（真实 LLM，人工确认后 add 生效）。

        对齐 S54 skillgen"候选→确认闸门"哲学：候选不进表，返回给用户/前端确认。
        """
        assert model is not None
        if not req.description.strip():
            raise HTTPException(status_code=400, detail="description 不能为空")
        if not 1 <= req.n <= 5:
            raise HTTPException(status_code=400, detail="n 需在 1-5 之间")
        prompt = build_agency_gen_prompt(req.description, req.n)
        try:
            out = model.respond([Message(role="system", content=prompt)], [])
            candidates = parse_agency_gen_result(out.text)
            return {
                "candidates": candidates[: req.n],
                "description": req.description,
                "note": "确认后 POST /api/agency/add 生效（人工确认闸门）",
            }
        except Exception as exc:
            logger.warning("档位生成失败: %s", exc)
            return {"candidates": [], "description": req.description, "note": f"生成失败: {exc}"}

    @app.patch("/api/agency/{level_id}", response_model=dict[str, object])
    def patch_agency_level(level_id: str, req: AgencyLevelIn) -> dict[str, object]:
        """S35：修改档位名称/描述/温度。"""
        lv = agency.update_level(level_id, req.name, req.description, req.temperature)
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.delete("/api/agency/{level_id}", response_model=dict[str, object])
    def delete_agency_level(level_id: str) -> dict[str, object]:
        """S35：删除档位（至少保留一条；删当前则回落默认）。"""
        ok = agency.delete_level(level_id)
        if not ok:
            raise HTTPException(status_code=400, detail="无法删除（至少保留一条或不存在）")
        return {"levels": [x.to_dict() for x in agency.list_levels()]}

    @app.post("/api/agency/reset", response_model=dict[str, object])
    def reset_agency() -> dict[str, object]:
        """S35：恢复默认五级档位（不重置心智模型——manual 在不同表，天然保留）。"""
        levels = agency.reset_defaults()
        return {
            "current": agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in levels],
        }

    # ------------------------------------------------------------------
    # S40 批量任务（场景 4 全书变换核心）：批量改写 / 批量审读
    # 后台队列执行（不阻塞请求），GET /api/batch/{id} 查进度；状态内存级（会话内）
    # ------------------------------------------------------------------
    @app.post("/api/batch/rewrite", response_model=dict[str, object])
    def batch_rewrite(req: BatchRewriteIn) -> dict[str, object]:
        """批量改写：多章统一指令改写（改文风/改情节），覆盖前旧版进版本历史。"""
        if not req.chapter_ids:
            raise HTTPException(status_code=400, detail="chapter_ids 不能为空")
        if not req.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction 不能为空")
        bid = uuid.uuid4().hex
        with _batch_lock:
            _batches[bid] = {
                "status": "queued",
                "done": 0,
                "total": len(req.chapter_ids),
                "results": [],
                "kind": "rewrite",
                "instruction": req.instruction,
            }
        _bg_queue.put(
            BgTask(
                kind="batch_rewrite", batch_id=bid, ids=req.chapter_ids, instruction=req.instruction
            )
        )
        return {"batch_id": bid, "total": len(req.chapter_ids)}

    @app.post("/api/batch/review", response_model=dict[str, object])
    def batch_review(req: BatchReviewIn) -> dict[str, object]:
        """批量审读：多章检测网审读（一致性/动机因果/情感连贯等 7 类）。"""
        if not req.chapter_ids:
            raise HTTPException(status_code=400, detail="chapter_ids 不能为空")
        bid = uuid.uuid4().hex
        with _batch_lock:
            _batches[bid] = {
                "status": "queued",
                "done": 0,
                "total": len(req.chapter_ids),
                "results": [],
                "kind": "review",
            }
        _bg_queue.put(BgTask(kind="batch_review", batch_id=bid, ids=req.chapter_ids))
        return {"batch_id": bid, "total": len(req.chapter_ids)}

    @app.get("/api/batch/{batch_id}", response_model=dict[str, object])
    def batch_status(batch_id: str) -> dict[str, object]:
        """批量任务状态/进度/结果。"""
        with _batch_lock:
            batch = _batches.get(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="批量任务不存在")
        return {
            "batch_id": batch_id,
            "status": batch["status"],
            "done": batch["done"],
            "total": batch["total"],
            "results": batch["results"],
        }

    # ------------------------------------------------------------------
    # S41 设定档（作者正典：人物卡/能力体系/世界观规则）
    # ------------------------------------------------------------------
    @app.get("/api/settings/categories", response_model=list[dict[str, Any]])
    def list_setting_categories() -> list[dict[str, Any]]:
        """设定档类别（S50 内容化：可增删改/开关）。"""
        return settings.list_categories()

    @app.post("/api/settings/categories", response_model=dict[str, Any])
    def add_setting_category(req: SettingCategoryIn) -> dict[str, Any]:
        c = settings.add_category(req.name)
        if c is None:
            raise HTTPException(status_code=409, detail=f"类别已存在: {req.name}")
        return c

    @app.patch("/api/settings/categories/{cat_id}", response_model=dict[str, Any])
    def patch_setting_category(cat_id: str, req: SettingCategoryPatch) -> dict[str, Any]:
        c = settings.set_category_enabled(cat_id, req.enabled)
        if c is None:
            raise HTTPException(status_code=404, detail="类别不存在")
        return c

    @app.delete("/api/settings/categories/{cat_id}", response_model=dict[str, bool])
    def delete_setting_category(cat_id: str) -> dict[str, bool]:
        ok = settings.delete_category(cat_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类别不存在")
        return {"ok": True}

    @app.get("/api/settings", response_model=list[dict[str, Any]])
    def list_settings() -> list[dict[str, Any]]:
        """设定档全部条目。"""
        return [s.to_dict() for s in settings.list()]

    @app.post("/api/settings", response_model=dict[str, Any])
    def add_setting(req: WorldSettingIn) -> dict[str, Any]:
        """新增设定条目（作者手写）。"""
        s = settings.add(req.content, req.category, req.name, source="manual")
        return s.to_dict()

    @app.patch("/api/settings/{setting_id}", response_model=dict[str, Any])
    def patch_setting(setting_id: str, req: WorldSettingPatch) -> dict[str, Any]:
        s = settings.update(setting_id, req.content, req.category, req.name)
        if s is None:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return s.to_dict()

    @app.delete("/api/settings/{setting_id}", response_model=dict[str, bool])
    def delete_setting(setting_id: str) -> dict[str, bool]:
        ok = settings.delete(setting_id)
        if not ok:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return {"ok": True}

    # S70：破限模式开关（书籍级）——GET 查 / POST 设；文件标志在每书工作区
    @app.get("/api/uncensored", response_model=dict[str, object])
    def get_uncensored(book_id: str = "main") -> dict[str, object]:
        return {"book_id": book_id, "enabled": workspace.is_uncensored(book_id)}

    @app.post("/api/uncensored", response_model=dict[str, object])
    def set_uncensored(req: UncensorIn) -> dict[str, object]:
        enabled = workspace.set_uncensored(req.book_id, req.enabled)
        return {"book_id": req.book_id, "enabled": enabled}

    @app.post("/api/settings/extract", response_model=dict[str, object])
    def extract_settings(req: WorldSettingExtractIn) -> dict[str, object]:
        """S42：从图谱提炼设定草案（只含已揭示信息，LLM 生成，作者确认后入库）。

        提炼边界（防止"角色认知越界/未来设定泄露"）：只基于图谱已有实体/事件——
        图谱覆盖=已写章节=角色与叙事者都可能知道的信息；未来设定需作者手写补充。
        """
        assert model is not None
        es = graph.list_entities(req.book_id, limit=10000)
        core = [e for e in es if e.weight >= 3]
        evs = sorted(graph.list_events(req.book_id, limit=10000), key=lambda x: x.chapter_order)
        ent_txt = "\n".join(
            f"- {e.name}（{e.entity_type}，出场{e.weight}章）"
            f"{('：' + (e.state or e.description)[:60]) if (e.state or e.description) else ''}"
            for e in sorted(core, key=lambda x: -x.weight)[:60]
        )
        ev_txt = "\n".join(
            f"[{ev.chapter_ref}] {ev.label}：{ev.description[:60]}" for ev in evs[:80]
        )
        prompt = (
            "根据以下小说知识图谱数据（实体/事件），提炼【设定档草案】——"
            "只包含图谱中已出现的信息（不编造未来设定）。按类别输出：\n"
            "人物卡（主要角色：身份/性格/当前状态）/ 能力体系（已出现的职业能力）/ "
            "世界观规则 / 势力 / 地点 / 物品。\n"
            '输出 JSON：{"settings": [{"category": "人物卡", '
            '"name": "顾欣桐", "content": "..."}]}\n'
            f"【实体】\n{ent_txt}\n【事件】\n{ev_txt}"
        )
        out = model.respond(
            [
                Message(
                    role="system",
                    content="你是设定考据者。严格基于图谱数据提炼设定草案，不编造。",
                ),
                Message(role="user", content=prompt),
            ],
            [],
        )
        import re as _re

        m = _re.search(r"\{.*\}", out.text, _re.DOTALL)
        if not m:
            return {"draft": [], "raw": out.text[:500]}
        try:
            data = json.loads(m.group(0))
            draft = [
                s for s in data.get("settings", []) if isinstance(s, dict) and s.get("content")
            ]
        except Exception:
            return {"draft": [], "raw": out.text[:500]}
        return {"draft": draft, "raw": ""}

    # ------------------------------------------------------------------
    # S50 叙事技巧（skill 式内容载体：镜头感/对白机锋/节奏控制等，可增删改/开关）
    # ------------------------------------------------------------------
    @app.post("/api/skills/generate", response_model=dict[str, object])
    def generate_skill(req: SkillGenerateIn) -> dict[str, object]:
        """S54/S58：从原文提炼 skill 候选（人工确认后走 /api/skills 入库）。

        mode=writing：文风/叙事技法（target=writing，写作调用用）；
        mode=main：类型/结构组织指导（target=main，主循环用）。
        """
        if not req.source_text.strip():
            raise HTTPException(status_code=400, detail="source_text 不能为空")
        mode = req.mode if req.mode in ("writing", "main") else "writing"
        candidates = skill_generator.generate(req.source_text, req.hint, req.max_items, mode=mode)
        if not candidates:
            raise HTTPException(status_code=502, detail="提炼失败（无有效候选）")
        # 去重：与现有 skill 名比对（避免重复生成）
        existing_names = {s.name for s in skills.list_skills()}
        fresh = [c for c in candidates if c["name"] not in existing_names]
        return {"candidates": fresh, "existing_skills": sorted(existing_names)}

    @app.post("/api/templates/generate", response_model=dict[str, object])
    def generate_template(req: TemplateGenerateIn) -> dict[str, object]:
        """S69：从书提炼剧情模式模板候选（人工确认后走 /api/templates/import 入库）。

        输入多章/全书片段 → 跨章结构归纳 → 模板四要素候选；
        与 /api/skills/generate 的区别：输出供探索 template 来源派生方向（S68 接线）。
        """
        if not req.source_text.strip():
            raise HTTPException(status_code=400, detail="source_text 不能为空")
        candidates = skill_generator.generate(req.source_text, req.hint, req.max_items, mode="plot")
        if not candidates:
            raise HTTPException(status_code=502, detail="提炼失败（无有效候选）")
        # 去重：与现有模板库（L2+L3）名比对
        existing_names = {t.name for t in templates_external.all()}
        fresh = [c for c in candidates if c["name"] not in existing_names]
        return {"candidates": fresh, "existing_templates": sorted(existing_names)}

    @app.get("/api/skills", response_model=list[dict[str, Any]])
    def list_skills() -> list[dict[str, Any]]:
        """全部写作技巧。"""
        return [s.to_dict() for s in skills.list_skills()]

    @app.post("/api/skills", response_model=dict[str, Any])
    def add_skill(req: WritingSkillIn) -> dict[str, Any]:
        s = skills.add(req.name, req.description, req.content, req.example, req.tags, req.target)
        return s.to_dict()

    # -- S54 候选草稿（后台自动生成 → 人工确认转正/拒绝）——须在 {skill_id} 路由前 --
    @app.get("/api/skills/drafts", response_model=list[dict[str, Any]])
    def list_skill_drafts() -> list[dict[str, Any]]:
        """skill 候选草稿（B 心智联动/C 信号驱动自动生成，未生效）。"""
        return skills.list_drafts()

    @app.post("/api/skills/drafts/{draft_id}/promote", response_model=dict[str, Any])
    def promote_skill_draft(draft_id: str) -> dict[str, Any]:
        """人工确认：草稿转正进 writing_skills（生效）。"""
        s = skills.promote_draft(draft_id)
        if s is None:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return s.to_dict()

    @app.delete("/api/skills/drafts/{draft_id}", response_model=dict[str, bool])
    def delete_skill_draft(draft_id: str) -> dict[str, bool]:
        ok = skills.delete_draft_by_id(draft_id)
        if not ok:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return {"ok": True}

    @app.patch("/api/skills/{skill_id}", response_model=dict[str, Any])
    def patch_skill(skill_id: str, req: WritingSkillPatch) -> dict[str, Any]:
        s = skills.update(
            skill_id,
            req.name,
            req.description,
            req.content,
            req.example,
            req.tags,
            req.target,
            req.enabled,
        )
        if s is None:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return s.to_dict()

    @app.delete("/api/skills/{skill_id}", response_model=dict[str, bool])
    def delete_skill(skill_id: str) -> dict[str, bool]:
        ok = skills.delete(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return {"ok": True}

    @app.get("/api/bias", response_model=list[dict[str, Any]])
    def list_bias() -> list[dict[str, Any]]:
        """AI 倾向档案（双向黑盒解法）。"""
        return bias.list()

    @app.post("/api/bias", response_model=dict[str, Any])
    def add_bias(req: BiasIn) -> dict[str, Any]:
        """新增倾向自述（AI 声明或用户修正）。"""
        return bias.add(req.content, req.source)

    @app.delete("/api/bias/{bias_id}")
    def delete_bias(bias_id: str) -> dict[str, bool]:
        bias.delete(bias_id)
        return {"ok": True}

    # ------------------------------------------------------------------
    # S10 低摩擦交互层 + T2 阶段 5/6（候选卡堆/方向声明/改写渐变/一章收尾）
    # ------------------------------------------------------------------
    @app.post("/api/chat/direction", response_model=dict[str, str])
    def chat_direction(req: DirectionIn) -> dict[str, str]:
        """阶段 5 方向声明：AI 只声明"我准备写：…"不写正文（摩擦前置，用户 0.5s 确认）。"""
        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        prompt = (
            "你是小说写作智能体。用户将让你写一段内容。"
            "在动笔前，先输出【方向声明】——一句话说明你准备写什么、怎么切入"
            "（像'我准备写：主角推开钟表铺的门，雨声里老周欲言又止'）。"
            "只输出声明，不要写正文。\n\n"
            f"用户要求：{req.prompt}{ctx}"
        )
        out = model.respond([Message(role="system", content=prompt)], [])
        direction = out.text.strip()
        if not direction.startswith("【方向声明】"):
            direction = f"【方向声明】{direction}"
        return {"direction": direction}

    @app.post("/api/chat/candidates", response_model=dict[str, object])
    def chat_candidates(req: CandidatesIn) -> dict[str, object]:
        """候选卡堆：并行生成 N 个差异化候选（上下文隔离→真多样性，机制 1/4）。"""
        from concurrent.futures import ThreadPoolExecutor

        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        n = max(2, min(4, req.n))
        styles = ["平实叙事", "强画面感", "悬念张力", "细腻心理"]

        def _one(i: int) -> str:
            prompt = (
                f"你是小说写作智能体。按风格「{styles[i % len(styles)]}」写下面要求的一段正文"
                f"（约 150-250 字，直接输出正文，不要解释）。\n\n用户要求：{req.prompt}{ctx}"
            )
            out = model.respond([Message(role="system", content=prompt)], [])
            return out.text.strip()

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(_one, range(n)))
        candidates = [
            {"id": f"c{i + 1}", "style": styles[i % len(styles)], "text": results[i]}
            for i in range(n)
        ]
        return {"candidates": candidates}

    @app.post("/api/chat/rewrite", response_model=dict[str, str])
    def chat_rewrite(req: RewriteIn) -> dict[str, str]:
        """改写渐变条（机制 4）：保原味↔大幅改，温度+指令差异化。"""
        mode = req.mode if req.mode in ("subtle", "balanced", "bold") else "balanced"
        temp_map = {"subtle": 0.3, "balanced": 0.7, "bold": 1.1}
        instruct_map = {
            "subtle": "尽量保留原文结构与表达，只做轻微润色",
            "balanced": "在保留原意的基础上改写，语言更生动",
            "bold": "大胆重构：换切入角度、换句式节奏、大幅改变表达",
        }
        prompt = (
            "你是小说写作智能体。改写下面这段正文。"
            f"要求：{instruct_map[mode]}。直接输出改写后的正文，不要解释。\n\n原文：\n{req.text[:3000]}"
        )
        # 渐变条温度映射：保原味=低温，大幅改=高温（仅真实模型生效）
        rewrite_model: Any = model
        if isinstance(model, DeepSeekModel):
            rewrite_model = DeepSeekModel(temperature=temp_map[mode])
        out = rewrite_model.respond(
            [Message(role="system", content=prompt)],
            [],
        )
        return {"rewritten": out.text.strip(), "mode": mode}

    @app.post("/api/chapters/{chapter_id}/wrapup", response_model=dict[str, object])
    def chapter_wrapup(chapter_id: str) -> dict[str, object]:
        """阶段 6 一章收尾：一致性摘要卡 + 下一章衔接提示（不自动评审，轻量）。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        prompt = (
            "你是小说写作智能体。读下面这章正文，输出两句：\n"
            "1. 一致性摘要（一句话概括本章发生了什么、推进了什么）\n"
            "2. 下一章衔接提示（建议下一章推进什么，如'推进角色弧/揭开伏笔'，给一个具体方向）\n"
            '格式（严格 JSON）：{"summary": "…", "next_hint": "…"}\n\n'
            f"章节《{ch.title}》正文：\n{ch.content[:4000]}"
        )
        out = model.respond([Message(role="system", content=prompt)], [])
        import re

        cleaned = out.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        summary, hint = "", ""
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                if isinstance(data, dict):
                    summary = str(data.get("summary", ""))
                    hint = str(data.get("next_hint", ""))
            except json.JSONDecodeError:
                pass
        # 图谱统计（本章涉及的实体）
        involved = graph_verifier.facts_for("main", ch.content[:2000])
        # S31：主线钩子检查——作者承诺的剧情钩子仍未回收的（轻量提示，建议非门禁）
        # 老龄化：带开放时长（中性事实，不设阈值不评判）
        open_hooks = plots.open_must("main", current_order=ch.order_index) or []
        hook_check = (
            [
                {
                    "content": h.content[:60],
                    "chapter_ref": h.chapter_ref,
                    "category": h.category,
                    "open_since": (
                        ch.order_index - h.planted_order if h.planted_order > 0 else None
                    ),
                }
                for h in open_hooks
            ][:8]
            if open_hooks
            else []
        )
        return {
            "chapter_id": chapter_id,
            "title": ch.title,
            "summary": summary or out.text.strip()[:100],
            "next_hint": hint,
            "graph_entities": [f.entity.name for f in involved][:10],
            "open_hooks": hook_check,  # S31：仍未回收的主线钩子（提醒，不阻断）
        }

    # -----------------------------------------------------------------------
    # S48 工作区：每项目一路径（上传存档/章节 md/卡片），md 文件为章节权威
    # -----------------------------------------------------------------------
    @app.get("/api/workspace", response_model=dict[str, Any])
    def workspace_overview() -> dict[str, Any]:
        """项目工作区结构总览：上传存档 / 章节文件 / 卡片。"""
        return workspace.describe("main")

    @app.post("/api/workspace/import", response_model=dict[str, Any])
    def workspace_import_chapters() -> dict[str, Any]:
        """S48：扫描章节 md 文件 → 同步入库（人工直接编辑 md 后调用）。

        仅内容变化才 upsert（版本历史只在变化时记录）。
        权威始终在文件——import 是"文件 → 库镜像"的单向同步。
        """
        imported: list[dict[str, Any]] = []
        for item in workspace.list_chapter_files("main"):
            content = workspace.read_chapter("main", item["order"], item["title"])
            if content is None:
                continue
            existing = next(
                (c for c in chapters.list_by_book("main") if c.title == item["title"]),
                None,
            )
            changed = existing is None or existing.content != content
            if changed:
                line = existing.narrative_line if existing else "main"
                chapters.upsert("main", item["title"], content, item["order"], line)
            imported.append({"title": item["title"], "order": item["order"], "changed": changed})
        return {
            "ok": True,
            "files": len(imported),
            "changed": sum(1 for i in imported if i["changed"]),
            "imported": imported,
        }

    @app.post("/api/upload", response_model=dict[str, Any])
    def upload_to_workspace(req: UploadIn) -> dict[str, Any]:
        """S48：上传原始文件进上传区（存档，不参与操作；后续消化为格式化产物）。

        用 base64 JSON（零新依赖 python-multipart）；前端/agent 都可直接传。
        """
        import base64

        try:
            data = base64.b64decode(req.data_b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"base64 解码失败：{exc}") from exc
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
        dest = workspace.save_upload("main", req.filename, data)
        logger.info("上传存档: %s -> %s", req.filename, dest.name)
        return {"ok": True, "name": dest.name, "path": str(dest), "size": len(data)}

    # -----------------------------------------------------------------------
    # S48-P4 角色推演：低成本多探索 + 选优（复用 explore 并行基建）
    # -----------------------------------------------------------------------
    @app.post("/api/role/card", response_model=dict[str, Any])
    def role_card_upsert(req: RoleCardIn) -> dict[str, Any]:
        """创建/更新角色卡（卡片/角色卡-{name}.md）。"""
        f = workspace.write_card("main", "角色卡", req.name, req.content)
        return {"ok": True, "name": req.name, "file": f.name}

    @app.post("/api/role/play", response_model=dict[str, Any])
    def role_play(req: RolePlayIn) -> dict[str, Any]:
        """角色推演：角色卡 + 当前状态 + 场景 → N 路隔离推演 → 判别选优（作为参考）。"""
        from anyspark.explore import load_role_card

        # 角色卡：文件优先，缺省从图谱实体描述兜底（S63 收敛到 load_role_card 共享）
        role_card, state = load_role_card(workspace, graph, req.role)
        if not role_card.strip():
            raise HTTPException(
                status_code=404, detail=f"角色卡不存在（可先 POST /api/role/card 创建）：{req.role}"
            )
        result = run_roleplay(model, role_card, state=state, scenario=req.scenario, n=req.n)
        if not result.candidates:
            raise HTTPException(status_code=502, detail="推演失败（无有效候选）")
        logger.info(
            "角色推演: %s × %d 路 → best=%s",
            req.role,
            len(result.candidates),
            result.best.strategy if result.best else "?",
        )
        return result.to_dict()

    # -----------------------------------------------------------------------
    # S65 互动推演（独立扩展包 anyspark-play：扮演角色多轮选择推进的推演树）
    # -----------------------------------------------------------------------
    @app.post("/api/play/sessions", response_model=dict[str, Any])
    def play_create(req: PlayCreateIn) -> dict[str, Any]:
        """创建互动推演会话（seed 切入 + 扮演 role → 根节点 scene + 候选行动）。"""
        try:
            return play_engine.create(
                role=req.role,
                seed=req.seed,
                book_id=req.book_id,
                title=req.title,
                max_depth=req.max_depth,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/play/sessions", response_model=list[dict[str, Any]])
    def play_list() -> list[dict[str, Any]]:
        return play_store.list_sessions()

    @app.get("/api/play/sessions/{session_id}", response_model=dict[str, Any])
    def play_get(session_id: str) -> dict[str, Any]:
        session = play_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"推演会话不存在：{session_id}")
        tree = play_store.session_tree(session_id)
        current_id = session["current_node_id"] or ""
        path = play_store.path_to(current_id)
        return {"session": session, "tree": tree, "path": path}

    @app.post("/api/play/sessions/{session_id}/choose", response_model=dict[str, Any])
    def play_choose(session_id: str, req: PlayChooseIn) -> dict[str, Any]:
        """选择候选行动（或自定义输入）→ 结算推进到下一场景。"""
        try:
            return play_engine.choose(
                session_id, option_id=req.option_id or "", custom_text=req.custom_text or ""
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/play/sessions/{session_id}/branch", response_model=dict[str, Any])
    def play_branch(session_id: str, req: PlayBranchIn) -> dict[str, Any]:
        """回溯分叉：回到指定节点重新生成一批候选行动（原选项保留）。"""
        try:
            return play_engine.branch(session_id, req.node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/play/sessions/{session_id}/stop", response_model=dict[str, Any])
    def play_stop(session_id: str) -> dict[str, Any]:
        """终止推演会话。"""
        try:
            return play_engine.stop(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/play/sessions/{session_id}/export", response_model=dict[str, Any])
    def play_export(session_id: str) -> dict[str, Any]:
        """当前路径导出灵感卡 md（接写正文参考）。"""
        try:
            md = play_engine.export_markdown(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"session_id": session_id, "markdown": md}

    @app.get("/api/review/reviewers", response_model=list[dict[str, object]])
    def review_reviewers_route() -> list[dict[str, object]]:
        """S65：列出评审团评审员（含人设/维度/激活态）。激活改 YAML（内容资产）。"""
        return review_panel.list_reviewers()

    @app.post("/api/review/panel", response_model=dict[str, object])
    async def review_panel_route(req: ReviewPanelRequest) -> dict[str, object]:
        """S65：拟人化评审团——并发评审 + 主席汇总裁决报告。



        自动组装外部上下文：check_report（规则引擎硬伤清单）+ foreshadow（关键点图谱）。

        与 /api/check 的分工：check=确定性硬伤（客观）；review=人格化评价（体验）。

        """

        text, chapter_ref = req.text, req.chapter_ref

        if not text.strip() and chapter_ref:
            ch = next(
                (c for c in chapters.list_by_book(req.book_id) if c.title == chapter_ref),
                None,
            )

            if ch is None:
                raise HTTPException(status_code=400, detail=f"章节不存在: {chapter_ref}")

            text, chapter_ref = ch.content, ch.title

        if not text.strip():
            raise HTTPException(status_code=400, detail="缺少评审文本（text 或 chapter_ref）")

        context: dict[str, str] = {}

        if req.with_check:
            check_report = await asyncio.to_thread(
                run_review, model, chapter_ref or "当前章节", text[:20000]
            )

            context["check_report"] = (
                f"规则引擎硬伤检测（{check_report.hard_count} 处硬伤，供核实）：\n"
                f"{check_report.render()}"
            )

        if req.with_foreshadow:
            with contextlib.suppress(Exception):  # 关键点图谱取不到不阻断评审
                context["foreshadow"] = plots.render(
                    req.book_id, current_order=len(chapters.list_by_book(req.book_id))
                )

        report = await review_panel.run_review(
            model,
            text,
            chapter_ref=chapter_ref or "当前章节",
            reviewer_ids=req.reviewer_ids or None,
            context=context,
        )

        return {
            "overall_score": report.overall_score,
            "summary": report.summary,
            "consensus": report.consensus,
            "divergences": report.divergences,
            "top_suggestions": report.top_suggestions,
            "reviewer_count": report.reviewer_count,
            "valid_count": report.valid_count,
            "errors": report.errors,
            "markdown": report.render(),
            "compact": report.render_compact(),
        }

    # -----------------------------------------------------------------------
    # S48-P4/B 扩展工具注册表：Agent 写的工具，人工批准才生效
    # -----------------------------------------------------------------------
    @app.get("/api/tools", response_model=list[dict[str, Any]])
    def list_ext_tools() -> list[dict[str, Any]]:
        return [t.to_dict() for t in ext_tools.list_all()]

    @app.post("/api/tools/register", response_model=dict[str, Any])
    def register_ext_tool(req: ToolRegisterIn) -> dict[str, Any]:
        """登记扩展工具（status=draft；人工批准后才注入 Agent 工具集）。"""
        try:
            params = json.loads(req.params_json) if req.params_json else []
            if not isinstance(params, list):
                raise ValueError("params 必须是 JSON 数组")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        if not req.code.strip() or "def run(" not in req.code:
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 run(args: dict) -> str 函数"
            )
        t = ext_tools.add(req.name, req.description, params, req.code)
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": "draft",
            "note": "已登记待审——人工批准后才生效",
        }

    @app.post("/api/tools/{tool_id}/approve", response_model=dict[str, Any])
    def approve_ext_tool(tool_id: str) -> dict[str, Any]:
        """人工批准：工具进入 active，后续请求注入 Agent 工具集（无需重启）。"""
        t = ext_tools.set_status(tool_id, "active")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        logger.info("扩展工具已批准生效: %s", t.name)
        return {"ok": True, "id": t.id, "name": t.name, "status": "active"}

    @app.patch("/api/tools/{tool_id}", response_model=dict[str, Any])
    def update_ext_tool(tool_id: str, req: ToolUpdateIn) -> dict[str, Any]:
        """更新扩展工具（S49：改代码/描述/参数）。安全：改后自动回 draft 重新批准。"""
        if req.params_json is not None:
            try:
                params = json.loads(req.params_json)
                if not isinstance(params, list):
                    raise ValueError("params 必须是 JSON 数组")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        else:
            params = None
        if req.code is not None and ("def run(" not in req.code):
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 def run(args: dict) -> str 函数"
            )
        t = ext_tools.update(tool_id, req.name, req.description, params, req.code)
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "note": "已更新，需重新人工批准后才生效",
        }

    @app.post("/api/tools/{tool_id}/disable", response_model=dict[str, Any])
    def disable_ext_tool(tool_id: str) -> dict[str, Any]:
        t = ext_tools.set_status(tool_id, "draft")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True, "id": t.id, "name": t.name, "status": "draft"}

    @app.delete("/api/tools/{tool_id}", response_model=dict[str, Any])
    def delete_ext_tool(tool_id: str) -> dict[str, Any]:
        if not ext_tools.delete(tool_id):
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S48-P5 代码扩展（anyspark-codex）：沙箱执行，固定工具做不了时用
    # -----------------------------------------------------------------------
    @app.post("/api/codex/run", response_model=dict[str, Any])
    def codex_run(req: CodexIn) -> dict[str, Any]:
        """沙箱执行 Python 代码（白名单安全 + 只读数据环境 ws_*：真实统计/自定义分析）。"""
        from anyspark.server.codex import make_data_env, run_code

        return run_code(req.code, req.timeout, data_env=make_data_env(workspace, chapters, graph))

    # -----------------------------------------------------------------------
    # S48-P3 输入消化管线：上传区原始文件 → 格式化区（章节 md / 摘要卡）
    # -----------------------------------------------------------------------
    @app.post("/api/ingest", response_model=dict[str, Any])
    def ingest_upload(req: IngestIn) -> dict[str, Any]:
        """消化上传区文件：长文（多章）拆成章节 md；资料/短文本生成摘要卡。

        原始文件原地不动（存档）；产物进格式化区（章节/ 或 卡片/）。
        多模态（扫描件 OCR/图片理解）明确不做，放未来计划。
        """
        from anyspark.server.pipeline import chapterize, extract_text

        path = workspace.read_upload("main", req.filename)
        if path is None:
            raise HTTPException(status_code=404, detail=f"上传区无此文件：{req.filename}")
        if path.suffix.lower() not in (".txt", ".md", ".markdown", ".docx", ".pdf"):
            raise HTTPException(
                status_code=400, detail="仅支持 txt/md/docx/pdf 文本消化（图片放未来）"
            )
        text = extract_text(path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="无法提取文本（扫描件 OCR 放未来计划）")
        chaps = chapterize(text, fallback_title=path.stem)
        # 判别：mode 强制 / 单章短文本 → 摘要卡；否则拆章
        is_card = req.mode == "card" or (
            req.mode != "chapters" and len(chaps) == 1 and len(text) < 3000
        )
        if is_card:
            digestor = MaterialDigestor(model)
            card = digestor.digest(text)
            saved = materials.save(card)
            card_md = (
                f"# {saved.title}\n\n主题：{saved.topic}\n\n"
                + "要点："
                + "；".join(saved.key_points[:6])
                + "\n设定："
                + "；".join(saved.key_settings[:6])
                + "\n角色："
                + "、".join(saved.characters[:8])
                + "\n术语："
                + "、".join(saved.terms[:8])
            )
            f = workspace.write_card("main", "摘要卡", saved.title, card_md)
            return {
                "ok": True,
                "kind": "card",
                "title": saved.title,
                "card_file": f.name,
                "material_id": saved.id,
            }
        written: list[dict[str, Any]] = []
        for i, ch in enumerate(chaps):
            workspace.write_chapter("main", i, ch["title"], ch["content"])
            chapters.upsert("main", ch["title"], ch["content"], i, "main")
            written.append({"order": i, "title": ch["title"], "chars": len(ch["content"])})
        logger.info("消化: %s → %d 章", req.filename, len(written))
        return {"ok": True, "kind": "chapters", "count": len(written), "chapters": written}

    @app.get("/api/export/book", response_model=None)
    def export_book(format: str = "md") -> Response:
        """全书导出（S48-P3）：txt/md/epub（epub 携带 md 引用的图片）。"""
        from anyspark.server.export import export_epub, export_md, export_txt

        items = chapters.list_by_book("main")
        chs = [{"title": c.title, "content": c.content} for c in items]
        fmt = format if format in ("txt", "md", "epub") else "md"
        if fmt == "epub":
            data = export_epub(
                "AnySpark 作品",
                "AnySpark",
                chs,
                image_dir=workspace.chapters_dir("main"),  # md 引用相对章节目录（../上传/x.png）
            )
            from urllib.parse import quote

            safe = quote("anyspark-book.epub")
            return Response(
                content=data,
                media_type="application/epub+zip",
                headers={
                    "Content-Disposition": (
                        f"attachment; filename=book.epub; filename*=UTF-8''{safe}"
                    )
                },
            )
        body = export_txt(chs) if fmt == "txt" else export_md(chs)
        media = "text/plain; charset=utf-8" if fmt == "txt" else "text/markdown; charset=utf-8"
        from urllib.parse import quote

        safe = quote(f"anyspark-book.{fmt}")
        return Response(
            content=body,
            media_type=media,
            headers={
                "Content-Disposition": (f"attachment; filename=book.{fmt}; filename*=UTF-8''{safe}")
            },
        )

    @app.get("/api/chapters", response_model=list[ChapterOut])
    def list_chapters() -> list[ChapterOut]:
        items = chapters.list_by_book("main")
        return [
            ChapterOut(
                id=c.id,
                book_id=c.book_id,
                title=c.title,
                content=c.content,
                order_index=c.order_index,
                updated_at=c.updated_at,
            )
            for c in items
        ]

    @app.post("/api/chapters", response_model=ChapterOut)
    def create_chapter(req: ChapterCreate) -> ChapterOut:
        """F1：手动新建章节（空正文，order_index=末尾+1；库+md 双写）。"""
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="标题不能为空")
        chs = chapters.list_by_book(req.book_id)
        order = max((c.order_index for c in chs), default=-1) + 1
        ch = chapters.upsert(req.book_id, title, req.content, order)
        workspace.write_chapter(req.book_id, order, ch.title, ch.content)
        return ChapterOut(
            id=ch.id,
            book_id=ch.book_id,
            title=ch.title,
            content=ch.content,
            order_index=ch.order_index,
            updated_at=ch.updated_at,
        )

    @app.get("/api/chapters/{chapter_id}", response_model=ChapterOut)
    def get_chapter(chapter_id: str) -> ChapterOut:
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        return ChapterOut(
            id=ch.id,
            book_id=ch.book_id,
            title=ch.title,
            content=ch.content,
            order_index=ch.order_index,
            updated_at=ch.updated_at,
        )

    @app.put("/api/chapters/{chapter_id}", response_model=ChapterOut)
    def update_chapter(chapter_id: str, req: ChapterUpdate) -> ChapterOut:
        """F2a：稿纸编辑器保存章节内容。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        chapters.upsert(ch.book_id, ch.title, req.content, ch.order_index, ch.narrative_line)
        updated = chapters.get(chapter_id)
        return ChapterOut(
            id=updated.id,
            book_id=updated.book_id,
            title=updated.title,
            content=updated.content,
            order_index=updated.order_index,
            updated_at=updated.updated_at,
        )

    @app.delete("/api/chapters/{chapter_id}", response_model=dict[str, object])
    def delete_chapter(chapter_id: str) -> dict[str, object]:
        """F1：删除章节（库 + md 双写删除）。前端章节树管理需要，属章节 CRUD 补全。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        # 双写：先删 md 权威文件，再删库镜像（幂等，文件不存在不影响）
        workspace.delete_chapter_file(ch.book_id, ch.order_index, ch.title)
        removed = chapters.delete(chapter_id)
        if not removed:
            raise HTTPException(status_code=500, detail="删除失败")
        logger.info("章节删除: %s《%s》", ch.book_id, ch.title)
        return {"ok": True, "id": chapter_id, "title": ch.title}

    @app.post("/api/chapters/{chapter_id}/patch", response_model=dict[str, object])
    def patch_chapter_route(chapter_id: str, req: ChapterPatchIn) -> dict[str, object]:
        """S44：定点编辑（锚点定位段落的插入/删除/替换，不重写整章）。"""
        from anyspark.server.tools_writing import apply_patch

        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        new_content, results = apply_patch(ch.content, req.operations)
        ok_all = all(r.get("ok") for r in results)
        chapters.upsert("main", ch.title, new_content, ch.order_index, ch.narrative_line)
        return {
            "title": ch.title,
            "ok": ok_all,
            "results": results,
            "chars": len(new_content),
        }

    @app.get("/api/chapters/{chapter_id}/export")
    def export_chapter(chapter_id: str, format: str = "txt") -> Response:
        """多格式导出（S11 工具扩展：txt/md）。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        fmt = format if format in ("txt", "md") else "txt"
        body = f"# {ch.title}\n\n{ch.content}\n" if fmt == "md" else f"{ch.title}\n{ch.content}\n"
        media = "text/markdown; charset=utf-8" if fmt == "md" else "text/plain; charset=utf-8"
        # 中文文件名用 RFC 5987 filename*（latin-1 无法直接编码中文）
        from urllib.parse import quote

        safe_name = quote(f"{ch.title}.{fmt}")
        disposition = f"attachment; filename=chapter.{fmt}; filename*=UTF-8''{safe_name}"
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": disposition},
        )

    # ------------------------------------------------------------------
    # 知识图谱（S7：AI 事实源，后台自动维护）
    # ------------------------------------------------------------------
    @app.get("/api/graph/types", response_model=list[dict[str, Any]])
    def list_graph_types() -> list[dict[str, Any]]:
        """实体类型集（S50 内容化：可增删改/开关）。"""
        return graph.list_types("main")

    @app.post("/api/graph/types", response_model=dict[str, Any])
    def add_graph_type(req: GraphTypeIn) -> dict[str, Any]:
        t = graph.add_type(req.name)
        if t is None:
            raise HTTPException(status_code=409, detail=f"类型已存在: {req.name}")
        return t

    @app.patch("/api/graph/types/{type_id}", response_model=dict[str, Any])
    def patch_graph_type(type_id: str, req: GraphTypePatch) -> dict[str, Any]:
        t = graph.set_type_enabled(type_id, req.enabled)
        if t is None:
            raise HTTPException(status_code=404, detail="类型不存在")
        return t

    @app.delete("/api/graph/types/{type_id}", response_model=dict[str, bool])
    def delete_graph_type(type_id: str) -> dict[str, bool]:
        ok = graph.delete_type(type_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类型不存在")
        return {"ok": True}

    @app.get("/api/graph/entities", response_model=list[dict[str, Any]])
    def list_graph_entities(q: str = "", entity_type: str = "") -> list[dict[str, Any]]:
        """图谱实体（可 q 模糊 / entity_type 过滤）。"""
        items = graph.list_entities("main", q=q or None, entity_type=entity_type or None)
        return [e.to_dict() for e in items]

    @app.post("/api/graph/entities", response_model=dict[str, Any])
    def create_graph_entity(req: EntityCreateIn) -> dict[str, Any]:
        """手动创建图谱实体。"""
        e = graph.create_entity("main", req.name, req.entity_type, req.aliases, req.description)
        if e is None:
            raise HTTPException(status_code=409, detail=f"实体已存在: {req.name}")
        return e.to_dict()

    @app.patch("/api/graph/entities/{entity_id}", response_model=dict[str, Any])
    def update_graph_entity(entity_id: str, req: EntityPatchIn) -> dict[str, Any]:
        """手动更新图谱实体。"""
        e = graph.update_entity(
            entity_id,
            name=req.name,
            entity_type=req.entity_type,
            aliases=req.aliases,
            description=req.description,
            state=req.state,
        )
        if e is None:
            raise HTTPException(status_code=404, detail="实体不存在")
        return e.to_dict()

    @app.delete("/api/graph/entities/{entity_id}", response_model=dict[str, bool])
    def delete_graph_entity(entity_id: str) -> dict[str, bool]:
        """手动删除图谱实体（同时删除关联关系）。"""
        ok = graph.delete_entity(entity_id)
        if not ok:
            raise HTTPException(status_code=404, detail="实体不存在")
        return {"ok": True}

    @app.get("/api/graph/relations", response_model=list[dict[str, Any]])
    def list_graph_relations() -> list[dict[str, Any]]:
        return [r.to_dict() for r in graph.list_relations("main")]

    @app.post("/api/graph/relations", response_model=dict[str, Any])
    def create_graph_relation(req: RelationCreateIn) -> dict[str, Any]:
        """手动创建图谱关系（两端实体不存在则自动创建占位）。"""
        r = graph.create_relation(
            "main", req.from_name, req.to_name, req.rel_type, req.description, req.chapter_ref
        )
        if r is None:
            raise HTTPException(status_code=400, detail="创建关系失败")
        return r.to_dict()

    @app.patch("/api/graph/relations/{relation_id}", response_model=dict[str, Any])
    def update_graph_relation(relation_id: str, req: RelationPatchIn) -> dict[str, Any]:
        """手动更新图谱关系。"""
        r = graph.update_relation(relation_id, rel_type=req.rel_type, description=req.description)
        if r is None:
            raise HTTPException(status_code=404, detail="关系不存在")
        return r.to_dict()

    @app.delete("/api/graph/relations/{relation_id}", response_model=dict[str, bool])
    def delete_graph_relation(relation_id: str) -> dict[str, bool]:
        """手动删除图谱关系。"""
        ok = graph.delete_relation(relation_id)
        if not ok:
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"ok": True}

    @app.get("/api/graph/events", response_model=list[dict[str, Any]])
    def list_graph_events() -> list[dict[str, Any]]:
        return [e.to_dict() for e in graph.list_events("main")]

    @app.post("/api/graph/events", response_model=dict[str, Any])
    def create_graph_event(req: EventCreateIn) -> dict[str, Any]:
        """手动创建图谱事件。"""
        e = graph.create_event(
            "main", req.label, req.time_point, req.chapter_ref, req.chapter_order,
            req.description, req.involved
        )
        return e.to_dict()

    @app.patch("/api/graph/events/{event_id}", response_model=dict[str, Any])
    def update_graph_event(event_id: str, req: EventPatchIn) -> dict[str, Any]:
        """手动更新图谱事件。"""
        e = graph.update_event(
            event_id,
            label=req.label,
            time_point=req.time_point,
            chapter_ref=req.chapter_ref,
            chapter_order=req.chapter_order,
            description=req.description,
            involved=req.involved,
        )
        if e is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return e.to_dict()

    @app.delete("/api/graph/events/{event_id}", response_model=dict[str, bool])
    def delete_graph_event(event_id: str) -> dict[str, bool]:
        """手动删除图谱事件。"""
        ok = graph.delete_event(event_id)
        if not ok:
            raise HTTPException(status_code=404, detail="事件不存在")
        return {"ok": True}

    @app.get("/api/graph/context", response_model=dict[str, str])
    def graph_context() -> dict[str, str]:
        """当前时空点已知事实注入块（预览）。"""
        return {"block": graph_injector.build_block("main")}

    @app.post("/api/impact", response_model=dict[str, object])
    def impact_route(req: ImpactIn) -> dict[str, object]:
        """S45：影响分析——改第 N 章（涉及实体）→ 后续受影响章节（连锁修改依据）。"""
        hits = graph.impact_chapters("main", req.chapter_order, req.entities)
        return {"changed_order": req.chapter_order, "impacted": hits, "count": len(hits)}

    # ------------------------------------------------------------------
    # S46 剧情计划（计划→执行：固化章节计划，写作注入，推进标记）
    # ------------------------------------------------------------------
    @app.get("/api/plan", response_model=list[dict[str, Any]])
    def list_plan() -> list[dict[str, Any]]:
        """全部章节计划（按 chapter_order）。"""
        return [p.to_dict() for p in plans.list()]

    @app.post("/api/plan", response_model=dict[str, Any])
    def add_plan(req: ChapterPlanIn) -> dict[str, Any]:
        p = plans.add(req.chapter_order, req.title, req.content)
        return p.to_dict()

    @app.patch("/api/plan/{plan_id}", response_model=dict[str, Any])
    def patch_plan(plan_id: str, req: ChapterPlanPatch) -> dict[str, Any]:
        p = plans.update(plan_id, req.title, req.content, req.status)
        if p is None:
            raise HTTPException(status_code=404, detail="计划不存在")
        return p.to_dict()

    @app.delete("/api/plan/{plan_id}", response_model=dict[str, bool])
    def delete_plan(plan_id: str) -> dict[str, bool]:
        ok = plans.delete(plan_id)
        if not ok:
            raise HTTPException(status_code=404, detail="计划不存在")
        return {"ok": True}

    # ------------------------------------------------------------------
    # S59 叙事树（分叉路径模型）+ 线进度（映射锚）
    # ------------------------------------------------------------------
    @app.get("/api/story/nodes", response_model=list[dict[str, Any]])
    def list_story_nodes(book_id: str = "main") -> list[dict[str, Any]]:
        """全部叙事树节点。"""
        return [n.to_dict() for n in story_tree.list_nodes(book_id)]

    @app.post("/api/story/nodes", response_model=dict[str, Any])
    def add_story_node(req: StoryNodeIn) -> dict[str, Any]:
        """加叙事节点（默认=探索可能性 candidate；kind 可指定 root/main/anchor/subplot）。"""
        n = story_tree.add_node(
            content=req.content,
            book_id=req.book_id,
            parent_id=req.parent_id,
            kind=req.kind,
            chosen=req.chosen,
        )
        return n.to_dict()

    @app.post("/api/story/nodes/{node_id}/choose", response_model=dict[str, Any])
    def choose_story_node(node_id: str) -> dict[str, Any]:
        """选为当前主线（chosen，其他让位）。"""
        n = story_tree.choose(node_id)
        if n is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        return n.to_dict()

    @app.post("/api/story/nodes/{node_id}/anchor", response_model=dict[str, Any])
    def anchor_story_node(node_id: str) -> dict[str, Any]:
        """标记为必经锚点。"""
        n = story_tree.mark_anchor(node_id)
        if n is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        return n.to_dict()

    @app.delete("/api/story/nodes/{node_id}", response_model=dict[str, Any])
    def delete_story_node(node_id: str) -> dict[str, Any]:
        """删除叙事节点（含所有后代）。"""
        ok = story_tree.delete_node(node_id)
        if not ok:
            raise HTTPException(status_code=404, detail="节点不存在")
        return {"ok": True, "id": node_id}

    @app.get("/api/story/tree", response_model=dict[str, Any])
    def story_tree_view(book_id: str = "main") -> dict[str, Any]:
        """树 + 线进度的注入视图（预览/调试）。"""
        return {
            "nodes": [n.to_dict() for n in story_tree.list_nodes(book_id)],
            "threads": [t.to_dict() for t in story_threads.list_threads(book_id)],
            "render": story_tree.render_tree(book_id),
            "thread_render": story_threads.render_threads(book_id),
        }

    @app.post("/api/story/threads", response_model=dict[str, Any])
    def add_story_thread(req: StoryThreadIn) -> dict[str, Any]:
        """声明/升级一条线（预定义或涌现后手动确认）。"""
        t = story_threads.add(
            name=req.name,
            book_id=req.book_id,
            content=req.content,
            progress=req.progress,
            role=req.role,
            node_id=req.node_id,
        )
        return t.to_dict()

    @app.get("/api/story/threads", response_model=list[dict[str, Any]])
    def list_story_threads(book_id: str = "main") -> list[dict[str, Any]]:
        return [t.to_dict() for t in story_threads.list_threads(book_id)]

    @app.patch("/api/story/threads/{thread_id}", response_model=dict[str, Any])
    def patch_story_thread(thread_id: str, req: StoryThreadPatch) -> dict[str, Any]:
        """更新线进度（映射锚）/ 完成。"""
        t = story_threads.get(thread_id)
        if t is None:
            raise HTTPException(status_code=404, detail="线不存在")
        if req.progress is not None:
            t = story_threads.update_progress(thread_id, req.progress)
        if req.status == "done":
            t = story_threads.mark_done(thread_id)
        return (t or story_threads.get(thread_id)).to_dict()  # type: ignore[union-attr]

    @app.post("/api/graph/extract", response_model=dict[str, int])
    def graph_extract_route(req: GraphExtractIn) -> dict[str, int]:
        """手动抽取一章入库（真实 LLM；write_chapter 后已自动，此为补抽/重抽）。"""
        existing = [e.to_dict() for e in graph.list_entities("main")]
        ext = graph_extractor.extract(req.chapter_ref, req.text, existing)
        chs = chapters.list_by_book("main")
        order = next((c.order_index for c in chs if c.title == req.chapter_ref), len(chs))
        graph.ingest_chapter("main", req.chapter_ref, order, ext)
        return {
            "entities": len(ext.entities),
            "relations": len(ext.relations),
            "events": len(ext.events),
        }

    # ------------------------------------------------------------------
    # S59 工作流 API（可选增强，默认关；模板与书解耦可迁移）
    # ------------------------------------------------------------------
    @app.get("/api/workflows", response_model=list[dict[str, Any]])
    def list_workflows() -> list[dict[str, Any]]:
        return workflow_store.list_templates()

    @app.post("/api/workflows", response_model=dict[str, Any])
    def create_workflow(req: WorkflowIn) -> dict[str, Any]:
        wf = WorkflowDef.from_dict(
            {
                "name": req.name,
                "description": req.description,
                "nodes": req.nodes,
                "edges": req.edges,
            }
        )
        errors = wf.validate()
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        workflow_store.add_template(wf)
        return wf.to_dict()

    @app.post("/api/workflows/generate", response_model=dict[str, Any])
    def generate_workflow(req: WorkflowGenerateIn) -> dict[str, Any]:
        """AI 生成工作流候选 → 草稿表（未生效，人工确认 promote 转正）。"""
        try:
            wf = workflow_generator.generate(req.goal)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        workflow_store.add_draft(wf, hint=req.goal)
        return wf.to_dict()

    @app.get("/api/workflows/drafts", response_model=list[dict[str, Any]])
    def list_workflow_drafts() -> list[dict[str, Any]]:
        return workflow_store.list_drafts()

    @app.post("/api/workflows/drafts/{draft_id}/promote", response_model=dict[str, Any])
    def promote_workflow_draft(draft_id: str) -> dict[str, Any]:
        wf = workflow_store.promote_draft(draft_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return wf.to_dict()

    @app.delete("/api/workflows/drafts/{draft_id}", response_model=dict[str, bool])
    def delete_workflow_draft(draft_id: str) -> dict[str, bool]:
        if not workflow_store.delete_draft(draft_id):
            raise HTTPException(status_code=404, detail="草稿不存在")
        return {"ok": True}

    @app.get("/api/workflows/tasks", response_model=list[dict[str, Any]])
    def list_workflow_tasks() -> list[dict[str, Any]]:
        return workflow_store.list_tasks()

    @app.get("/api/workflows/tasks/{task_id}", response_model=dict[str, Any])
    def get_workflow_task(task_id: str) -> dict[str, Any]:
        task = workflow_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    @app.post("/api/workflows/tasks/{task_id}/approve", response_model=dict[str, Any])
    def approve_workflow_task(task_id: str, req: dict[str, str]) -> dict[str, Any]:
        """approval 节点人工确认：{"decision": "ok"|"reject"}。"""
        try:
            return workflow_engine.approve(task_id, decision=req.get("decision", "ok"))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/workflows/{workflow_id}", response_model=dict[str, Any])
    def get_workflow(workflow_id: str) -> dict[str, Any]:
        wf = workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf.to_dict()

    @app.delete("/api/workflows/{workflow_id}", response_model=dict[str, bool])
    def delete_workflow(workflow_id: str) -> dict[str, bool]:
        if not workflow_store.delete_template(workflow_id):
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"ok": True}

    @app.post("/api/workflows/{workflow_id}/run", response_model=dict[str, Any])
    def run_workflow(workflow_id: str, req: WorkflowRunIn) -> dict[str, Any]:
        """运行工作流：冻结定义快照 → 后台线程执行（不阻塞请求）。"""
        wf = workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        task_id = workflow_store.create_task(wf, book_id=req.book_id, template_id=workflow_id)

        def _run() -> None:
            try:
                workflow_engine.run_task(task_id)
            except Exception as exc:
                logger.warning("工作流后台执行异常 %s: %s", task_id, exc)

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "queued"}

    return app


app = build_app()
