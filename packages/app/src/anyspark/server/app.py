"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import contextlib
import os
import queue
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

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
from anyspark.check import run_review
from anyspark.core import (
    Agent,
    CancellationToken,
    Message,
    Model,
    RetryingModel,
)
from anyspark.explore import (
    DimensionStore,
    ProjectArchive,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.library import LibraryStore
from anyspark.library.search import search_reference_books
from anyspark.models.mode import ModeResolver, ModeStore
from anyspark.models.registry import (
    ModelProvider,
    ModelRegistry,
)
from anyspark.play import PlayEngine, PlayStore
from anyspark.review import ReviewPanel
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.recorder import RunRecorder
from anyspark.server.routes_agency import make_agency_router
from anyspark.server.routes_books import make_books_router
from anyspark.server.routes_chapters import make_chapters_router
from anyspark.server.routes_chat import make_chat_router
from anyspark.server.routes_check import make_check_router
from anyspark.server.routes_conversations import make_conversations_router
from anyspark.server.routes_explore import make_explore_router
from anyspark.server.routes_graph import make_graph_router
from anyspark.server.routes_library import make_library_router
from anyspark.server.routes_mind import make_mind_router
from anyspark.server.routes_mode import make_mode_router
from anyspark.server.routes_play import make_play_router
from anyspark.server.routes_plot import make_plot_router
from anyspark.server.routes_settings import make_settings_router
from anyspark.server.routes_skills import make_skills_router
from anyspark.server.routes_story import make_story_router
from anyspark.server.routes_tools import make_tools_router
from anyspark.server.routes_workflow import make_workflow_router
from anyspark.server.routes_workspace import make_workspace_router
from anyspark.server.schemas import (
    DEFAULT_SYSTEM as DEFAULT_SYSTEM,  # re-export（test_recorder 兼容）
)
from anyspark.server.tasks import start_bg_worker
from anyspark.server.tools_domain import render_reference_knowledge
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
)
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
    MaterialStore,
    PlotGenerator,
    PlotResolver,
    PlotStore,
)
from anyspark.workflow import (
    NodeResult,
    RunContext,
    WorkflowEngine,
    WorkflowGenerator,
    WorkflowStore,
    wait_approval,
)

# 数据根：项目 data/（gitignored，绝不入库）
# S109 打包改造：PyInstaller frozen 下——资源根=_MEIPASS（只读：frontend dist/.env 模板/reviewers），
# 数据根=exe 同目录 /data（用户可写、可整体拷贝）；开发模式保持项目 data/。


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _runtime_root() -> Path:
    """资源根：frozen → PyInstaller 解包目录（只读）；开发 → 项目根。"""
    if _is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[5]


