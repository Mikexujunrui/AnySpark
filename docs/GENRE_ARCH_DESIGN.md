# 多体裁叙事平台架构设计报告

> 版本: v1.0 | 日期: 2026-07-19 | 状态: 设计阶段，待评审
>
> 基于 `GENRE_ESSENCE_ANALYSIS.md` 的本质差异分析，本文档定义多体裁支持的完整架构设计。

---

## 一、问题定义

### 1.1 现状

当前系统是"小说写作助手"。所有设计——从数据结构到工具到前端编辑器——都围绕小说的叙事模式：

```
小说模式: 章节 → 段落 → 叙述/对白
数据模型: {id, title, content, status}
核心工具: write_chapter, delegate_writing, read_chapter
编辑器:   Markdown 编辑器
存储:     chapters_{bookId}.json
```

### 1.2 核心矛盾

短剧剧本、剧本杀、游戏文案等体裁与小说有**本质性差异**——它们不是"更短的小说"或"多视角的小说"：

| 维度 | 小说 | 短剧剧本 | 剧本杀 | 游戏文案 |
|------|------|---------|--------|---------|
| 叙事单元 | 章节 | 场景→镜头 | 角色剧本→线索卡 | 任务→对话节点 |
| 叙述者 | 有 | 无 | 无 | 无 |
| 信息维度 | 文字 | 景别/运镜/布景/灯光/时长 | 时间线/谎言/不在场证明/线索层级 | 对话树/条件判断/物品描述/UI文本 |
| 数据结构 | 线性 | 树形（集→场景→镜头） | 平行碎片（6个角色×N条线索） | 图（任务→对话→分支→条件） |
| 评判标准 | 文笔/人物/情节 | 爽点密度/反转节奏/钩子效果 | 诡计自洽性/线索可推理度 | 对话自然度/碎片自洽性 |

### 1.3 设计目标

1. **每个体裁是一等公民**：不是"小说的变体"，而是独立的叙事模式
2. **共用通用的引擎**：Agent循环、知识图谱、幻觉检测等底层能力复用
3. **隔离体裁差异**：数据模型、工具、编辑器、评审标准按体裁独立
4. **可渐进开发**：先完成短剧剧本，验证架构，再扩展其他体裁

---

## 二、架构总览

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    前端层 (Frontend)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ 小说编辑器│ │ 短剧编辑器│ │ 剧本杀编辑器│ ...        │
│  │ Markdown │ │ 分镜时间轴│ │ 多面板线索墙│            │
│  └──────────┘ └──────────┘ └──────────┘             │
│         │            │            │                   │
│         └────────────┼────────────┘                   │
│                      ▼                               │
│         ┌────────────────────────┐                   │
│         │  GenreViewRegistry     │  ← 体裁→编辑器映射│
│         └────────────────────────┘                   │
├─────────────────────────────────────────────────────┤
│                    API 层 (Routes)                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  /api/books  /api/genres  /api/genre/{id}/... │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│                 体裁插件层 (Genre Plugins)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ Novel    │ │ShortDrama│ │MurderMyst│ ...          │
│  │ Plugin   │ │ Plugin   │ │ Plugin   │             │
│  │          │ │          │ │          │             │
│  │• prompt  │ │• prompt  │ │• prompt  │             │
│  │• tools   │ │• tools   │ │• tools   │             │
│  │• schema  │ │• schema  │ │• schema  │             │
│  │• reviewer│ │• reviewer│ │• reviewer│             │
│  └──────────┘ └──────────┘ └──────────┘             │
│         │            │            │                   │
│         └────────────┼────────────┘                   │
│                      ▼                               │
│         ┌────────────────────────┐                   │
│         │   GenreRegistry        │  ← 体裁注册中心   │
│         │   (统一管理所有插件)     │                   │
│         └────────────────────────┘                   │
├─────────────────────────────────────────────────────┤
│                通用引擎层 (Core Engine)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │Agent Loop│ │GraphStore│ │Hallucin. │             │
│  │(1881行)  │ │(3300行)  │ │Detector  │             │
│  └──────────┘ └──────────┘ └──────────┘             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │LLM Client│ │ContextMgr│ │ToolExec. │             │
│  │          │ │          │ │(dispatch)│             │
│  └──────────┘ └──────────┘ └──────────┘             │
│                                                      │
│  所有体裁共享，不感知体裁差异                          │
└─────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户创建项目 → 选择体裁 → GenreRegistry 加载对应插件
                              │
                              ├→ 注册体裁专属工具到 ToolRegistry
                              ├→ 加载体裁专属 system prompt
                              ├→ 配置体裁专属数据存储
                              └→ 加载体裁专属评审员

