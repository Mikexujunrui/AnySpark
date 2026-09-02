"""anyspark.server.seeds_campus — 校园场景预置 workflow 模板（S248）。

从 seeds.py 拆分（该文件已近千行）：学术/申报/新媒体场景的模板数据。
全部复用既有原语（book_refine_* / list_split / batch_prepare / read_chapter /
chapter_by_id / chapter_title_by_id / write_chapter / accumulate），模板即数据——
用户改节点指令即改行为，零新机制。

拆解维度与 server.genres 的 ACADEMIC profile 单一来源（模板构建时引用，防漂移）。
"""

from __future__ import annotations

from typing import Any

from anyspark.server.genres import ACADEMIC

# 学术七维单一来源：引用 genres.ACADEMIC（内联拷贝会在 profile 更新后漂移）
_ACADEMIC_DIMS = ACADEMIC.decomposition_dimensions


def _seed_paper_refine_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S248：拆论文——学术七维拆解书库论文/专著 → 方法论 skill 草稿（人工确认）。

    复用拆书管线原语（prepare/accumulate/finish），仅拆解指令换学术维度。
    论文无剧情模式/定点精读环节，管线相应精简。运行参数：library_book_id。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "拆论文",
            "description": (
                "按学术七维（研究问题/方法数据/贡献结论/论证链/结构组织/表达规范/文献使用）"
                "拆解书库中的论文/专著 → 方法论 skill 草稿（人工确认后生效）。"
                "运行参数：library_book_id=书库书 id（reference_lookup 可查）。"
            ),
            "nodes": [
                {
                    "id": "prep",
                    "kind": "script",
                    "label": "选段分批",
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
                        "max_iterations": 24,
                        "collection_var": "prepared",
                        "item_var": "batch",
                    },
                },
                {
                    "id": "decompose",
                    "kind": "agent",
                    "label": "学术拆解本批",
                    "params": {
                        "instruction": (
                            "你是学术论文结构分析师。拆解以下文本批次，输出单条方法论 skill"
                            "（严格 JSON 单元素数组，字段：name/description/content/example，"
                            "example 留空）。聚焦可迁移的写作方法论，不要复述内容。\n"
                            + _ACADEMIC_DIMS
                            + "\n\n"
                            "文本批次：\n{{batch}}\n"
                        ),
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
                        "instruction": (
                            "把各批拆解结果归并为单条方法论 skill（严格 JSON 单元素数组，"
                            "字段同前），去重整合、保留最有迁移价值的写法。\n"
                            "各批结果：\n{{partials}}\n"
                        ),
                        "output_key": "merged",
                    },
                },
                {
                    "id": "finish",
                    "kind": "script",
                    "label": "落草稿",
                    "params": {
                        "function": "book_refine_finish",
                        "merge": "{{merged}}",
                        "library_book_id": "{{library_book_id}}",
                        "output_key": "finish_report",
                    },
                },
            ],
            "edges": [
                {"source": "prep", "target": "loop"},
                {"source": "loop", "target": "merge"},
                {"source": "merge", "target": "finish"},
            ],
        }
    )
    _commit(workflow_store, wf, "拆论文")


