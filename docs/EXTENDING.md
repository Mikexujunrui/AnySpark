# 扩展开发指南

> 本文档面向需要为火花开发扩展的开发者。火花提供四种扩展机制：**插件系统**（Python 钩子）、**YAML 技能**（复合工作流）、**文风模板**（叙事策略）、**自定义评审员**（审核人设）。

---

## 目录

1. [插件系统（Python 钩子）](#1-插件系统python-钩子)
2. [技能系统（YAML 工作流）](#2-技能系统yaml-工作流)
3. [文风系统（YAML 叙事模板）](#3-文风系统yaml-叙事模板)
4. [评审员自定义（YAML 人设）](#4-评审员自定义yaml-人设)
5. [工具扩展（Python 实现）](#5-工具扩展python-实现)

---

## 1. 插件系统（Python 钩子）

插件允许在写作流程的关键节点注入自定义 Python 逻辑。放置于 `plugins/` 目录下的 `.py` 文件会被自动发现和加载。

### 文件格式

```python
"""我的自定义插件：功能描述。"""

PLUGIN_NAME = "my_plugin"           # 插件名称（必填）
PLUGIN_VERSION = "0.1.0"            # 插件版本（必填）
PLUGIN_DESCRIPTION = "功能说明"      # 插件描述（可选）
PLUGIN_AUTHOR = ""                  # 作者（可选）
```

### 可用钩子

| 钩子函数 | 触发时机 | 参数 | 返回值 |
|----------|---------|------|--------|
| `modify_system_prompt` | 构建 System Prompt 时 | `value: str`（当前 prompt），`**kwargs` | `str`（修改后的 prompt） |
| `on_write_before` | 写作开始前 | `instruction: str`，`**kwargs` | `None` |
| `on_chapter_save` | 章节保存后 | `title: str`，`content: str`，`**kwargs` | `None` |
| `on_extract_before` | 知识提取开始前 | `text: str`，`**kwargs` | `None` |

### 完整示例

参考 `plugins/example_style.py`：

```python
"""示例插件：为写作添加文风约束。"""

PLUGIN_NAME = "example_style"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "示例：为写作添加文风约束"
PLUGIN_AUTHOR = ""

def modify_system_prompt(value: str, **kwargs) -> str:
    """在 system prompt 末尾添加文风提示。"""
    style_hint = "\n\n[插件约束] 写作时注意：句式简洁有力，多用短句。"
    return value + style_hint

def on_write_before(instruction: str = "", **kwargs) -> None:
    """写作前的钩子，可用于日志或参数修改。"""
    pass

def on_chapter_save(title: str = "", content: str = "", **kwargs) -> None:
    """章节保存后的钩子。"""
    pass
```

### 注意事项

- 插件文件放在 `plugins/` 根目录（不支持子目录）
- 钩子函数签名中的 `**kwargs` 保留用于未来扩展
- 插件中抛出异常不会中断主流程，仅记录日志
- 多个插件按文件名排序依次执行

---

## 2. 技能系统（YAML 工作流）

技能将多个工具调用组合为可复用的工作流，定义在 `skills/` 目录下的 YAML 文件中。

### 文件格式

```yaml
- name: my_skill                # 技能名称（必填，唯一标识）
  description: "技能说明"        # 技能描述（提示 LLM 何时使用）
  triggers: [content_type]      # 触发内容类型，可选值：
                                #   novel_chapter | setting_document
                                #   story_fragment | inspiration_note
                                #   instruction | mixed
  steps:
    - tool: tool_name           # 调用的工具名
      label: "步骤标签"          # 步骤标签（显示在前端进度条）
      params:                   # 工具参数（可选）
        param1: value1          # 固定参数
```

### 系统预设技能

参见 `skills/default.yaml` 包含 7 个预设技能：

| 技能名 | 用途 | 步骤序列 |
|--------|------|---------|
| `full_novel_import` | 导入完整小说 | store_chapter → compare_versions |
| `setting_extraction` | 纯设定提取 | extract_knowledge → search_knowledge |
| `draft_polish` | 草稿精修 | store_inspiration |
| `brainstorm_expand` | 灵感展开 | store_inspiration → search_knowledge |
| `daily_writing` | 日常写作流程 | write_chapter → compare_versions → store_chapter |
| `full_novel_reconstruct` | 拆书复写 | decompose_chapter → extract_style → count_words → reconstruct_chapter → compare_plot |
| `chapter_rewrite` | 单章复写 | decompose_chapter → count_words → reconstruct_chapter → compare_plot |

### 工作流引擎步骤类型

共 15 种步骤类型，可在技能步骤的 `tool` 字段引用：

| 步骤类型 | 用途 |
|----------|------|
| `read` | 读取章节/文档内容 |
| `decompose` | 拆解章节为场景和情节节拍 |
| `annotate` | 对拆解后的节点添加注释/修改标记 |
| `rewrite` | 根据注释重写章节 |
| `ask_user` | 向用户提问并等待输入 |
| `search` | 搜索知识库 |
| `compare_plot` | 对比原文和改写版的情节 |
| `diff` | 生成版本差异 |
| `generate_outline` | 生成大纲 |
| `write_chapter` | AI 续写章节 |
| `store_chapter` | 保存章节 |
| `extract_knowledge` | 提取结构化知识 |
| `count_words` | 统计字数 |
| `extract_style` | 提取文风特征 |

### 创建自定义技能

```yaml
# skills/my_custom_skill.yaml
- name: my_rewrite_pipeline
  description: "我的自定义复写流程：分析→改写→验证"
  triggers: [novel_chapter]
  steps:
    - tool: read
      label: "读取章节"
      params: {}
    - tool: decompose_chapter
      label: "拆解分析"
      params: {}
    - tool: reconstruct_chapter
      label: "智能复写"
      params:
        target_words: 3000
    - tool: compare_plot
      label: "质量校验"
      params: {}
```

---

## 3. 文风系统（YAML 叙事模板）

文风模板定义叙事策略的 6 个维度和注入写作提示的插槽（Slot）模板。系统默认模板在 `styles/default.yaml`，用户自定义模板存储在 `data/styles/`。

### 文件格式

```yaml
- name: my_style                # 文风名称（唯一标识）
  description: "文风描述"        # 描述文本
  priority: suggest              # 优先级：suggest（建议）| require（强制）
  applies_to: [标签1, 标签2]     # 适用场景标签
  narrative_strategy:
    pov: third_person_limited    # 叙事视角
                                 #   first_person | second_person
                                 #   third_person_limited
                                 #   third_person_omniscient
                                 #   third_person_cinematic
    pacing_curve: three_act      # 节奏曲线
                                 #   three_act | roller_coaster
                                 #   slow_burn | episodic
    reveal_density: moderate     # 信息揭示密度
                                 #   sparse | moderate | dense
    foreshadow_budget: 3         # 伏笔数量预算（0-10）
    chapter_arc:                 # 章节弧线模式
      setup_development_climax_resolution
    tone_guidance: "语调指引文本" # 自然语言语调描述
  slots:
    - target: system             # 注入到 system prompt
      content: |                 # 注入内容（Markdown 格式）
        这里是写入系统提示的模板内容。
    - target: scene              # 注入到场景提示
      content: |
        这里是写入场景提示的模板内容。
    - target: knowledge          # 注入到知识约束
      content: |
        这里是写入知识约束的模板内容。
```

### 预设文风

| 文风 | 适用场景 | 节奏 | 视角 |
|------|---------|------|------|
| `classic` | 日常/过渡/铺垫 | three_act | 第三人称有限 |
| `fast_paced` | 战斗/高潮/危机 | roller_coaster | 第三人称电影 |
| `dark` | 悬疑/背叛/牺牲 | slow_burn | 第三人称有限 |
| `poetic` | 回忆/独白/意境 | three_act | 第三人称全知 |

### 创建自定义文风

```yaml
# data/styles/my_romance_style.yaml
- name: romance_warm
  description: 温暖浪漫风——细腻情感描写，舒缓节奏
  priority: suggest
  applies_to: [恋爱, 日常, 甜蜜]
  narrative_strategy:
    pov: third_person_limited
    pacing_curve: slow_burn
    reveal_density: moderate
    foreshadow_budget: 2
    chapter_arc: setup_development_climax_resolution
    tone_guidance: "情感描写细腻，对话温柔，多用内心独白。环境描写烘托氛围。"
  slots:
    - target: system
      content: |
        温暖浪漫风格写作指引。
        注重情感细节和环境氛围渲染，对话自然温馨。
    - target: scene
      content: |
        本章风格指引：温暖浪漫。
        建议多用感官描写（温度/光线/气味）烘托氛围。
        情感表达自然流露，不做作。
    - target: knowledge
      content: |
        优先引用角色关系、情感羁绊相关设定。
        角色的情感状态应符合已建立的人物弧线。
```

---

## 4. 评审员自定义（YAML 人设）

评审员通过 YAML 人设文件定义，系统默认评审员在 `reviewers/default.yaml`，用户自定义评审员在 `data/reviewers/`。

### 文件格式

```yaml
- id: my_reviewer               # 评审员 ID（唯一标识）
  name: "评审员名称"             # 显示名称
  avatar: heart                  # 头像图标（Lucide Icons 名称）
  category: professional         # 分类：professional | reader | continuation
  active: true                   # 是否默认激活
  needs_knowledge: false         # 是否需要知识库上下文
  persona: |                     # 人设描述（Markdown，注入 LLM Prompt）
    你是一名资深XXX，拥有XX年经验。
    你关注的是：
    - 第一条标准
    - 第二条标准
    ...
    你的评审风格：XXX
  scoring_dimensions:            # 评分维度（5 项）
    - { name: "维度名", weight: 0.30, desc: "评分说明" }
    - { name: "维度名", weight: 0.25, desc: "评分说明" }
    - { name: "维度名", weight: 0.20, desc: "评分说明" }
    - { name: "维度名", weight: 0.15, desc: "评分说明" }
    - { name: "维度名", weight: 0.10, desc: "评分说明" }
```

### 评分维度权重规则

- 必须恰好 **5 项** 评分维度
- 权重之和 **必须等于 1.0**
- 建议按重要性递减排列（0.30 → 0.25 → 0.20 → 0.15 → 0.10）

### 系统预设评审员

| ID | 名称 | 分类 | 需要知识库 |
|----|------|------|-----------|
| `screenwriter` | 编剧 | professional | 否 |
| `literary_editor` | 文学编辑 | professional | 否 |
| `logic_checker` | 逻辑审校 | professional | 是 |
| `canon_purist` | 原著党 | professional | 是 |
| `power_fantasy_reader` | 爽文读者 | reader | 否 |
| `emotional_reader` | 情感型读者 | reader | 否 |
| `hardcore_reader` | 硬核党 | reader | 是 |
| `harsh_critic` | 挑刺王 | reader | 否 |
| `casual_reader` | 休闲读者 | reader | 否 |
| `ai_flavor_sniffer` | AI味嗅觉 | continuation | 否 |
| `character_voice_expert` | 角色语音专家 | continuation | 是 |
| `continuation_style_expert` | 续写风格专家 | continuation | 是 |
| `foreshadow_auditor` | 伏笔审计员 | continuation | 是 |
| `zhipi_compliance` | 知皮合规 | continuation | 是 |

---

## 5. 工具扩展（Python 实现）

如果你需要添加全新的工具给 Agent 使用，需在 `tools/impl/` 下创建工具实现文件，并在 `tools/executor.py` 中注册。

### 完整流程

**步骤 1**：在 `tools/impl/` 下创建实现文件：

```python
# tools/impl/my_tool.py
"""我的自定义工具实现。"""

TOOL_NAME = "my_custom_tool"           # 工具名称（用于 LLM function calling）
TOOL_DESCRIPTION = "我的自定义工具说明"  # 工具描述

def my_tool_handler(param1: str, param2: int = 10, **kwargs) -> dict:
    """
    工具处理函数。

    参数类型和描述会被自动提取为 JSON Schema.
    """
    result = do_something(param1, param2)
    return {"status": "ok", "result": result}
```

**步骤 2**：在 `tools/impl/` 的 `__init__.py` 中导入（或确认自动发现）：
- executor.py 使用 dispatch table 架构，支持自动注册机制
- 只需确保 `TOOL_NAME` 和 `TOOL_DESCRIPTION` 正确定义即可

**步骤 3**：在 `tools/tool_meta.py` 中添加元数据（可选）：

```python
# 在 tool_meta.py 的 TOOL_META 字典中
"my_custom_tool": ToolMeta(
    description="我的自定义工具",
    category="writing",  # writing | management | review | transform
    streaming=False,     # 是否流式输出
    dangerous=False,     # 是否危险操作（需用户确认）
)
```

### 注意事项

- 工具 handler 的**参数名和类型注解**会被自动提取为工具的 JSON Schema
- 可选参数必须有默认值
- 返回 `dict`，包含 `status` 和具体数据字段
- 危险操作（如批量删除）应将 `ToolMeta.dangerous` 设为 `True`