用户发送消息 → Agent Loop (通用引擎)
                  │
                  ├→ build_system_prompt(genre_id) → 体裁专属 prompt
                  ├→ resolve_tools(genre_id) → 通用工具 + 体裁专属工具
                  ├→ execute_tool → ToolRegistry.dispatch → 工具实现
                  └→ 输出 → 前端根据 genre 渲染对应编辑器
```

---

## 三、GenrePlugin 接口设计

### 3.1 核心接口

```python
class GenrePlugin(ABC):
    """体裁插件基类。每个体裁实现此接口。"""

    # ── 元数据 ──
    genre_id: str                          # "short_drama"
    display_name: str                      # "短剧剧本"
    content_unit_label: str                # "集" / "角色剧本" / "任务"

    # ── Prompt ──
    def get_system_prompt(self, agent_type: str) -> str: ...

    # ── 工具 ──
    def get_tools(self) -> list[Tool]: ...
    def register_tools(self, dispatch: dict) -> None: ...

    # ── 数据模型 ──
    def get_content_schema(self) -> dict: ...       # 内容单元的 JSON Schema
    def get_storage_file(self, book_id: str) -> str: ...  # 存储文件名

    # ── 评审 ──
    def get_reviewers(self) -> list[dict]: ...       # 体裁专属评审员

    # ── 图谱扩展 ──
    def get_graph_extensions(self) -> dict: ...      # 额外的节点/边类型

    # ── 前端 ──
    def get_editor_component(self) -> str: ...       # 前端编辑器组件名
    def get_panel_components(self) -> list[str]: ... # 前端面板组件名
```

### 3.2 注册机制

```python
class GenreRegistry:
    """体裁注册中心。管理所有 GenrePlugin 实例。"""

    _plugins: dict[str, GenrePlugin] = {}

    @classmethod
    def register(cls, plugin: GenrePlugin):
        cls._plugins[plugin.genre_id] = plugin

    @classmethod
    def get(cls, genre_id: str) -> GenrePlugin:
        return cls._plugins.get(genre_id)

    @classmethod
    def list_all(cls) -> list[dict]:
        return [{"genre_id": p.genre_id, "display_name": p.display_name}
                for p in cls._plugins.values()]