def _seed_literature_review_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S248：文献综述——逐篇标题轨迹拆解 → 分主题综述汇编（直接出文本）。

    V1 以标题轨迹为单篇输入（廉价全局视图）；单篇深读拆解先跑「拆论文」。
    运行参数：paper_ids（书库书 id，逗号串或 JSON 数组）+ topic（综述主题，可选）。
    """
    wf = wf_def_cls.from_dict(
        {
            "name": "文献综述",
            "description": (
                "对书库中多篇论文逐篇做结构拆解（标题轨迹 + 学术七维要点），"
                "汇编为主题组织的文献综述草稿。运行参数：paper_ids=书库书 id "
                "（逗号串或 JSON 数组）；topic=综述主题（可选）。"
            ),
            "nodes": [
                {
                    "id": "split",
                    "kind": "script",
                    "label": "文献清单切分",
                    "params": {
                        "function": "list_split",
                        "text": "{{paper_ids}}",
                        "output_key": "paper_list",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐篇拆解",
                    "params": {
                        "body": ["titles", "analyze", "accumulate"],
                        "max_iterations": 24,
                        "collection_var": "paper_list",
                        "item_var": "pid",
                    },
                },
                {
                    "id": "titles",
                    "kind": "script",
                    "label": "取章题轨迹",
                    "params": {
                        "function": "book_refine_titles",
                        "library_book_id": "{{pid}}",
                        "output_key": "titles_text",
                    },
                },
                {
                    "id": "analyze",
                    "kind": "agent",
                    "label": "单篇要点",
                    "params": {
                        "instruction": (
                            "你是学术综述助手。根据该论文的章节标题轨迹，输出其结构化要点：\n"
                            "- 研究问题与主题\n- 方法路线\n- 主要贡献（推测性表述，标注"
                            "「据标题推断」）\n- 与综述主题的关联点\n"
                            "简洁（≤150 字），不要虚构未提及的细节。\n"
                            "章节标题轨迹：\n{{titles_text}}\n"
                        ),
                        "output_key": "partial",
                    },
                },
                {
                    "id": "accumulate",
                    "kind": "script",
                    "label": "累计要点",
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
                    "label": "综述汇编",
                    "params": {
                        "instruction": (
                            "把各论文要点汇编为一篇文献综述草稿：分主题组织（不要逐篇罗列），"
                            "标注各文献贡献与关联，结尾给出研究空白与综述结论。"
                            "语气客观，推断性表述保留「据标题推断」标注。\n"
                            "综述主题：{{topic}}\n\n各论文要点：\n{{partials}}\n"
                        ),
                        "output_key": "review_text",
                    },
                },
            ],
            "edges": [
                {"source": "split", "target": "loop"},
                {"source": "loop", "target": "merge"},
            ],
        }
    )
    _commit(workflow_store, wf, "文献综述")


def _seed_proposal_draft_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S248：申报书起草——大纲 → 逐节起草 → 汇编全文（直接出文本，人工采纳）。"""
    wf = wf_def_cls.from_dict(
        {
            "name": "申报书起草",
            "description": (
                "竞赛申报书/项目建议书起草：按主题与要点生成大纲（JSON），逐节起草，"
                "汇编完整草稿。运行参数：topic=项目主题；key_points=要点"
                "（分号分隔或 JSON 数组）。"
            ),
            "nodes": [
                {
                    "id": "outline",
                    "kind": "agent",
                    "label": "生成大纲",
                    "params": {
                        "instruction": (
                            "你是竞赛申报书专家。按主题与要点生成申报书大纲，输出严格 JSON "
                            '数组：[{"title":"节标题","brief":"本节要点一句话"}]，'
                            "覆盖：项目背景与痛点/方案与创新/实施计划/团队与分工/预期成果"
                            "（可按主题增删调整）。\n主题：{{topic}}\n要点：{{key_points}}\n"
                        ),
                        "output_key": "outline_json",
                    },
                },
                {
                    "id": "split",
                    "kind": "script",
                    "label": "大纲切分",
                    "params": {
                        "function": "list_split",
                        "text": "{{outline_json}}",
                        "output_key": "section_list",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐节起草",
                    "params": {
                        "body": ["draft", "accumulate"],
                        "max_iterations": 24,
                        "collection_var": "section_list",
                        "item_var": "section",
                    },
                },
                {
                    "id": "draft",
                    "kind": "agent",
                    "label": "起草本节",
                    "params": {
                        "instruction": (
                            "按本节大纲起草申报书正文（200-400 字）：有说服力、要点明确、"
                            "紧扣主题。本节大纲：{{section}}\n主题：{{topic}}\n要点：{{key_points}}\n"
                        ),
                        "output_key": "partial",
                    },
                },
                {
                    "id": "accumulate",
                    "kind": "script",
                    "label": "累计各节",
                    "params": {
                        "function": "book_refine_accumulate",
                        "item_var": "partial",
                        "list_var": "sections",
                        "output_key": "sections",
                    },
                },
                {
                    "id": "merge",
                    "kind": "agent",
                    "label": "汇编全文",
                    "params": {
                        "instruction": (
                            "把各节正文汇编为完整申报书：加总标题与节标题，衔接过渡，"
                            "统一口径与语风。各节正文：\n{{sections}}\n"
                        ),
                        "output_key": "proposal_text",
                    },
                },
            ],
            "edges": [
                {"source": "outline", "target": "split"},
                {"source": "split", "target": "loop"},
                {"source": "loop", "target": "merge"},
            ],
        }
    )
    _commit(workflow_store, wf, "申报书起草")


def _seed_multi_platform_template(workflow_store: Any, wf_def_cls: Any) -> None:
    """S248：多平台改写——一稿按平台清单逐版适配（直接出文本，人工采纳）。"""
    wf = wf_def_cls.from_dict(
        {
            "name": "多平台改写",
            "description": (
                "一稿多平台适配：对给定平台清单（如 公众号,小红书,知乎）逐平台改写，"
                "汇编各平台版本。运行参数：chapter_title=原稿章节标题；"
                "platforms=平台清单（逗号串或 JSON 数组）。"
            ),
            "nodes": [
                {
                    "id": "read",
                    "kind": "script",
                    "label": "读原稿",
                    "params": {
                        "function": "read_chapter",
                        "chapter_title": "{{chapter_title}}",
                        "output_key": "manuscript",
                    },
                },
                {
                    "id": "split",
                    "kind": "script",
                    "label": "平台清单切分",
                    "params": {
                        "function": "list_split",
                        "text": "{{platforms}}",
                        "output_key": "platform_list",
                    },
                },
                {
                    "id": "loop",
                    "kind": "loop",
                    "label": "逐平台改写",
                    "params": {
                        "body": ["adapt", "accumulate"],
                        "max_iterations": 12,
                        "collection_var": "platform_list",
                        "item_var": "platform",
                    },
                },
                {
                    "id": "adapt",
                    "kind": "agent",
                    "label": "平台适配",
                    "params": {
                        "instruction": (
                            "把原稿改写为适合「{{platform}}」平台的版本："
                            "按该平台的篇幅习惯/标题风格/语气/排版惯例调整，保留核心信息。"
                            "输出前加一行平台标注。\n原稿：\n{{manuscript}}\n"
                        ),
                        "output_key": "partial",
                    },
                },
                {
                    "id": "accumulate",
                    "kind": "script",
                    "label": "累计各版",
                    "params": {
                        "function": "book_refine_accumulate",
                        "item_var": "partial",
                        "list_var": "versions",
                        "output_key": "versions",
                    },
                },
                {
                    "id": "merge",
                    "kind": "agent",
                    "label": "汇编交付",
                    "params": {
                        "instruction": (
                            "把各平台版本整理为交付稿：平台标注清晰、可直接复制发布。"
                            "各版本：\n{{versions}}\n"
                        ),
                        "output_key": "delivery",
                    },
                },
            ],
            "edges": [
                {"source": "read", "target": "split"},
                {"source": "split", "target": "loop"},
                {"source": "loop", "target": "merge"},
            ],
        }
    )
    _commit(workflow_store, wf, "多平台改写")


def _commit(workflow_store: Any, wf: Any, label: str) -> None:
    """校验并入库（builtin 保护，与 seeds.py 各 _seed_* 同型）。"""
    errors = wf.validate()
    if errors:
        raise ValueError(f"{label}模板校验失败: {errors}")
    workflow_store.add_template(wf, builtin=True)
