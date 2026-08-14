"""
anyspark.server.deps — AppDeps 组合根契约（S80 拆分）。

build_app() 装配的所有 store / engine / 进程内共享状态收敛为单个 dataclass，
router 工厂函数 make_xxx_router(deps: AppDeps) 统一注入。行为零变化：
字段名与 build_app 内闭包变量名一致，router 内 deps.xxx 等价于原闭包引用。

进程内共享状态（必须单例，随 deps 传递，不能每 router 重建）：
- active_tokens / active_agents / active_lock：chat 取消与插话
- bg_queue：后台任务队列（章节抽取/提炼/摘要）
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from anyspark.align import (
    AgencyStore,
    BiasStore,
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
)
from anyspark.core import Agent, CancellationToken, Model
from anyspark.explore import DimensionStore, ProjectArchive
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.library import LibraryStore
from anyspark.models.mode import ModeResolver, ModeStore
from anyspark.models.registry import ModelProvider, ModelRegistry
from anyspark.play import PlayEngine, PlayStore
from anyspark.review import ReviewPanel
from anyspark.server.context import TokenBudget
from anyspark.server.recorder import RunRecorder
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
    MaterialDigestor,
    MaterialStore,
    PlotGenerator,
    PlotResolver,
    PlotStore,
)
from anyspark.workflow import WorkflowEngine, WorkflowGenerator, WorkflowStore


@dataclass
class BgTask:
    """后台任务（S62：取代元组魔法派发——kind 字段 + 类型化负载，新增任务类型只加一条）。"""

    kind: str  # chapter|refine|skill_drafts|summarize
    title: str = ""
    content: str = ""
    order: int = 0
    line: str = "main"
    book_id: str = "main"  # S85：章节抽取按书隔离（手动编辑挂任务用）
    conv_id: str = ""
    ids: list[str] = field(default_factory=list)
    instruction: str = ""


@dataclass
class AppDeps:
    """组合根依赖契约：build_app 装配 → 各 router 注入。"""

    # --- stores ---
    store: SqliteConversationStore
    chapters: ChapterStore
    ext_tools: Any  # ExtensionToolStore（类型在 server.tools_extensions）
    manual: ManualStore
    signals: SignalStore
    archive: ProjectArchive
    dim_store: DimensionStore
    materials: MaterialStore
    plots: PlotStore
    models: ModelRegistry
    mode_store: ModeStore
    mode_resolver: ModeResolver
    memory_store: MemoryStore
    story_tree: StoryTreeStore
    story_threads: StoryThreadStore
    graph: GraphStore
    agency: AgencyStore
    bias: BiasStore
    settings: WorldSettingStore
    skills: WritingSkillStore
    plans: StoryPlanStore
    workflow_store: WorkflowStore
    play_store: PlayStore
    library: LibraryStore

    # --- engines / generators ---
    mind_planner: MindPlanner
    signal_collector: SignalCollector
    provider: ModelProvider
    model: Model
    summarizer: SessionSummarizer
    plot_generator: PlotGenerator
    plot_resolver: PlotResolver
    preference_extractor: PreferenceExtractor
    skill_generator: SkillGenerator
    graph_extractor: GraphExtractor
    graph_injector: GraphInjector
    graph_verifier: GraphVerifier
    budget: TokenBudget
    window: int  # token 预算窗口（模型上下文窗口，activate_model 校验用）

    # --- 其他（无默认值字段必须在默认值字段前） ---
    workspace: Workspace
    recorder: RunRecorder
    db_path: str  # 数据库文件路径（stats 等用）

    # --- 可选引擎（默认 None） ---
    material_digestor: MaterialDigestor | None = None
    workflow_generator: WorkflowGenerator | None = None
    workflow_engine: WorkflowEngine | None = None
    play_engine: PlayEngine | None = None
    review_panel: ReviewPanel | None = None

    # --- 进程内共享状态（单例，不能每 router 重建） ---
    active_tokens: dict[str, CancellationToken] = field(default_factory=dict)
    active_agents: dict[str, Agent] = field(default_factory=dict)
    active_lock: threading.Lock = field(default_factory=threading.Lock)
    # S99：会话级消息队列（排队接力第一步；自动消费=第二步 SSE 循环化）
    conv_queues: dict[str, list[dict[str, str]]] = field(
        default_factory=dict
    )  # conv_id -> [{id, text}]
    queue_lock: threading.Lock = field(default_factory=threading.Lock)
    bg_queue: queue.Queue[BgTask] = field(default_factory=queue.Queue)