```

---

## 四、数据模型设计

### 4.1 小说 (novel) — 现有模型，无需改动

```json
// chapters_{bookId}.json
[{
    "id": "uuid",
    "title": "第一章 初遇",
    "content": "章节正文...",
    "status": "draft" | "final",
    "order": 1,
    "versions": [...],
    "createdAt": "ISO8601",
    "updatedAt": "ISO8601"
}]
```

### 4.2 短剧剧本 (short_drama) — 全新设计

```json
// short_drama_{bookId}.json
{
    "episodes": [{
        "id": "ep_001",
        "episode_number": 1,
        "title": "第1集 意外的重逢",
        "synopsis": "本集概要...",
        "duration_seconds": 90,
        "hook": "结尾钩子：门后的人竟然是...",
        "ai_video_prompt": "一部竖屏短剧，场景是...",
        "scenes": [{
            "id": "sc_001",
            "scene_number": 1,
            "location": "咖啡厅",
            "time_of_day": "日",
            "interior": true,
            "scene_description": "午后阳光透过落地窗洒在木质地板上",
            "set_dressing": {
                "props": ["咖啡杯×2", "笔记本电脑", "枯萎的盆栽"],
                "lighting": "暖色调，侧逆光",
                "color_palette": "棕色+米色+金色"
            },
            "shots": [{
                "id": "shot_001",
                "shot_number": 1,
                "shot_type": "中景",          // 特写/近景/中景/全景/远景
                "camera_move": "缓缓推进",     // 推/拉/摇/移/跟/固定
                "angle": "平视",
                "duration_seconds": 5,
                "characters_in_frame": ["林小雨", "陈墨"],
                "visual_description": "林小雨坐在靠窗位置，手指无意识地搅动咖啡",
                "dialogue": [{
                    "speaker": "林小雨",
                    "line": "三年了，你还是喜欢坐靠窗的位置。",
                    "emotion": "平静中带着一丝紧张",
                    "delivery_note": "语速略慢，尾音微微上扬"
                }, {
                    "speaker": "陈墨",
                    "line": "你也是。",
                    "emotion": "平静",
                    "delivery_note": "简短，不抬头，继续看电脑"
                }],
                "action": "陈墨继续敲击键盘，没有抬头。林小雨的手指停住了。",
                "sound_effect": "键盘敲击声，咖啡杯轻碰碟子的声音",
                "bgm": "轻柔的钢琴曲，音量30%",
                "transition": "切"             // 切/淡入/淡出/叠化
            }]
        }],
        "beat_points": [{                     // 爽点标记
            "shot_id": "shot_008",
            "type": "身份揭晓",
            "description": "陈墨摘下眼镜，露出真实的身份"
        }],
        "status": "draft" | "final",
        "createdAt": "ISO8601",
        "updatedAt": "ISO8601"
    }]
}
```

**关键设计决策**：
- 集(Episode) → 场景(Scene) → 镜头(Shot) 三层嵌套，对应短剧的叙事层级
- 每个镜头包含**小说完全不需要**的信息：景别、运镜、布景道具、灯光、色调、时长、音效、BGM、转场方式
- 对白带有 emotion 和 delivery_note（给演员/配音的指导），不只是纯文字
- 爽点标记(beat_points)单独列出，方便评审时检查爽点密度
- ai_video_prompt 是最终交付物，直接对接AI视频生成工具

### 4.3 剧本杀 (murder_mystery) — 后续设计

核心数据结构将完全不同：
```json
// murder_mystery_{bookId}.json
{
    "case_title": "...",
    "victim": {...},
    "suspects": [{
        "id": "sus_001",
        "name": "林小雨",
        "role_script": {
            "public_identity": "咖啡厅老板",
            "secret": "实际上是受害者的前妻",
            "timeline_view": [           // 该角色视角的时间线
                {"time": "17:00", "event": "到达宴会厅", "truth_level": "true"},
                {"time": "17:15", "event": "去洗手间", "truth_level": "lie"},  // 谎言！
                {"time": "17:30", "event": "发现尸体", "truth_level": "true"}
            ],
            "motive": "财产纠纷",
            "relationships": [...]
        },
        "is_murderer": false
    }],
    "clue_cards": [{
        "id": "clue_001",
        "number": 1,
        "type": "物证",                  // 物证/口供/环境/时间/动机
        "content": "一块停止在17:03的手表",
        "source": "洗手间垃圾桶",
        "tier": "深入",                  // 公开/深入/隐藏
        "points_to": "sus_001",          // 指向哪个嫌疑人
        "reveals": "角色的时间线谎言"     // 揭示什么
    }],
    "truth": {
        "murderer": "sus_003",
        "motive": "...",
        "method": "...",
        "full_timeline": [...],         // 完整真相时间线
        "deduction_chain": [...]        // 推理链
    }
}
```

### 4.4 游戏文案 (game_narrative) — 后续设计

```json
// game_narrative_{bookId}.json
{
    "quests": [{
        "id": "q_M001",
        "type": "main",                  // main/side/daily/event/hidden
        "title": "第一章：觉醒",
        "prerequisites": ["完成序章"],
        "steps": [{
            "step_number": 1,
            "dialogue_nodes": [{
                "id": "dn_001",
                "npc": "艾莉丝",
                "npc_line": "你终于来了，我等了很久。",
                "player_options": [{
                    "id": "opt_001",
                    "text": "发生什么事了？",
                    "conditions": {},      // 条件判断
                    "effects": {"affection_alice": 2},
                    "next_node": "dn_002"
                }, {
                    "id": "opt_002",
                    "text": "（沉默地点头）",
                    "conditions": {"courage": {"gte": 5}},
                    "effects": {"affection_alice": 1, "hidden_flag": "silent_type"},
                    "next_node": "dn_003"
                }]
            }]
        }],
        "rewards": {"exp": 500, "items": ["樱花发饰"]},
        "unlocks": ["q_M002"]
    }],
    "items": [{                          // 碎片化叙事
        "id": "item_001",
        "name": "樱花发饰",
        "rarity": 3,
        "description": "艾莉丝随身携带的发饰。花瓣已经褪色，据说来自她的故乡。",
        "lore_hint": "暗示艾莉丝失去了故乡"  // 世界观线索
    }]
}
```

---

## 五、工具系统设计

### 5.1 工具分发机制（复用现有架构）

现有 `_DISPATCH` 表已经支持按体裁注册工具。只需扩展注册流程：

```python
# 在 GenrePlugin.register_tools() 中调用
def register_tools(self, dispatch: dict):
    dispatch["create_shot"] = self._create_shot
    dispatch["update_scene"] = self._update_scene
    dispatch["generate_hook"] = self._generate_hook
    # ...
