"""
anyspark.server.seeds — 预置 workflow 模板种子（从 app.py 拆出，S187 技术债清理）。

包含：
- _migrate_templates_to_skills：旧 templates 表 → skill 表 type=plot 迁移
- 8 个 _seed_*_template：预置 workflow 模板（拆书/批量改写/批量审读/图谱抽取等）
  在 build_app 时幂等种入 workflow_store（已存在则跳过 + 补标 builtin）

这些函数是纯函数（不引用 build_app 闭包变量），从 app.py 提取无行为变化。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from anyspark.align import WritingSkillStore


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
