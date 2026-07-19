# SPDX-License-Identifier: Commercial
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). All rights reserved.

"""Genre Configuration — multi-genre support for the AnySpark narrative platform.

Defines GenreConfig dataclass and a registry of supported genres. Each genre
specifies its own system prompts, tool sets, output format, and knowledge graph
schema extensions. The Agent loop uses the active genre to select the correct
prompt and tools at runtime.

Architecture:
    GenreConfig is a lightweight data class. It does NOT import any other
    project modules. It is consumed by system_prompt.py and agent_loop.py.

Adding a new genre:
    1. Add a new GenreConfig to GENRES below.
    2. Add the genre's system prompt to system_prompt.py's GENRE_PROMPTS dict.
    3. (Future) Add genre-specific tools under tools/impl/genre_{name}/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Default genre ID (fallback when no genre is specified) ──
DEFAULT_GENRE = "novel"


@dataclass
class GenreConfig:
    """Configuration for a single narrative genre.

    Attributes:
        genre_id: Unique identifier (e.g. "novel", "short_drama", "murder_mystery").
        display_name: Human-readable name shown in UI.
        description: One-line description for the genre selector.
        content_unit_label: What to call a unit of content (e.g. "章节", "集", "幕").
        content_unit_label_plural: Plural form.
        system_prompt_key: Key into GENRE_PROMPTS dict in system_prompt.py.
            If empty, uses genre_id.
        output_format: Description of the expected output format.
        enabled_tool_sets: Tool categories to enable (e.g. ["writing", "knowledge", "review"]).
        graph_schema_extensions: Additional node/edge types for Neo4j (future).
        reviewer_presets: Genre-specific reviewer presets (future).
        workflow_templates: Default workflow templates (future).
    """

    genre_id: str
    display_name: str
    description: str = ""
    content_unit_label: str = "章节"
    content_unit_label_plural: str = "章节"
    system_prompt_key: str = ""
    output_format: str = ""
    enabled_tool_sets: list[str] = field(default_factory=list)
    graph_schema_extensions: dict = field(default_factory=dict)
    reviewer_presets: list[str] = field(default_factory=list)
    workflow_templates: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.system_prompt_key:
            self.system_prompt_key = self.genre_id


# ── Genre Registry ──

GENRES: dict[str, GenreConfig] = {
    "novel": GenreConfig(
        genre_id="novel",
        display_name="小说",
        description="传统长篇小说写作，支持章节管理、大纲、分卷、伏笔系统",
        content_unit_label="章",
        content_unit_label_plural="章",
        output_format="章节正文（叙述+对白），支持章节编号",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "volume", "reference",
            "plot_chain", "worldbuilding", "autopilot", "workflow",
        ],
    ),
    "short_drama": GenreConfig(
        genre_id="short_drama",
        display_name="短剧剧本",
        description="抖音/快手竖屏短剧剧本，支持分镜脚本、爽点钩子、AI视频提示词",
        content_unit_label="集",
        content_unit_label_plural="集",
        output_format="剧本格式：场景号 → 景别/运镜 → 对白/动作 → 钩子 → AI视频提示词",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "autopilot", "workflow",
        ],
    ),
    "murder_mystery": GenreConfig(
        genre_id="murder_mystery",
        display_name="剧本杀",
        description="谋杀之谜剧本创作，支持多角色视角、线索卡系统、时间线诡计、真相复盘",
        content_unit_label="角色剧本",
        content_unit_label_plural="角色剧本",
        output_format="剧本杀格式：角色剧本 → 线索卡 → 时间线 → 真相复盘",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "game_narrative": GenreConfig(
        genre_id="game_narrative",
        display_name="游戏文案",
        description="游戏主线/支线/活动剧情，支持任务树、对话树、碎片化叙事、二次元风格",
        content_unit_label="任务",
        content_unit_label_plural="任务",
        output_format="游戏文案格式：任务节点 → 对话分支 → 条件判断 → 奖励/后续",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "interactive_fiction": GenreConfig(
        genre_id="interactive_fiction",
        display_name="互动小说/AVG",
        description="视觉小说/互动叙事，支持分支树、多结局、好感度系统",
        content_unit_label="节",
        content_unit_label_plural="节",
        output_format="互动小说格式：场景描述 → 对话 → 选择节点 → 条件分支",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "audio_drama": GenreConfig(
        genre_id="audio_drama",
        display_name="广播剧/有声书",
        description="广播剧剧本，支持旁白与对白分离、音效标注、BGM提示、配音指导",
        content_unit_label="集",
        content_unit_label_plural="集",
        output_format="广播剧格式：旁白 → 对白（角色名标注）→ 音效 → BGM",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "virtual_host": GenreConfig(
        genre_id="virtual_host",
        display_name="虚拟主播/虚拟人",
        description="AI虚拟主播台词，支持直播脚本、人设一致性、粉丝互动应答",
        content_unit_label="段",
        content_unit_label_plural="段",
        output_format="直播脚本格式：开场 → 互动 → 话题 → 感谢 → 下播",
        enabled_tool_sets=[
            "writing", "knowledge", "review", "timeline",
            "style", "reference",
        ],
    ),
    "ttrpg": GenreConfig(
        genre_id="ttrpg",
        display_name="跑团模组",
        description="TTRPG冒险模组，支持遭遇表、检定节点、战利品、D&D/COC规则",
        content_unit_label="场景",
        content_unit_label_plural="场景",
        output_format="模组格式：房间描述 → NPC对话 → 检定节点 → 遭遇 → 战利品",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "comic_script": GenreConfig(
        genre_id="comic_script",
        display_name="漫画脚本",
        description="动态漫画/条漫脚本，支持分格描述、镜头语言、对话气泡、节奏控制",
        content_unit_label="话",
        content_unit_label_plural="话",
        output_format="漫画脚本格式：分格描述 → 画面内容 → 对话气泡 → 镜头指导",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "foreshadow", "style", "chapter", "reference",
            "plot_chain", "worldbuilding", "workflow",
        ],
    ),
    "children_story": GenreConfig(
        genre_id="children_story",
        display_name="儿童故事/绘本",
        description="儿童绘本脚本，支持年龄分级词汇、教育目标嵌入、亲子互动提示",
        content_unit_label="篇",
        content_unit_label_plural="篇",
        output_format="绘本格式：画面描述 → 简单文字 → 互动提示 → 教育目标",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review",
            "style", "chapter", "reference", "worldbuilding",
        ],
    ),
    "brand_world": GenreConfig(
        genre_id="brand_world",
        display_name="品牌世界观",
        description="企业品牌世界观构建，支持跨媒体叙事一致性、品牌元素管理",
        content_unit_label="文档",
        content_unit_label_plural="文档",
        output_format="品牌世界观文档：核心设定 → 品牌角色 → 叙事规则 → 跨媒体指南",
        enabled_tool_sets=[
            "writing", "knowledge", "outline", "review", "timeline",
            "style", "chapter", "reference",
            "worldbuilding", "workflow",
        ],
    ),
}


def get_genre(genre_id: str | None) -> GenreConfig:
    """Get genre configuration by ID. Falls back to DEFAULT_GENRE."""
    if not genre_id:
        return GENRES[DEFAULT_GENRE]
    return GENRES.get(genre_id, GENRES[DEFAULT_GENRE])


def list_genres() -> list[dict]:
    """Return all available genres for the frontend selector."""
    return [
        {
            "genre_id": g.genre_id,
            "display_name": g.display_name,
            "description": g.description,
            "content_unit_label": g.content_unit_label,
        }
        for g in GENRES.values()
    ]