```

### 5.2 短剧剧本专属工具

| 工具名 | 功能 | 输入 | 输出 |
|--------|------|------|------|
| `create_episode` | 创建新一集 | episode_number, title, synopsis | episode_id |
| `add_scene` | 添加场景 | episode_id, location, time_of_day, description | scene_id |
| `add_shot` | 添加镜头 | scene_id, shot_type, camera_move, duration | shot_id |
| `write_dialogue` | 写入对白 | shot_id, speaker, line, emotion, delivery_note | ok |
| `set_beat_point` | 标记爽点 | shot_id, beat_type, description | ok |
| `generate_hook` | 生成结尾钩子 | episode_id, context | hook_text |
| `generate_video_prompt` | 生成AI视频提示词 | episode_id | prompt_text |
| `list_episodes` | 列出所有集 | — | episode_list |
| `get_episode` | 获取单集完整数据 | episode_id | episode_json |
| `update_shot` | 修改镜头 | shot_id, fields | ok |
| `delete_shot` | 删除镜头 | shot_id | ok |
| `reorder_shots` | 重排镜头顺序 | episode_id, shot_order | ok |

### 5.3 剧本杀专属工具（后续）

| 工具名 | 功能 |
|--------|------|
| `create_suspect` | 创建嫌疑人角色 |
| `add_clue_card` | 添加线索卡 |
| `set_timeline_view` | 设置角色视角时间线 |
| `generate_truth` | 生成真相复盘 |
| `check_timeline_consistency` | 检查时间线一致性 |
| `check_clue_completeness` | 检查线索是否可推理 |

### 5.4 游戏文案专属工具（后续）

| 工具名 | 功能 |
|--------|------|
| `create_quest` | 创建任务 |
| `add_dialogue_node` | 添加对话节点 |
| `add_player_option` | 添加玩家选项（含条件） |
| `create_item_description` | 写物品描述（碎片化叙事） |
| `check_quest_flow` | 检查任务流程完整性 |
| `export_dialogue_tree` | 导出对话树 |

---

## 六、前端设计

### 6.1 组件架构

```
GenreViewRouter (根据 genre_id 选择视图)
│
├── NovelView (当前已有)
│   ├── MarkdownEditor
│   ├── ChaptersPanel
│   ├── OutlinePanel
│   └── ...
│
├── ShortDramaView (新建)
│   ├── EpisodeTimeline      ← 集的时间轴视图
│   ├── SceneCardEditor       ← 场景卡片编辑器
│   ├── ShotDetailPanel       ← 镜头详情面板
│   │   ├── ShotTypeSelector  (景别选择器)
│   │   ├── CameraMoveSelector (运镜选择器)
│   │   ├── DialogueEditor    (对白编辑器，含emotion/delivery)
│   │   ├── SetDesignPanel    (布景设计面板：道具/灯光/色调)
│   │   └── DurationSlider    (时长滑块)
│   ├── BeatPointOverlay      ← 爽点标记叠加层
│   ├── HookPreview            ← 钩子预览
│   └── VideoPromptPreview    ← AI视频提示词预览
│
├── MurderMysteryView (后续)
│   ├── SuspectPanel          ← 嫌疑人面板（可切换角色）
│   ├── ClueWall              ← 线索墙（可视化卡片）
│   ├── TimelineComparison    ← 多角色时间线对比
│   └── TruthPanel            ← 真相复盘面板
│
└── GameNarrativeView (后续)
    ├── QuestTree              ← 任务树可视化
    ├── DialogueTreeEditor     ← 对话树编辑器
    ├── ItemDescriptionEditor  ← 物品描述编辑器
    └── FragmentPreview        ← 碎片化叙事预览