def _data_root() -> Path:
    """数据根：frozen → exe 同目录 /data（可写、可拷贝、可见）；开发 → 项目 data/。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[5] / "data"


PROJECT_ROOT = _runtime_root()
DATA_DIR = _data_root()
DB_PATH = DATA_DIR / "anyspark.db"


# S128（PLAN-SKILL-UNIFY 阶段 2）：templates（ExternalLibrary）并入 skill 表。
# 物理并入：L2 默认模板（DEFAULT_TEMPLATES）+ L3 外部模板（templates_external 表）
# 迁移为 skill 表 type=plot 条目——四要素（granularity/position/function/params）
# 与 layer（default/external）存 ext 扩展 JSON；探索消费方改读 skills.plot_skills()。
# 幂等同名跳过（可重复启动/迁移不重复），ExternalLibrary 类保留供独立测试。
def _migrate_templates_to_skills(skills: WritingSkillStore, db_path: str | Path) -> None:
    import json as _json

    from anyspark.template import ExternalLibrary, default_library

    existing = {s.name for s in skills.list_skills()}
    lib = ExternalLibrary(db_path)
    try:
        # L2 默认模板（代码内嵌）+ L3 外部模板（templates_external 表）合并迁移
        for t in [*default_library(), *lib.list_external()]:
            if t.name in existing:
                continue
            skills.add(
                name=t.name,
                description=t.description,
                content=f"剧情模式：{t.description}",
                tags="剧情模式",
                type="plot",
                ext=_json.dumps(
                    {
                        "granularity": t.granularity,
                        "position": t.position,
                        "function": t.function,
                        "params": t.params,
                        "layer": t.layer,
                    },
                    ensure_ascii=False,
                ),
            )
            existing.add(t.name)
    finally:
        lib.close()


# S129（WORKFLOW 第 1 批）：预置拆书 workflow 模板。
# skill_refine(mode=book) 的多步 LLM 管道声明化为 workflow：
#   prep（script 选章分批）→ loop[decompose agent 拆批 + accumulate script 累计]
#     → merge agent（归并书名方法论）→ skeleton agent（骨架扫描）
#     → refine agent（定点精读架构技法）→ plot agent（剧情模式双落）
#     → finish script（解析三路候选落草稿）
# 确定性步骤（选章/分批/累计/精读输入组装/落草稿）作 script 节点；LLM 步骤作
# agent 节点（可断点恢复/可重试/节点级记账）。prompt 文本种子时从 skillgen 常量
# 内联进模板（模板=数据：用户改节点指令即改拆解要求，不碰代码）。
def _seed_book_refine_template(workflow_store: Any) -> None:
    """预置拆书/批量/轻流程 workflow 模板（WORKFLOW 第 1+2+3 批）。"""
    from anyspark.workflow import WorkflowDef

    existing = {t["name"] for t in workflow_store.list_templates()}
    # S152：预置模板保护——旧库已存在的同名模板补标 builtin（迁移），
    # 使工具收编执行路径/安全网载体全部受保护
    _preset_names = (
        "拆书提炼",
        "批量改写",
        "批量审读",
        "图谱抽取",
        "信号提炼",
        "会话摘要",
        "章节加料",
        "资料调研",
    )
    for name in _preset_names:
        workflow_store.mark_builtin_by_name(name)
    if "拆书提炼" not in existing:
        _seed_refine_template(workflow_store, WorkflowDef)
    if "批量改写" not in existing:
        _seed_batch_rewrite_template(workflow_store, WorkflowDef)
    if "批量审读" not in existing:
        _seed_batch_review_template(workflow_store, WorkflowDef)
    if "图谱抽取" not in existing:
        _seed_graph_extract_template(workflow_store, WorkflowDef)
    if "信号提炼" not in existing:
        _seed_signal_refine_template(workflow_store, WorkflowDef)
    if "会话摘要" not in existing:
        _seed_conversation_summarize_template(workflow_store, WorkflowDef)
    if "章节加料" not in existing:
        _seed_enrich_template(workflow_store, WorkflowDef)


def _seed_graph_extract_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S134（WORKFLOW 第 3 批）：图谱抽取——逐章 LLM 抽取实体/关系/事件 → 落库。

    非全程（直接出结果，无 approval——轻流程）；集合遍历逐章；落库形态复用
    tasks.extract_chapter（图谱+伏笔回收+学习审查与现后台任务一致）。
    运行参数：chapter_ids（JSON 数组或逗号串，缺省全部章节）。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "图谱抽取",
            "description": (
                "逐章图谱抽取（实体/关系/事件）+ 伏笔回收 + 学习审查。直接出结果；"
                "集合遍历逐章，落库形态与章节落盘自动抽取一致。"
                "运行参数：chapter_ids=章节id数组或逗号串（缺省全部）。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "收集章节",
                    "params": {
                        "function": "batch_prepare",
                        "chapter_ids": "{{chapter_ids}}",
                        "output_key": "chapter_ids",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐章抽取",
                    "params": {
                        "body": ["extract"],
                        "max_iterations": 500,
                        "collection_var": "chapter_ids",
                        "item_var": "cid",
                    },
                },
                {
                    "id": "extract",
                    "kind": "script",
                    "label": "抽取落库",
                    "params": {
                        "function": "chapter_extract",
                        "item_var": "cid",
                        "output_key": "extract_report",
                    },
                },
            ],
            "edges": [{"source": "prep", "target": "loop"}],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"图谱抽取模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_signal_refine_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S134：信号提炼——未处理信号 → 偏好提炼 → 说明书（直接出结果）。"""
    wf = wf_def_cls.from_dict(
        {
            "name": "信号提炼",
            "description": (
                "把未处理的操作信号提炼成说明书偏好条目（增量游标，分批归并）。"
                "直接出结果；复用后台 refine_from_signals 同逻辑。无运行参数。"
            ),
            "nodes": [
                {
                    "id": "refine",
                    "kind": "script",
                    "label": "信号提炼",
                    "params": {"function": "signal_refine", "output_key": "report"},
                }
            ],
            "edges": [],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"信号提炼模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_conversation_summarize_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S134：会话摘要——会话 → 场景记忆摘要（直接出结果）。"""
    wf = wf_def_cls.from_dict(
        {
            "name": "会话摘要",
            "description": (
                "把会话归档成场景记忆（跨会话延续性）。直接出结果；复用后台"
                " summarize_conversation 同逻辑。运行参数：conv_id=会话 id。"
            ),
            "nodes": [
                {
                    "id": "summarize",
                    "kind": "script",
                    "label": "会话摘要",
                    "params": {
                        "function": "conversation_summarize",
                        "conv_id": "{{conv_id}}",
                        "output_key": "report",
                    },
                }
            ],
            "edges": [],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"会话摘要模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_enrich_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S137：章节加料模板——遍历章节 + 定点插入（原文保留，区别于批量改写整章覆盖）。

    加料 = 按自定义指令在章内合适位置插入新内容（扩写环境/内心/对白等），
    不是重写——enrich agent 产出含【插入】标记的内容，stitch script 原位并入原文。
    指令完全参数化（enrich_instruction 运行参数）：非敏感指令（如"扩充环境细节描写"）
    与敏感指令（如"加入亲密场景"）走同一条管道——验证用非敏感指令即可绕开审核坎。
    重操作（写回覆盖）→ loop 前 approval 闸门（W2）。
    运行参数：chapter_ids（缺省全部）+ enrich_instruction=加料指令。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "章节加料",
            "description": (
                "按自定义指令在章节中定点插入新内容（扩写环境/心理/对白/细节等），"
                "原文保留不重写。重操作带确认闸门；逐章集合遍历。"
                "运行参数：chapter_ids=章节id数组或逗号串（缺省全部）；"
                "enrich_instruction=加料指令（如'扩充环境细节描写'）。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "收集章节",
                    "params": {
                        "function": "batch_prepare",
                        "chapter_ids": "{{chapter_ids}}",
                        "output_key": "chapter_ids",
                    },
                },
                {
                    "id": "gate_confirm",
                    "kind": "approval",
                    "label": "确认加料",
                    "params": {"prompt": "章节加料将写回所选章节（旧版进版本历史），确认执行？"},
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐章加料",
                    "params": {
                        "body": ["read", "title", "enrich", "stitch", "save"],
                        "max_iterations": 500,
                        "collection_var": "chapter_ids",
                        "item_var": "cid",
                    },
                },
                {
                    "id": "read",
                    "kind": "script",
                    "label": "读原文",
                    "params": {
                        "function": "chapter_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_text",
                    },
                },
                {
                    "id": "title",
                    "kind": "script",
                    "label": "取标题",
                    "params": {
                        "function": "chapter_title_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_title",
                    },
                },
                {
                    "id": "enrich",
                    "kind": "agent",
                    "label": "生成插入内容",
                    "params": {
                        "instruction": (
                            "按加料指令在本章合适位置**定点插入**新内容，不重写原文。\n"
                            "输出格式：在原文基础上，把要插入的新内容用【插入】…【/插入】标记"
                            "标出（可多处，标在对应位置）；其余原文逐字保留。\n"
                            "【加料指令】{{enrich_instruction}}\n【原章】\n{{chapter_text}}\n"
                            "【插入后的完整正文】"
                        ),
                        "output_key": "enriched",
                    },
                },
                {
                    "id": "stitch",
                    "kind": "script",
                    "label": "合并原文",
                    "params": {
                        "function": "enrich_stitch",
                        "source_var": "chapter_text",
                        "insert_var": "enriched",
                        "output_key": "merged",
                    },
                },
                {
                    "id": "save",
                    "kind": "script",
                    "label": "写回章节",
                    "params": {
                        "function": "write_chapter",
                        "chapter_title": "{{chapter_title}}",
                        "text_key": "merged",
                        "output_key": "saved",
                    },
                },
            ],
            "edges": [
                {"source": "prep", "target": "gate_confirm"},
                {"source": "gate_confirm", "target": "loop"},
            ],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"章节加料模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_refine_template(workflow_store: Any, wf_def_cls: Any) -> None:
    from anyspark.align.skillgen import (
        GENERATE_PROMPT_BOOK,
        GENERATE_PROMPT_PLOT_FROM_SKELETON,
        MERGE_PROMPT_BOOK,
        REFINE_PROMPT,
        SKELETON_PROMPT,
    )

    wf = wf_def_cls.from_dict(
        {
            "name": "拆书提炼",
            "description": (
                "从书库参考书提炼 skill：整本书方法论（文风/节奏/结构/人设/对白/信息投放/钩子）"
                "+ 架构机关技法 + 剧情模式 plot 子条 → 落草稿（人工确认后生效）。"
                "运行参数：library_book_id=书库书 id（reference_lookup 可查）。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "选章分批",
                    "params": {
                        "function": "book_refine_prepare",
                        "library_book_id": "{{library_book_id}}",
                        "output_key": "prepared",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "分批拆解",
                    "params": {
                        "body": ["decompose", "accumulate"],
                        "max_iterations": 24,  # 安全上限（实际=批次集合长度）
                        "collection_var": "prepared",
                        "item_var": "batch",
                    },
                },
                {
                    "id": "decompose",
                    "kind": "agent",
                    "label": "拆解本批",
                    "params": {
                        "instruction": GENERATE_PROMPT_BOOK + "\n（代表批，整章）\n{{batch}}\n",
                        "output_key": "partial",
                    },
                },
                {
                    "id": "accumulate",
                    "kind": "script",
                    "label": "累计批次",
                    "params": {
                        "function": "book_refine_accumulate",
                        "item_var": "partial",
                        "list_var": "partials",
                        "output_key": "partials",
                    },
                },
                {
                    "id": "merge",
                    "kind": "agent",
                    "label": "归并方法论",
                    "params": {
                        "instruction": MERGE_PROMPT_BOOK + "\n{{partials}}\n",
                        "output_key": "merged",
                    },
                },
                {
                    "id": "titles",
                    "kind": "script",
                    "label": "取章标题",
                    "params": {
                        "function": "book_refine_titles",
                        "library_book_id": "{{library_book_id}}",
                        "output_key": "titles_text",
                    },
                },
                {
                    "id": "skeleton",
                    "kind": "agent",
                    "label": "骨架扫描",
                    "params": {
                        "instruction": SKELETON_PROMPT.format(book_name="本书")
                        + "\n{{titles_text}}\n",
                        "output_key": "skeleton_note",
                    },
                },
                {
                    "id": "refine_input",
                    "kind": "script",
                    "label": "精读输入",
                    "params": {
                        "function": "book_refine_refine_input",
                        "note": "{{skeleton_note}}",
                        "library_book_id": "{{library_book_id}}",
                        "output_key": "refine_excerpt",
                    },
                },
                {
                    "id": "refine",
                    "kind": "agent",
                    "label": "定点精读",
                    "params": {
                        "instruction": REFINE_PROMPT.format(book_name="本书")
                        + "\n{{refine_excerpt}}\n",
                        "output_key": "arch_cands",
                    },
                },
                {
                    "id": "plot",
                    "kind": "agent",
                    "label": "剧情模式",
                    "params": {
                        "instruction": GENERATE_PROMPT_PLOT_FROM_SKELETON + "\n{{skeleton_note}}\n",
                        "output_key": "plot_cands",
                    },
                },
                {
                    "id": "finish",
                    "kind": "script",
                    "label": "落草稿",
                    "params": {
                        "function": "book_refine_finish",
                        "merge": "{{merged}}",
                        "arch": "{{arch_cands}}",
                        "plot": "{{plot_cands}}",
                        "refine_excerpt": "{{refine_excerpt}}",
                        "library_book_id": "{{library_book_id}}",
                        "output_key": "finish_report",
                    },
                },
            ],
            "edges": [
                {"source": "prep", "target": "loop"},
                {"source": "loop", "target": "merge"},
                {"source": "merge", "target": "titles"},
                {"source": "titles", "target": "skeleton"},
                {"source": "skeleton", "target": "refine_input"},
                {"source": "refine_input", "target": "refine"},
                {"source": "refine", "target": "plot"},
                {"source": "plot", "target": "finish"},
            ],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"拆书模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_batch_rewrite_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S133：批量改写模板——多章统一指令改写（重操作：loop 前强制 approval 闸门）。

    prep 收集章节集合 → approval 人工确认（覆盖原稿前把关，W2 重操作强制）→
    loop 集合遍历逐章：chapter_by_id 读原文 → agent 按指令改写 → write_chapter 落盘
    （覆盖前旧版进版本历史，与 run_batch_rewrite 一致）。
    运行参数：chapter_ids（JSON 数组或逗号串，缺省全部章节）+ instruction。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "批量改写",
            "description": (
                "多章统一指令改写（改文风/改情节）。覆盖原稿前人工确认闸门；"
                "逐章集合遍历（断点恢复/失败重试）；覆盖前旧版进版本历史。"
                "运行参数：chapter_ids=章节id数组或逗号串（缺省全部）；instruction=改写指令。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "收集章节",
                    "params": {
                        "function": "batch_prepare",
                        "chapter_ids": "{{chapter_ids}}",
                        "output_key": "chapter_ids",
                    },
                },
                {
                    "id": "gate_confirm",
                    "kind": "approval",
                    "label": "确认覆盖",
                    "params": {"prompt": "批量改写将覆盖所选章节（旧版进版本历史），确认执行？"},
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐章改写",
                    "params": {
                        "body": ["read", "title", "rewrite", "save"],
                        "max_iterations": 500,  # 安全上限（实际=章节集合长度）
                        "collection_var": "chapter_ids",
                        "item_var": "cid",
                    },
                },
                {
                    "id": "read",
                    "kind": "script",
                    "label": "读原文",
                    "params": {
                        "function": "chapter_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_text",
                    },
                },
                {
                    "id": "title",
                    "kind": "script",
                    "label": "取标题",
                    "params": {
                        "function": "chapter_title_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_title",
                    },
                },
                {
                    "id": "rewrite",
                    "kind": "agent",
                    "label": "按指令改写",
                    "params": {
                        "instruction": (
                            "按用户指令改写以下章节。保持剧情走向/人物/设定/时间线一致，"
                            "只按指令调整（风格/情节/表达）。直接输出改写后的完整正文，"
                            "不要解释。\n【指令】{{instruction}}\n【原章】\n{{chapter_text}}\n"
                            "【改写后正文】"
                        ),
                        "output_key": "rewritten",
                    },
                },
                {
                    "id": "save",
                    "kind": "script",
                    "label": "写回章节",
                    "params": {
                        "function": "write_chapter",
                        "chapter_title": "{{chapter_title}}",
                        "text_key": "rewritten",
                        "output_key": "saved",
                    },
                },
            ],
            "edges": [
                {"source": "prep", "target": "gate_confirm"},
                {"source": "gate_confirm", "target": "loop"},
            ],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"批量改写模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


def _seed_batch_review_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S133：批量审读模板——多章检测网审读（轻操作：只读不改，无 approval 闸门）。

    prep 收集章节集合 → loop 集合遍历逐章：chapter_by_id 读原文 → review_chapter
    检测网审读。逐章报告落任务 results（断点恢复/失败重试）。
    运行参数：chapter_ids（JSON 数组或逗号串，缺省全部章节）。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "批量审读",
            "description": (
                "多章检测网审读（一致性/动机因果/情感连贯等）。只读不改，无人工闸门；"
                "逐章集合遍历。运行参数：chapter_ids=章节id数组或逗号串（缺省全部）。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "收集章节",
                    "params": {
                        "function": "batch_prepare",
                        "chapter_ids": "{{chapter_ids}}",
                        "output_key": "chapter_ids",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐章审读",
                    "params": {
                        "body": ["read", "title", "review"],
                        "max_iterations": 500,
                        "collection_var": "chapter_ids",
                        "item_var": "cid",
                    },
                },
                {
                    "id": "read",
                    "kind": "script",
                    "label": "读原文",
                    "params": {
                        "function": "chapter_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_text",
                    },
                },
                {
                    "id": "title",
                    "kind": "script",
                    "label": "取标题",
                    "params": {
                        "function": "chapter_title_by_id",
                        "item_var": "cid",
                        "output_key": "chapter_title",
                    },
                },
                {
                    "id": "review",
                    "kind": "script",
                    "label": "检测网审读",
                    "params": {
                        "function": "review_chapter",
                        "chapter_title": "{{chapter_title}}",
                        "output_key": "review_report",
                    },
                },
            ],
            "edges": [{"source": "prep", "target": "loop"}],
        }
    )
    errors = wf.validate()
    if errors:
        raise ValueError(f"批量审读模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)


# S55 #3 注入块分层缓存：stable 块（跨请求不变）按签名缓存，volatile 块每次组装。
# 签名=底层数据内容（任何增删改 → 签名变 → 缓存失效），避免长会话重复渲染。


# 应用装配
# ---------------------------------------------------------------------------


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
    # S109：.env 位置——frozen 下放数据根（exe 同目录，用户可填 key）；缺失时从模板生成
    if _is_frozen():
        env_path = DATA_DIR / ".env"
        if not env_path.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            template = PROJECT_ROOT / ".env.example"
            if template.exists():
                with contextlib.suppress(Exception):
                    env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            logger.warning("已生成 .env 模板（请填入 DeepSeek API Key 后重启）：%s", env_path)
    else:
        env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)
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

    _bg_queue: queue.Queue[BgTask] = queue.Queue()  # 后台任务队列（S28/S40）

    mind_planner = MindPlanner(manual)  # S50 心智模型=会话规划器（不从写作循环注入）
    signal_collector = SignalCollector(signals)
    # S47 运行时模型：注册表（持久化多配置）+ 动态 Provider——
    # 默认装配 RetryingModel(ModelProvider(registry))，所有组件跟随当前激活配置；
    # 测试可注入 fake model（实现 core Model 协议），走共享分支不受影响。
    # 注意：必须在任何依赖 model 的组件（summarizer/plot/提炼器等）之前初始化。
    models = ModelRegistry(real_db)
    # S98 快速模式切换：模式/槽位/任务映射存储 + 解析器；provider 按任务分流（未配回退激活）
    mode_store = ModeStore(real_db)
    mode_resolver = ModeResolver(mode_store, models)
    provider = ModelProvider(models, mode=mode_resolver)
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
    # S128（PLAN-SKILL-UNIFY 阶段 2）：templates（ExternalLibrary）并入 skill 表。
    # 物理并入：L2 默认模板 + L3 外部模板迁移为 type=plot 条目（四要素+layer 存 ext），
    # 探索消费方改读 skills.plot_skills()；幂等同名跳过（可重复启动/迁移不重复）。
    _migrate_templates_to_skills(skills, real_db)
    plans = StoryPlanStore(real_db)  # S46 剧情计划（计划→执行）

    # S59 工作流扩展包（可选增强，默认关）：结构化流程（顺序/分支/循环）+
    # 断点恢复 + AI 生成（草稿→人工确认转正）。runner 由组合根注入：
    # agent 节点=干净单次 LLM 调用；script 节点=确定性函数（read/review）；
    # approval=等待人工。
    workflow_store = WorkflowStore(real_db)
    # S129（WORKFLOW 第 1 批）：预置拆书模板——把 skill_refine(mode=book) 的多步 LLM 管道
    # 声明化为 workflow（确定性步骤=script 节点，LLM 步骤=agent 节点，可断点/可编辑）。
    # prompt 文本在种子时从 skillgen 常量内联（模板=数据，用户可改拆解指令不碰代码）。
    _seed_book_refine_template(workflow_store)
    workflow_generator = WorkflowGenerator(model)
    # S65 互动推演（独立扩展包 anyspark-play）：扮演角色多轮选择推进的推演树
    # S65：拟人化评审团面板（系统评审员随包分发 + 用户自定义覆盖 data/reviewers/）
    # S109：frozen 下系统评审员在 _MEIPASS/reviewers（默认 parents 计算失效）
    review_panel = (
        ReviewPanel(system_dir=PROJECT_ROOT / "reviewers") if _is_frozen() else ReviewPanel()
    )
    try:
        review_panel.add_dir(DATA_DIR / "reviewers")
    except Exception as _rpe:  # 用户目录损坏不影响服务启动
        logger.warning("加载用户评审员失败: %s", _rpe)
    play_store = PlayStore(real_db)
    # S86 参考书库（全局文件区 data/library/ + 关联表）
    library = LibraryStore(real_db)

    def _wf_run_agent(ctx: RunContext, node: Any) -> NodeResult:
        """agent 节点：干净单次 LLM 调用（无对话历史/工具记录——对齐 S56 干净写作）。

        S115 提案 B：params.delegate 存在 → 子 Agent 执行（独立上下文跑完整工具循环，
        工具白名单 scope.tools，预算 budget.max_turns）——工作流=通用固定流程执行器。
        变量插值：instruction/system_prompt 中的 {{var}} 从上游节点输出解析
        （如 {{chapter_text}} = 前序 read_chapter 脚本的产出）——真实链路暴露的
        接缝：AI 生成的流程若不插值，agent 拿不到章节内容。
        """
        if node.params.get("delegate"):
            return _wf_run_subagent(ctx, node)

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
                # S109：工作流章节注入阈值 8000→15000；超限告知边界（直调无工具）
                ch_content = ch.content or ""
                if len(ch_content) > 15000:
                    ch_content = (
                        f"【注意：本章全文 {len(ch.content)} 字，以下仅前 15000 字，"
                        "末尾部分未展示】\n" + ch_content[:15000]
                    )
                instruction = f"【章节正文】\n{ch_content}\n\n{instruction}"
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

    def _wf_run_subagent(ctx: RunContext, node: Any) -> NodeResult:
        """S115 提案 B：子 Agent 执行（独立上下文跑完整工具循环）。

        delegate 配置（节点 params.delegate）：
            {
              "scope": {"tools": [工具名...]},   # 工具白名单（空=全量）
              "budget": {"max_turns": 10},       # 子 Agent 轮数护栏
            }
        - fresh 上下文：InMemoryConversationStore（不落库、不受父会话污染）
        - 复用 core Agent 完整循环（含 S108b 重复检测/取消/工具执行）
        - 产出：turn.text 作为 NodeResult.output（返回父流程，作为一条工具结果）
        """
        from anyspark.server.subagent import run_subagent_task

        instruction = _wf_resolve(str(node.params.get("instruction") or ""), ctx)
        system = _wf_resolve(str(node.params.get("system_prompt") or ""), ctx)
        delegate = node.params.get("delegate") or {}
        scope = delegate.get("scope") or {}
        scope_tools = list(scope.get("tools") or [])
        budget = delegate.get("budget") or {}
        max_turns = int(budget.get("max_turns") or 10)

        r = run_subagent_task(
            deps,
            instruction=instruction,
            system_prompt=system,
            scope_tools=scope_tools or None,
            max_turns=max_turns,
            book_id=ctx.book_id,
        )
        if not r["ok"]:
            return NodeResult(error=r["error"])
        return NodeResult(output=r["output"], token_usage=0)

    def _wf_resolve(text: str, ctx: RunContext) -> str:
        """把 {{var}} 占位符替换为上游节点输出（缺失保留原样）。"""
        import re

        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            val = ctx.results.get(key, "")
            return str(val) if val else f"{{{{{key}}}}}"

        return re.sub(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}", _repl, text)

    # ------------------------------------------------------------------
    # S150（REPAIR-LIST D1）：script 函数拆分——每个 script 独立方法 + 注册表分发
    # （此前 500 行 if/elif 单函数，每阶段加分支持续膨胀）
    _wf_scripts: dict[str, Callable[[RunContext, Any], NodeResult]] = {}

    def _wf_script_noop(ctx: RunContext, node: Any) -> NodeResult:
        # 无操作（AI 生成流程常用来做循环体出口占位）
        return NodeResult(output=str(node.params.get("output_key") or "done"))

    _wf_scripts["noop"] = _wf_script_noop

    def _wf_script_read_chapter(ctx: RunContext, node: Any) -> NodeResult:
        title = _wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
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

    _wf_scripts["read_chapter"] = _wf_script_read_chapter

    def _wf_script_review_chapter(ctx: RunContext, node: Any) -> NodeResult:
        title = _wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
        ch = next((c for c in chapters.list_by_book(ctx.book_id) if c.title == title), None)
        if ch is None:
            return NodeResult(error=f"章节不存在: {title}")
        report = run_review(model, ch.title, ch.content[:20000])
        return NodeResult(output=f"硬伤数: {report.hard_count}\n" + report.render())

    _wf_scripts["review_chapter"] = _wf_script_review_chapter

    def _wf_script_list_chapters(ctx: RunContext, node: Any) -> NodeResult:
        chs = chapters.list_by_book(ctx.book_id)
        if not chs:
            return NodeResult(output="（无章节）")
        return NodeResult(output="\n".join(f"{c.order_index}. {c.title}" for c in chs))

    _wf_scripts["list_chapters"] = _wf_script_list_chapters

    def _wf_script_write_chapter(ctx: RunContext, node: Any) -> NodeResult:
        """写回章节：参数 chapter_title + content（或 {{var}} 引用上游改写结果）。

        content 缺失时取 params.text_key（缺省 'rewritten'）对应的上游输出——
        AI 生成的流程常用：改写 agent 输出 rewritten → write_chapter 脚本落盘。
        chapter_title/content 支持 {{var}} 解析（如 {{chapter_title}} 来自 run params）。
        """
        title = _wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
        content = _wf_resolve(str(node.params.get("content") or ""), ctx)
        if not content:
            text_key = str(node.params.get("text_key") or "rewritten")
            content = str(ctx.results.get(text_key, ""))
        if not title:
            return NodeResult(error="write_chapter 缺 chapter_title")
        if not content.strip():
            return NodeResult(error="write_chapter 无内容（检查 text_key 上游输出）")
        try:
            # S138（B1）：版本 note 携带来源——批量任务写回带任务标识，
            # 供批级回滚（rollback）按来源聚合定位改前快照。
            src_note = (
                f"批量任务/任务{getattr(ctx, 'task_id', '')}"
                if getattr(ctx, "task_id", "")
                else "修改前"
            )
            chs = chapters.list_by_book(ctx.book_id)
            ch = next((c for c in chs if c.title == title), None)
            if ch is None:
                order = len(chs) + 1
                chapters.upsert(ctx.book_id, title, content, order, note=src_note)
            else:
                chapters.upsert(ctx.book_id, title, content, ch.order_index, note=src_note)
                # 双写落盘（工作区 md 权威，与 write_chapter 工具一致）
            try:
                if workspace is not None:
                    order = ch.order_index if ch else (len(chs) + 1)
                    workspace.write_chapter(ctx.book_id, order, title, content)
            except Exception:
                pass  # 库镜像已更新，落盘失败不阻断
            return NodeResult(output=f"已写回章节: {title}")
        except Exception as exc:
            return NodeResult(error=f"写回失败: {exc}")

    _wf_scripts["write_chapter"] = _wf_script_write_chapter

    def _wf_script_read_settings(ctx: RunContext, node: Any) -> NodeResult:
        """读本项目设定档（正典设定）→ 文本块（供 agent 注入，防 OOC）。

        params: keyword 可选（过滤分类/名称/内容）；limit 缺省 40。
        """
        keyword = str(node.params.get("keyword") or "").strip()
        try:
            limit = max(1, min(200, int(str(node.params.get("limit") or "40"))))
        except ValueError:
            limit = 40
        try:
            items = settings.list(ctx.book_id)
        except Exception as exc:
            return NodeResult(error=f"读设定档失败: {exc}")
        lines = []
        for s in items:
            if keyword and keyword.lower() not in f"{s.name} {s.content} {s.category}".lower():
                continue
            # S157：条目内容不截断（设定条目是查证核心信息，写全了却截断没道理）
            lines.append(f"[{s.category}] {s.name or s.content[:30]}：{s.content}")
            if len(lines) >= limit:
                break
        if not lines:
            return NodeResult(output=f"（项目「{ctx.book_id}」设定档无匹配条目）")
        # S157：超限告知（limit 可调，但 agent 需知道还有更多条目）
        if len(items) > len(lines):
            lines.append(
                f"（设定档共 {len(items)} 条，已列 {len(lines)}，可调 limit 或带关键词精查）"
            )
        return NodeResult(output="\n".join(lines))

    _wf_scripts["read_settings"] = _wf_script_read_settings

    def _wf_script_read_graph(ctx: RunContext, node: Any) -> NodeResult:
        """读本项目图谱（人物/地点/伏笔状态 + 关系）→ 文本块（供 agent 注入）。

        params: keyword 可选（实体名/别名匹配）；limit 缺省 20（按出场章数取 Top N）。
        """
        keyword = str(node.params.get("keyword") or "").strip()
        try:
            limit = max(1, min(100, int(str(node.params.get("limit") or "20"))))
        except ValueError:
            limit = 20
        try:
            ents = graph.list_entities(ctx.book_id, q=keyword or None, limit=200)
        except Exception as exc:
            return NodeResult(error=f"读图谱失败: {exc}")
        ents = sorted(ents, key=lambda e: -e.weight)[:limit]
        if not ents:
            return NodeResult(output=f"（项目「{ctx.book_id}」图谱无匹配实体）")
        lines = []
        try:
            rels = graph.list_relations(ctx.book_id, limit=500)
        except Exception:
            rels = []
        for e in ents:
            state = (e.state or e.description or "").strip()
            # S157：状态不截断（图谱实体状态是写作查证核心；实体数由 limit 控制防爆）
            line = f"实体[{e.entity_type}] {e.name}（出场{e.weight}章）" + (
                f"：{state}" if state else ""
            )
            for r in rels:
                if r.from_name == e.name or r.to_name == e.name:
                    line += f"\n  ↳ {r.from_name} {r.rel_type} {r.to_name}"
            lines.append(line)
        return NodeResult(output="\n".join(lines))

    _wf_scripts["read_graph"] = _wf_script_read_graph

    def _wf_script_query_reference(ctx: RunContext, node: Any) -> NodeResult:
        """查参考书（分级检索）：原文片段 + 高级参考书（项目）的图谱/设定知识层。

        params: keyword 必填（支持 {{var}} 解析，如 run params 传 ref_keyword）；
        max_per_book 缺省 3。复用 reference_lookup 分级检索。
        """
        keyword = _wf_resolve(str(node.params.get("keyword") or ""), ctx).strip()
        if not keyword:
            return NodeResult(error="query_reference 缺 keyword")
        try:
            max_per = max(1, min(5, int(str(node.params.get("max_per_book") or "3"))))
        except ValueError:
            max_per = 3

        def _project_files(ref_book_id: str) -> str:
            parts = []
            for ch in chapters.list_by_book(ref_book_id):
                parts.append(f"【{ch.title}】\n{ch.content}")
            return "\n\n".join(parts)

        try:
            res = search_reference_books(
                library,
                ctx.book_id,
                keyword,
                project_files=_project_files,
                max_per_book=max_per,
            )
        except Exception as exc:
            return NodeResult(error=f"参考书检索失败: {exc}")
        lines = [f"参考书命中「{keyword}」："]
        for item in res.get("results", []):
            lines.append(f"——{item['ref_name']}——")
            for h in item.get("hits", []):
                lines.append(f"({h['count']}次) {h['snippet']}")
            # 高级参考书（项目）知识层：图谱/设定
        if library is not None:
            try:
                for ref in library.get_references(ctx.book_id):
                    if ref.get("type") != "project":
                        continue
                    klines = render_reference_knowledge(
                        graph, settings, str(ref.get("id", "")), keyword
                    )
                    if klines:
                        lines.append(f"——项目「{ref.get('id', '?')}」（知识层：图谱/设定）——")
                        lines.extend(klines)
            except Exception:
                pass
        if len(lines) == 1:
            return NodeResult(output=f"参考书中未命中「{keyword}」（含图谱/设定层）。")
        return NodeResult(output="\n\n".join(lines))

    _wf_scripts["query_reference"] = _wf_script_query_reference

    def _wf_script_chapter_extract(ctx: RunContext, node: Any) -> NodeResult:
        """S134（WORKFLOW 第 3 批）：单章图谱抽取+伏笔回收+学习审查。

        复用 tasks.extract_chapter（落库形态与现后台任务一致）：读 chapter_id →
        图谱抽取/伏笔回收/学习审查三合一。params.item_var（缺省 "item"）= chapter_id。
        """
        from anyspark.server import tasks as _tasks

        cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
        if not cid:
            return NodeResult(error="chapter_extract 缺 item（chapter_id）")
        ch = chapters.get(cid)
        if ch is None:
            return NodeResult(error=f"章节不存在: {cid}")
        _tasks.extract_chapter(deps, ctx.book_id, ch.title, ch.content or "", ch.order_index)
        return NodeResult(output=f"图谱抽取完成: 《{ch.title}》")

    _wf_scripts["chapter_extract"] = _wf_script_chapter_extract

    def _wf_script_signal_refine(ctx: RunContext, node: Any) -> NodeResult:
        """S134：信号 → 偏好提炼 → 说明书（复用 tasks.refine_from_signals，增量游标）。"""
        from anyspark.server import tasks as _tasks

        before = len(deps.manual.list("project", "main"))
        _tasks.refine_from_signals(deps)
        after = len(deps.manual.list("project", "main"))
        return NodeResult(output=f"信号提炼完成（说明书 {before}→{after} 条）")

    _wf_scripts["signal_refine"] = _wf_script_signal_refine

    def _wf_script_conversation_summarize(ctx: RunContext, node: Any) -> NodeResult:
        """S134：会话 → 场景记忆摘要（复用 tasks.summarize_conversation）。

        params.conv_id：会话 id（{{var}} 解析）。
        """
        from anyspark.server import tasks as _tasks

        conv_id = _wf_resolve(str(node.params.get("conv_id") or ""), ctx).strip()
        if not conv_id:
            return NodeResult(error="conversation_summarize 缺 conv_id")
        _tasks.summarize_conversation(deps, conv_id)
        return NodeResult(output=f"会话归档摘要完成: {conv_id}")

    _wf_scripts["conversation_summarize"] = _wf_script_conversation_summarize

    def _wf_script_enrich_stitch(ctx: RunContext, node: Any) -> NodeResult:
        """S137：加料拼接——把 agent 生成的插入内容合并进原文（定点插入，原文保留）。

        agent 输出含 【插入】...【/插入】 标记（可多处；带锚点说明）：
          原文……【插入】新增内容【/插入】原文……
        stitch 把标记块原位展开并入原文；未提供完整标记时把插入块追加到章末。
        params：source_var（原章文本变量名，缺省 "chapter_text"）/ insert_var
        （agent 输出变量名，缺省 "enriched"）。输出完整增强版正文。
        """
        import re as _re

        src = str(ctx.var(str(node.params.get("source_var") or "chapter_text")) or "")
        insert = str(ctx.var(str(node.params.get("insert_var") or "enriched")) or "")
        if not src.strip():
            return NodeResult(error="enrich_stitch 缺源章文本（source_var 上游未产出）")
        if not insert.strip():
            return NodeResult(error="enrich_stitch 缺插入内容（insert_var 上游未产出）")
            # 方案 A：agent 已产出带【插入】标记的完整正文 → 直接合并标记块
        if "【插入】" in insert:

            def _expand(m: _re.Match[str]) -> str:
                return m.group(1)

            merged = _re.sub(r"【插入】\s*(.*?)\s*【/插入】", _expand, insert, flags=_re.S)
            if merged.strip():
                return NodeResult(output=merged)
            # 方案 B：agent 只产出纯插入段 → 追加到章末（保原文不丢）
        return NodeResult(output=f"{src.rstrip()}\n\n{insert.strip()}")

    _wf_scripts["enrich_stitch"] = _wf_script_enrich_stitch

    def _wf_script_batch_prepare(ctx: RunContext, node: Any) -> NodeResult:
        """S133（WORKFLOW 第 2 批）：批量任务准备——收集章节 id 集合（遍历源）。

        params：chapter_ids（逗号分隔或 JSON 数组，支持 {{var}} 从 run params 传入）；
        缺省=当前项目全部章节（list_chapters 同源）。输出 JSON 数组供 loop collection_var。
        """
        import json as _json

        raw = _wf_resolve(str(node.params.get("chapter_ids") or ""), ctx).strip()
        ids: list[str] = []
        if raw:
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, list):
                    ids = [str(x) for x in parsed]
            except Exception:
                ids = [x.strip() for x in raw.split(",") if x.strip()]
        if not ids:
            # 缺省全部章节
            ids = [c.id for c in chapters.list_by_book(ctx.book_id)]
        if not ids:
            return NodeResult(error="batch_prepare 无章节（chapter_ids 为空且项目无章节）")
        return NodeResult(output=_json.dumps(ids, ensure_ascii=False))

    _wf_scripts["batch_prepare"] = _wf_script_batch_prepare

    def _wf_script_chapter_by_id(ctx: RunContext, node: Any) -> NodeResult:
        """S133：按 chapter_id 读章节（标题+正文）——loop 集合遍历逐项喂 agent。

        读 params.item_var（缺省 "item"）为 chapter_id，输出「标题\n正文」；
        超长章（>20000）告知边界（对齐 run_batch_rewrite）。
        """
        cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
        if not cid:
            return NodeResult(error="chapter_by_id 缺 item（chapter_id）")
        ch = chapters.get(cid)
        if ch is None:
            return NodeResult(error=f"章节不存在: {cid}")
        ch_content = ch.content or ""
        if len(ch_content) > 20000:
            ch_content = (
                f"【注意：本章全文 {len(ch.content)} 字，以下仅前 20000 字，"
                "末尾部分未展示】\n" + ch_content[:20000]
            )
        return NodeResult(output=f"【{ch.title}】\n{ch_content}")

    _wf_scripts["chapter_by_id"] = _wf_script_chapter_by_id

    def _wf_script_chapter_title_by_id(ctx: RunContext, node: Any) -> NodeResult:
        """S133：按 chapter_id 取章标题（write_chapter 落盘用）。

        读 params.item_var（缺省 "item"）为 chapter_id → 输出标题。
        """
        cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
        if not cid:
            return NodeResult(error="chapter_title_by_id 缺 item（chapter_id）")
        ch = chapters.get(cid)
        if ch is None:
            return NodeResult(error=f"章节不存在: {cid}")
        return NodeResult(output=ch.title)

    _wf_scripts["chapter_title_by_id"] = _wf_script_chapter_title_by_id

    def _wf_script_book_refine_prepare(ctx: RunContext, node: Any) -> NodeResult:
        """S129（WORKFLOW 第 1 批）：拆书准备——从书库读全书 → 选章 → 分批。

        确定性步骤（复用 skillgen 选章/分批逻辑）：
        params.library_book_id：书库书 id（支持 {{var}} 解析，如 run params 传入）
        params.batch_size：每批章数（缺省 4，对齐 skillgen._BATCH_SIZE）
        输出 JSON：{"batches": [...], "titles": [...]}——batches 供 loop collection_var
        遍历，titles 供骨架扫描（章标题轨迹）。
        """
        import json as _json

        from anyspark.align.skillgen import (
            _BATCH_SIZE as _SK_BATCH,
        )
        from anyspark.align.skillgen import (
            _build_batches as _build_batches_fn,
        )
        from anyspark.align.skillgen import (
            _parse_chapters as _parse_chapters_fn,
        )
        from anyspark.align.skillgen import (
            _select_structural_chapters as _select_fn,
        )

        bid = _wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
        if not bid:
            return NodeResult(error="book_refine_prepare 缺 library_book_id")
        try:
            batch_size = max(1, min(8, int(str(node.params.get("batch_size") or _SK_BATCH))))
        except ValueError:
            batch_size = _SK_BATCH
        if library is None:
            return NodeResult(error="书库不可用（未装配）")
        book = library.get_book(bid)
        if book is None:
            return NodeResult(error=f"书库无此书：{bid}")
        source = library.read_book(bid, max_chars=None).strip()
        if not source:
            return NodeResult(error=f"书库《{book['name']}》无内容（先导入文本）")
        chaps = _parse_chapters_fn(source)
        if len(chaps) < 5:  # 无章节结构回退均匀抽样（对齐 generate_book）
            batches = [source]
            titles = []
        else:
            selected = _select_fn(chaps)
            batches = _build_batches_fn(chaps, selected, batch_size)
            titles = [t for t, _ in chaps]
        return NodeResult(
            output=_json.dumps(
                {"batches": batches, "titles": titles, "book_name": book["name"]},
                ensure_ascii=False,
            )
        )

    _wf_scripts["book_refine_prepare"] = _wf_script_book_refine_prepare

    def _wf_script_book_refine_titles(ctx: RunContext, node: Any) -> NodeResult:
        """S129：取全书章标题（骨架扫描输入——标题轨迹无正文）。

        params.library_book_id：书库书 id。输出："第1章 标题\n第2章 标题..."
        （超 _MAX_SKELETON_TITLES 抽稀，对齐 skillgen 骨架扫描）。
        """
        from anyspark.align.skillgen import (
            _MAX_SKELETON_TITLES as _SK_TITLES,
        )
        from anyspark.align.skillgen import (
            _parse_chapters as _parse_chapters_fn,
        )

        bid = _wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
        if not bid:
            return NodeResult(error="book_refine_titles 缺 library_book_id")
        if library is None:
            return NodeResult(error="书库不可用（未装配）")
        book = library.get_book(bid)
        if book is None:
            return NodeResult(error=f"书库无此书：{bid}")
        source = library.read_book(bid, max_chars=None).strip()
        chaps = _parse_chapters_fn(source)
        n = len(chaps)
        if n < 1:
            return NodeResult(output=f"《{book['name']}》（无章节标题）")
        titles = [t for t, _ in chaps]
        if n > _SK_TITLES:
            step = n / _SK_TITLES
            titles = [titles[int(i * step)] for i in range(_SK_TITLES - 1)] + [titles[-1]]
        lines = [f"第{i + 1}章 {t}" for i, t in enumerate(titles)]
        return NodeResult(output=f"《{book['name']}》\n" + "\n".join(lines))

    _wf_scripts["book_refine_titles"] = _wf_script_book_refine_titles

    def _wf_script_book_refine_accumulate(ctx: RunContext, node: Any) -> NodeResult:
        """S129：累计单批拆解结果 → partials JSON 数组。
        读 params.item_var（缺省 "partial"）对应的上游 agent 输出，append 进
        params.list_var（缺省 "partials"）数组；输出更新后的数组（供归并 agent 读）。
        """
        import json as _json

        item_var = str(node.params.get("item_var") or "partial")
        list_var = str(node.params.get("list_var") or "partials")
        item = str(ctx.var(item_var) or "")
        if not item.strip():
            return NodeResult(error=f"book_refine_accumulate 缺 {item_var}（上游未产出）")
        current = ctx.var(list_var)
        try:
            arr = _json.loads(current) if isinstance(current, str) and current.strip() else []
        except Exception:
            arr = []
        arr.append(item)
        return NodeResult(output=_json.dumps(arr, ensure_ascii=False))

    _wf_scripts["book_refine_accumulate"] = _wf_script_book_refine_accumulate

    def _wf_script_book_refine_refine_input(ctx: RunContext, node: Any) -> NodeResult:
        """S129：定点精读输入准备——从骨架笔记定位机关章 → 精读原文片段。

        复用 skillgen 的 _extract_chapter_nums / _locate_mechanism_passages：
        骨架笔记提到机关章号 → 拼机关章 + 首尾章 + 关键词定位段（确定性，防案例幻觉的
        先给原文）。params.note：骨架笔记（{{var}} 解析）；params.library_book_id。
        """
        from anyspark.align.skillgen import (
            _extract_chapter_nums as _ext_nums,
        )
        from anyspark.align.skillgen import (
            _locate_mechanism_passages as _locate_passages,
        )

        note = _wf_resolve(str(node.params.get("note") or ""), ctx).strip()
        bid = _wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
        if not note or not bid:
            return NodeResult(error="book_refine_refine_input 缺 note/library_book_id")
        if library is None:
            return NodeResult(error="书库不可用（未装配）")
        book = library.get_book(bid)
        if book is None:
            return NodeResult(error=f"书库无此书：{bid}")
        source = library.read_book(bid, max_chars=None).strip()
        from anyspark.align.skillgen import _parse_chapters as _parse_chapters_fn

        chaps = _parse_chapters_fn(source)
        if len(chaps) < 2:
            return NodeResult(output="（章节不足，跳过定点精读）")
        nums = _ext_nums(note)
        idxs: set[int] = set()
        for a, b in nums:
            for k in range(a, min(b, a + 4) + 1):
                if 1 <= k <= len(chaps):
                    idxs.add(k - 1)
        idxs.add(0)
        idxs.add(len(chaps) - 1)
        ref_idx = sorted(i for i in idxs if 0 < i < len(chaps) - 1)
        ordered = ([*ref_idx, 0, len(chaps) - 1])[:6]
        parts = []
        for i in ordered:
            t, body = chaps[i]
            # S157：截断保留（防爆）但必须告知——agent 知道片段不完整，需要时用 read_chapter 读全文
            cut = f"（正文 {len(body)} 字，仅列前 4000）" if len(body) > 4000 else ""
            parts.append(f"【第{i + 1}章 {t}】{cut}\n{body[:4000]}")
        passages = _locate_passages(chaps, note)
        excerpt = "\n\n".join([*passages, *parts])
        note_cut = f"（笔记 {len(note)} 字，仅列前 2500）" if len(note) > 2500 else ""
        return NodeResult(output=f"{note[:2500]}{note_cut}\n\n{excerpt}")

    _wf_scripts["book_refine_refine_input"] = _wf_script_book_refine_refine_input

    def _wf_script_book_refine_finish(ctx: RunContext, node: Any) -> NodeResult:
        """S129：拆书落草稿——解析三路 agent 候选 → skills.add_draft。

        params：merge(书名方法论)/arch(架构技法)/plot(剧情模式) 三路文本
        （{{var}} 解析）+ refine_excerpt（精读原文，供架构技法案例机器校验）。
        确定性解析复用 skillgen._parse_skills/_parse_templates（含枚举校验回落）
        + _sanitize_examples（防案例幻觉：引号句必须逐字在精读片段）。
        类型映射对齐 generate_book：merge→both（文风给写作、结构给主循环）；
        arch→main（架构机关给主循环）；plot→plot（四要素进 ext）。
        """
        import json as _json

        from anyspark.align.skillgen import (
            _parse_skills as _ps,
        )
        from anyspark.align.skillgen import (
            _parse_templates as _pt,
        )
        from anyspark.align.skillgen import (
            _sanitize_examples as _san,
        )

        merge_raw = _wf_resolve(str(node.params.get("merge") or ""), ctx).strip()
        arch_raw = _wf_resolve(str(node.params.get("arch") or ""), ctx).strip()
        plot_raw = _wf_resolve(str(node.params.get("plot") or ""), ctx).strip()
        excerpt = _wf_resolve(str(node.params.get("refine_excerpt") or ""), ctx)
        # S130：拆书产物同书名一包（pack_id=书名，整包引用写作只取 writing/both）
        pack_id = _wf_resolve(str(node.params.get("pack_id") or ""), ctx).strip()
        if not pack_id:
            # 回退：从 library_book_id 解析书名
            bid = _wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
            if bid and library is not None:
                bk = library.get_book(bid)
                if bk is not None:
                    pack_id = str(bk.get("name", ""))
        if skills is None:
            return NodeResult(error="skills 未装配（无法落草稿）")
        cands: list[dict[str, str]] = []
        # 书名方法论（GENERATE_PROMPT_BOOK 单元素输出）→ both
        for mk in _ps(merge_raw)[:1]:
            mk["type"] = "both"
            cands.append(mk)
            # 架构技法（REFINE_PROMPT 多元素）→ main + 案例机器校验
        arch_cands = _ps(arch_raw)
        for ac in arch_cands:
            ac["type"] = "main"
        cands.extend(_san(arch_cands, excerpt))
        # 剧情模式（骨架笔记版四要素）→ plot（content 由 description 派生）
        for pc in _pt(plot_raw):
            cands.append(
                {
                    "name": pc["name"],
                    "description": pc["description"],
                    "content": f"剧情模式：{pc['description']}",
                    "example": "",
                    "tags": "剧情模式",
                    "type": "plot",
                    "granularity": pc["granularity"],
                    "position": pc["position"],
                    "function": pc["function"],
                    "params": pc["params"],
                }
            )
        if not cands:
            return NodeResult(output="（无有效候选）")
        added = 0
        for cd in cands:
            typ = cd.get("type", "writing")
            ext = ""
            if typ == "plot":
                params: Any = cd.get("params", [])
                if isinstance(params, str):
                    params = [p.strip() for p in params.split(",") if p.strip()]
                ext = _json.dumps(
                    {
                        "granularity": cd.get("granularity", "章"),
                        "position": cd.get("position", "发展"),
                        "function": cd.get("function", "主线"),
                        "params": params or [],
                    },
                    ensure_ascii=False,
                )
            d = skills.add_draft(
                name=str(cd.get("name", ""))[:120],
                description=str(cd.get("description", ""))[:500],
                content=str(cd.get("content", "")),
                example=str(cd.get("example", ""))[:2000],
                tags=str(cd.get("tags", "")),
                type=typ,
                ext=ext,
                pack_id=pack_id,
                source="workflow",
            )
            if d:
                added += 1
        return NodeResult(output=f"已存 {added} 条 skill 草稿（人工确认后生效）")

    _wf_scripts["book_refine_finish"] = _wf_script_book_refine_finish

    def _wf_run_script(ctx: RunContext, node: Any) -> NodeResult:
        """script 节点：确定性函数（内置白名单）——查表分发（S150 拆分）。"""
        fn = str(node.params.get("function") or "")
        handler = _wf_scripts.get(fn)
        if handler is None:
            return NodeResult(error=f"未注册的 script 函数: {fn}")
        result = handler(ctx, node)
        assert isinstance(result, NodeResult)
        return result

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
    # S116 安全收紧：CORS 从 "*" 改为 localhost 开发白名单（原 * 允许任意网页
    # 跨域调本地 API——配合无鉴权可被恶意网页触发 codex RCE）。
    # 前端 dev 走 Vite proxy（5173→8000，浏览器同源无需 CORS）；生产后端 serve
    # dist（同源）。第三方前端可用 ANYSPARK_CORS_ORIGINS（逗号分隔）显式扩展。
    _cors_origins = [
        o.strip() for o in os.environ.get("ANYSPARK_CORS_ORIGINS", "").split(",") if o.strip()
    ] or ["http://127.0.0.1:5173", "http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        """全局兜底：未捕获异常打 ERROR 日志（含 traceback）再返回 500——
        此前 _make_agent 等 try 块外的异常静默 500 零日志，排查无据。"""
        logger.exception("未捕获异常: %s %s", request.method, request.url.path, exc_info=exc)
        return Response(status_code=500, content="Internal Server Error")

    @app.middleware("http")
    async def _access_log(request: Request, call_next: Any) -> Response:
        """S104：请求级访问日志——写操作 + 非 2xx + 慢读请求（防刷屏）。

        bug 定位用：前端报错时后端能查到这个端点/耗时/状态码；异常堆栈
        由 _unhandled 兜底（此处只记访问行，不重复记异常）。
        """
        started = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception:
            raise  # 交给 _unhandled 记堆栈
        ms = int((time.monotonic() - started) * 1000)
        is_write = request.method in ("POST", "PUT", "PATCH", "DELETE")
        is_bad = response.status_code >= 400
        if is_write or is_bad or ms >= 2000:
            logger.info(
                "请求 %s %s → %d（%dms）%s",
                request.method,
                request.url.path,
                response.status_code,
                ms,
                f"?{request.url.query}" if request.url.query else "",
            )
        return response

    # S80b：组合根依赖契约（AppDeps 单例；router 拆分后各 make_xxx_router(deps) 注入）
    deps = AppDeps(
        store=store,
        chapters=chapters,
        ext_tools=ext_tools,
        manual=manual,
        signals=signals,
        archive=archive,
        dim_store=dim_store,
        materials=materials,
        plots=plots,
        models=models,
        mode_store=mode_store,
        mode_resolver=mode_resolver,
        memory_store=memory_store,
        story_tree=story_tree,
        story_threads=story_threads,
        graph=graph,
        agency=agency,
        bias=bias,
        settings=settings,
        skills=skills,
        plans=plans,
        workflow_store=workflow_store,
        play_store=play_store,
        library=library,
        mind_planner=mind_planner,
        signal_collector=signal_collector,
        provider=provider,
        model=model,
        summarizer=summarizer,
        plot_generator=plot_generator,
        plot_resolver=plot_resolver,
        preference_extractor=preference_extractor,
        skill_generator=skill_generator,
        graph_extractor=graph_extractor,
        graph_injector=graph_injector,
        graph_verifier=graph_verifier,
        budget=budget,
        window=_window,
        db_path=str(real_db),
        workflow_generator=workflow_generator,
        workflow_engine=workflow_engine,
        play_engine=play_engine,
        review_panel=review_panel,
        active_tokens=_active_tokens,
        active_agents=_active_agents,
        active_lock=_active_lock,
        bg_queue=_bg_queue,
        workspace=workspace,
        recorder=recorder,
    )

    # S81：shutdown 时统一 close 各 store 连接（WAL 优雅收尾；防连接泄漏）
    @app.on_event("shutdown")
    def _close_stores() -> None:
        for name in deps.__dataclass_fields__:
            obj = getattr(deps, name)
            close = getattr(obj, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # 单个失败不阻断其余
                    logger.warning("关闭 %s 失败: %s", name, exc)

    # S80d：router 拆分后薄包装已移除——端点直接调 make_agent(deps, ...) / extract_chapter(deps, ...)
    start_bg_worker(deps)
    app.include_router(make_conversations_router(deps))
    app.include_router(make_books_router(deps))
    app.include_router(make_agency_router(deps))
    app.include_router(make_chapters_router(deps))
    app.include_router(make_check_router(deps))
    app.include_router(make_chat_router(deps))
    app.include_router(make_explore_router(deps))
    app.include_router(make_graph_router(deps))
    app.include_router(make_mind_router(deps))
    app.include_router(make_mode_router(deps))
    app.include_router(make_library_router(deps))
    app.include_router(make_play_router(deps))
    app.include_router(make_plot_router(deps))
    app.include_router(make_settings_router(deps))
    app.include_router(make_skills_router(deps))
    app.include_router(make_story_router(deps))
    app.include_router(make_tools_router(deps))
    app.include_router(make_workflow_router(deps))
    app.include_router(make_workspace_router(deps))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name), "log": log_path()}

    # S88：生产模式——frontend/dist 存在时由后端同端口 serve（单端口全包）。
    # /api/* 路由优先（FastAPI 先匹配路由后匹配 mount），静态资源走 dist。
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    # S135：暴露组合根（测试/工具收编验证用——可直接取 workflow 依赖做单元验证）
    app.state.deps = deps
    return app


app = build_app()