```

### 6.2 短剧编辑器核心交互

```
┌──────────────────────────────────────────────────────┐
│  [集选择器] ◀ 第1集 第2集 第3集 ▶  [+ 新建集]        │
├──────────────────────────────────────────────────────┤
│  第1集 ── "意外的重逢"                          90秒  │
│                                                      │
│  ┌─ 场景1: 咖啡厅 ──────────────────────────────┐   │
│  │  📍 咖啡厅 · 🕐 日 · 🏠 室内                   │   │
│  │  🎬 镜头1 [中景·推·5秒]                        │   │
│  │  ┌──────────────────────────────────────┐    │   │
│  │  │ 画面: 林小雨搅动咖啡...               │    │   │
│  │  │ 对白: 林小雨→"三年了..." 😌          │    │   │
│  │  │      陈墨→"你也是。" 😐              │    │   │
│  │  │ 动作: 陈墨继续敲键盘                  │    │   │
│  │  │ 🔊 键盘声 🎵 钢琴 BGM                │    │   │
│  │  └──────────────────────────────────────┘    │   │
│  │  🎬 镜头2 [特写·固定·3秒]                     │   │
│  │  ...                                          │   │
│  │  [+ 添加镜头]                                 │   │
│  └──────────────────────────────────────────────┘   │
│  ┌─ 场景2: 咖啡厅门外 ──────────────────────────┐   │
│  │  ...                                          │   │
│  └──────────────────────────────────────────────┘   │
│  [+ 添加场景]                                       │
│                                                      │
│  ⚡ 爽点: 镜头8 — 身份揭晓                            │
│  🪝 钩子: 门后的人竟然是...                          │
│  🎥 AI视频提示词: [展开预览]                         │
└──────────────────────────────────────────────────────┘
```

---

## 七、评审系统设计

### 7.1 体裁专属评审员

现有14位评审员是小说专用的。每个体裁需要自己的评审员集合：

| 体裁 | 评审员 | 评审维度 |
|------|--------|---------|
| 小说 | 编剧/文学编辑/逻辑审校/爽文读者/... | 文笔/人物/情节/逻辑 |
| 短剧 | **节奏导演**（爽点密度/反转节奏）<br>**视觉指导**（景别/运镜/布景合理性）<br>**钩子检测员**（每集结尾钩子效果）<br>**对白导演**（口语化/冲突感）<br>**AI视频适配员**（提示词可执行性） | 爽点密度/画面感/钩子/对白/可拍摄性 |
| 剧本杀 | **诡计审查员**（逻辑自洽性）<br>**线索平衡员**（难度/信息分布）<br>**角色对等员**（每个角色参与感）<br>**时间线检查员**（交叉验证）<br>**模拟玩家**（模拟推理过程） | 诡计/线索/角色平衡/时间线/可玩性 |
| 游戏文案 | **对话自然度评审**<br>**碎片自洽性评审**<br>**角色一致性评审**<br>**玩家体验评审**（跳过/重复测试） | 对话/碎片/一致性/体验 |

### 7.2 评审员配置

```yaml
# reviewers/short_drama.yaml
reviewers:
  - id: rhythm_director
    name: 节奏导演
    category: professional
    persona: |
      你是短剧节奏导演。你关注：
      1. 每集爽点密度：至少1个爽点，不超过2集无爽点
      2. 反转节奏：30秒内必须有小高潮
      3. 每集结尾钩子：必须让观众想看下一集
      4. 整体节奏：不能拖沓，不能信息过载

  - id: visual_director
    name: 视觉指导
    category: professional
    persona: |
      你是短剧视觉指导。你关注：
      1. 景别选择是否合理（该用特写的地方用了全景？）
      2. 运镜是否有助于叙事
      3. 布景和道具是否具体、可执行
      4. 灯光和色调是否符合场景情绪
      ...
```

---

## 八、存储层设计

### 8.1 存储文件命名

```
当前（仅小说）:
  chapters_{bookId}.json
  outline_{bookId}.json
  ...

改为（按体裁）:
  novel_{bookId}.json          ← 小说内容
  short_drama_{bookId}.json    ← 短剧内容
  murder_mystery_{bookId}.json ← 剧本杀内容
  game_narrative_{bookId}.json ← 游戏文案内容
  ...

共用（不变）:
  sessions_{bookId}.json
  outline_{bookId}.json        ← 大纲（所有体裁通用）
  timeline_{bookId}.json       ← 时间线（所有体裁通用）
  books.json                   ← 项目列表（新增 genre 字段）
```

### 8.2 API 设计

```
GET  /api/genres                          → 列出所有可用体裁
GET  /api/books                           → 列出所有项目（含 genre 字段）
POST /api/books {title, description, genre} → 创建项目（指定体裁）
GET  /api/books/{bookId}                  → 获取项目详情（含 genre）

# 体裁专属 API（按 genre 路由）
GET  /api/short-drama/{bookId}/episodes   → 列出所有集
POST /api/short-drama/{bookId}/episodes   → 创建新集
GET  /api/short-drama/{bookId}/episodes/{epId} → 获取单集
PUT  /api/short-drama/{bookId}/episodes/{epId} → 更新单集
POST /api/short-drama/{bookId}/scenes     → 添加场景
POST /api/short-drama/{bookId}/shots      → 添加镜头
...
```

---

## 九、实施路线

### Phase 8a: 短剧剧本完整实现（当前阶段）

**目标**：完整实现短剧剧本的端到端创作流程，验证架构设计

| 序号 | 任务 | 预估工时 | 优先级 |
|------|------|---------|--------|
| 1 | 定义短剧数据模型（`ShortDramaStore`） | 2天 | P0 |
| 2 | 实现短剧专属 API 路由 | 1天 | P0 |
| 3 | 实现短剧专属工具（12个） | 3天 | P0 |
| 4 | 实现短剧专属评审员 | 1天 | P1 |
| 5 | 实现短剧前端编辑器（分镜时间轴） | 5天 | P1 |
| 6 | 实现短剧前端面板（爽点/钩子/视频提示词） | 2天 | P1 |
| 7 | 端到端测试 | 2天 | P0 |

### Phase 8b: 剧本杀完整实现

类似工作量，但数据模型和前端完全不同。

### Phase 8c: 游戏文案完整实现

类似工作量。

---

## 十、风险与决策

### 10.1 已识别风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 前端开发量过大 | 高 | 高 | 先用纯文本+聊天界面验证，前端编辑器后做 |
| 体裁间数据模型差异过大，共用引擎不够 | 中 | 高 | 每个体裁先做 MVP 验证，不一次设计所有 |
| 用户对某个体裁的需求与设计不符 | 中 | 中 | 设计阶段多与用户确认，先做可用的MVP |

### 10.2 关键决策

1. **先做短剧剧本**：数据模型最清晰、与小说的差异最直观、商业化价值最高
2. **前端分两阶段**：第一阶段用聊天界面（Agent对话生成短剧内容），第二阶段做专用编辑器
3. **存储文件按体裁分离**：不做"统一内容模型"，允许每个体裁有完全不同的数据结构
4. **评审员按体裁独立**：不做"通用评审框架"，每个体裁定义自己的评审维度

---

*本文档在开始编码前需经评审确认。确认后作为 Phase 8a 的实施依据。*
