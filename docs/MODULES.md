# 模块定义

---

## 1. 对话界面模块 (Chat Interface)

| 属性 | 内容 |
|------|------|
| 层级 | 用户层 |
| 职责 | 提供聊天式交互界面，消息中内嵌可视化组件 |
| 依赖 | SSE 服务、消息组件库 |
| 难度 | 中等 |
| 状态 | 🔄 进行中 |
| 实现 | `frontend/src/components/ChatPanel.tsx` |

**接口:**
| 接口名 | 说明 | 输入 → 输出 |
|--------|------|------------|
| `sendMessage` | 发送聊天消息 | `{ text, attachments }` → `{ messageId }` |
| `onAgentMessage` | 接收Agent流式回复 | `Stream<{ text, embeddedCards, actions }>` |
| `onKnowledgeConfirm` | 用户确认/拒绝知识提案 | `{ knowledgeId, action: accept/reject/modify }` |

---

## 2. 可视化仪表盘模块 (Visualization Dashboard)

| 属性 | 内容 |
|------|------|
| 层级 | 用户层 |
| 职责 | 知识百科、角色卡、时间线、地图、图谱、伏笔板等可视化组件集合 |
| 依赖 | 知识库管理器 API、D3.js / Leaflet |
| 难度 | 中等 |
| 状态 | 🔄 进行中（核心可视化已实现，WorldMap/ForeshadowBoard 待开发） |
| 实现 | `frontend/src/components/` |

**子组件:**
| 组件 | 说明 | 技术选型 |
|------|------|---------|
| WikiViewer | 类 Wiki 的知识条目查看/编辑 | React Router + Markdown render |
| CharacterCard | 角色信息卡，含关系、轨迹、时间线 | 自研组件 |
| TimelineView | 水平滚动时间线，标注事件/伏笔/章节 | D3.js + 自研 |
| WorldMap | 4D 地理+时间维度世界地图 | Leaflet + 时间滑块 |
| KnowledgeGraph | 实体关系图（力导向图） | D3.js force layout |
| ForeshadowBoard | 伏笔→回收追踪看板 | 自研看板组件 |

**接口:**
| 接口名 | 说明 | 输入 → 输出 |
|--------|------|------------|
| `getEntity` | 获取实体详情 | `{ entityId }` → `Entity` |
| `getTimeline` | 获取时间线数据 | `{ projectId, filters }` → `TimelineEvent[]` |
| `getGraph` | 获取图数据 | `{ projectId, depth }` → `{ nodes, edges }` |

---

## 3. 知识抽取 Agent (Knowledge Extractor)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 从对话文本、上传文档中自动识别实体、关系、事件，提出结构化知识提案 |
| 依赖 | LLM 网关、知识库管理器、一致性校验 Agent |
| 难度 | 困难 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/extractor.py` |

**核心能力:**
- 实体识别：人物、地点、物品、组织、概念
- 关系提取：人物间关系、所属关系、因果关系
- 事件提取：事件发生时间、地点、参与者
- 伏笔检测：模糊表述、暗示性语句 → 标记为伏笔
- 知识提案：不是直接写入，而是生成"知识变更提案"交给用户确认

**接口:**
| 接口名 | 说明 | 输入 → 输出 |
|--------|------|------------|
| `extractFromText` | 从文本提取知识 | `{ text, context }` → `KnowledgeProposal[]` |
| `extractFromDocument` | 从文档提取知识 | `{ documentId }` → `KnowledgeProposal[]` |
| `suggestKnowledge` | 主动建议补充知识 | `{ projectId, trigger }` → `KnowledgeProposal[]` |

---

## 4. 上下文管理器 (Context Manager)

| 属性 | 内容 |
|------|------|
| 层级 | 业务层 |
| 职责 | **核心组件** — 为写作Agent构建最优上下文，确保知识约束生效 |
| 依赖 | 知识图谱（Neo4j）、全文搜索（SQLite FTS5） |
| 难度 | 困难 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/context_manager.py` |

**工作流程:**
1. 接收写作任务（写什么、风格、位置）
2. 查询相关知识（图查询 + 语义检索）
3. 按相关性排序 + 剪裁 token 预算
4. 构建 system prompt：**明确列出"必须使用的知识"和"禁止编造的内容"**
5. 输出给写作 Agent

**接口:**
| 接口名 | 说明 | 输入 → 输出 |
|--------|------|------------|
| `buildWritingContext` | 构建写作上下文 | `{ task, projectId, constraints }` → `PromptContext` |
| `validateAgainstKnowledge` | 校验文本是否与知识库一致 | `{ text, knowledgeRefs }` → `ValidationResult` |

---

## 5. 写作 Agent (Writing Engine)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 在知识约束下生成小说正文，严格基于知识库 |
| 依赖 | 上下文管理器、LLM 网关、一致性校验 Agent |
| 难度 | 困难 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/writer.py` + Agent Loop |

**约束机制:**
- **强约束模式**（知识库详尽时）：LLM 只能基于提供的知识写作，不得新增任何事实
- **弱约束模式**（知识库不完整时）：LLM 可补充细节，但需标记"待确认"由用户审批
- 生成后经过一致性校验，标记违规行

**接口:**
| 接口名 | 说明 | 输入 → 输出 |
|--------|------|------------|
| `write` | 写作 | `{ context, instruction, mode }` → `Stream<TextChunk>` |
| `rewrite` | 改写已有段落 | `{ text, instruction, context }` → `Stream<TextChunk>` |
| `expand` | 扩写 | `{ text, targetLength, context }` → `Stream<TextChunk>` |

---

## 6. 工作流 Agent (Workflow Agent)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 通过对话理解用户意图，自动生成/修改写作工作流定义 |
| 依赖 | LLM 网关、工作流执行引擎 |
| 难度 | 困难 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/workflow_engine.py` |

**工作流定义示例 (JSON):**
```json
{
  "name": "每日写作流程",
  "steps": [
    { "agent": "knowledge_extractor", "input": "今日草稿", "mode": "incremental" },
    { "agent": "planner", "input": "知识变更", "task": "建议今日写作方向" },
    { "agent": "writer", "input": "规划结果", "chapter": "第5章", "mode": "strict" },
    { "agent": "editor", "input": "写作结果", "task": "润色" }
  ]
}
```

---

## 7. 知识库管理器 (Knowledge Manager)

| 属性 | 内容 |
|------|------|
| 层级 | 业务层 |
| 职责 | 知识实体的 CRUD、版本追踪、关联查询、冲突检测 |
| 依赖 | Neo4j、JSON 文件存储 |
| 难度 | 中等 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/knowledge.py`, `src/core/graph_store.py` |

---

## 8. 项目/章节管理器 (Project Manager)

| 属性 | 内容 |
|------|------|
| 层级 | 业务层 |
| 职责 | 小说项目创建、章节管理、版本历史、导出 |
| 依赖 | JSON 文件存储 |
| 难度 | 简单 |
| 状态 | ✅ 已实现 |
| 实现 | `src/routes/chapters.py`, `src/data/json_store.py` |

---

## 9. LLM 网关 (LLM Gateway)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层支撑 |
| 职责 | 统一多模型接入、请求限流、重试回退、Token 统计 |
| 依赖 | 外部 LLM API（DeepSeek / OpenAI 兼容） |
| 难度 | 中等 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/llm_client.py` |

---

## 10. 工作流执行引擎 (Workflow Engine)

| 属性 | 内容 |
|------|------|
| 层级 | 业务层 |
| 职责 | 解析工作流 JSON 定义，按序/条件/并行调用 Agent |
| 依赖 | 所有 Agent |
| 难度 | 中等 |
| 预估 | 8 人天 |
| 状态 | ✅ 已实现 |

---

## 11. Agent 决策引擎

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 内容分类 → 工具规划 → 执行反馈。LLM 自主判断输入类型并选择处理路径 |
| 依赖 | LLM 网关、工具注册表、技能系统 |
| 状态 | ✅ 已实现 |

分类类型: setting_document / novel_chapter / story_fragment / inspiration_note / instruction / mixed

## 12. 工具注册表

| 属性 | 内容 |
|------|------|
| 层级 | AI 层支撑 |
| 职责 | 注册所有可用工具，为 Agent 提供 tool-use 能力 |
| 状态 | ✅ 已实现 |

工具: extract_knowledge, store_chapter, store_inspiration, search_knowledge, write_chapter, compare_versions, ask_user

## 13. 技能系统

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 加载 skills/*.yaml 复合工作流技能，与 Agent 整合 |
| 状态 | ✅ 已实现 |

预装: full_novel_import, setting_extraction, draft_polish, brainstorm_expand, daily_writing, full_novel_reconstruct, chapter_rewrite

## 14. 拆书复写工具集

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 将完整小说拆解为结构化叙事数据（场景/情节节拍/风格），再基于数据逐章复写 |
| 状态 | ✅ 已实现 |

工具: decompose_chapter（章节→场景分解）, extract_style（文风特征提取）, reconstruct_chapter（情节大纲→全文章节复写）, compare_plot（原文vs复写情节对比）, count_words（字数统计）

## 15. 评审团系统

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 + 业务层 |
| 职责 | 多维度章节评审：多位评审员（专业审稿人+读者代言人）并发评审，汇总为结构化报告 |
| 依赖 | LLM网关、知识库管理器、JSON存储 |
| 状态 | ✅ 已实现 |

**子组件:**
| 组件 | 说明 |
|------|------|
| ReviewerRegistry | 从 reviewers/*.yaml 加载评审员人设定义，支持自定义 |
| ReviewPanel | 编排层：管理激活状态、并发/串行执行策略、进度追踪 |
| ReviewSummarizer | 汇总Agent：整合所有评审意见为结构化报告（评分+共识+分歧+建议） |

**预设评审员 (8位):**
| ID | 名称 | 分类 | 核心关注 |
|----|------|------|---------|
| screenwriter | 编剧 | 专业 | 三幕结构、戏剧张力、场景转换 |
| literary_editor | 文学编辑 | 专业 | 文笔质量、风格一致性、叙事视角 |
| logic_checker | 逻辑审校 | 专业 | 情节漏洞、时间线矛盾、设定冲突 |
| power_fantasy_reader | 爽文读者 | 读者 | 爽感密度、节奏、金手指 |
| emotional_reader | 情感型读者 | 读者 | 情感共鸣、角色代入 |
| hardcore_reader | 硬核党 | 读者 | 世界观自洽、设定考据 |
| harsh_critic | 挑刺王 | 读者 | 原创性、角色智商、诚意度 |
| casual_reader | 休闲读者 | 读者 | 可读性、吸引力、追更欲 |

工具: run_review（启动评审）, manage_reviewers（管理评审员）

## 16. 剧情卡片系统

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 + 用户层 |
| 职责 | 在剧情规划时生成多个走向选项卡片，阻塞等待用户选择后继续 |
| 依赖 | LLM网关、知识库管理器、大纲系统、question_manager |
| 状态 | ✅ 已实现 |

**交互流程:**
1. Agent 调用 `suggest_plot_directions` 工具（传入剧情需求）
2. 工具读取当前章节/大纲/知识库，调用 LLM 生成 3-5 个不同走向
3. 返回 `{type: "plot_cards", cards: [...]}` 特殊结构
4. agent_loop 检测此类型 → 创建阻塞问题 → 通过 SSE 发送到前端
5. 前端渲染 PlotCardSelector 卡片组件
6. 用户可以: 点击选择某个方向 / 输入自定义方向 / 全部拒绝
7. 答案回传 → agent_loop 恢复 → Agent 根据选择继续

**卡片结构:**
| 字段 | 说明 |
|------|------|
| title | 方向名称（6字以内） |
| description | 具体描述（50-100字） |
| key_events | 关键事件列表 |
| tone | 基调标签（热血/虐心/悬疑/治愈等） |
| impact | 对后续剧情的影响 |
| risk | 创作风险/难点 |

工具: suggest_plot_directions

---

## 17. 叙事逻辑引擎 (Narrative Logic Engine)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 + 业务层 |
| 职责 | 写作时自动检测叙事约束违规，计算置信度评分，传播约束变更影响 |
| 依赖 | Neo4j 知识图谱、LLM 网关 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/narrative_logic/` |

**子模块:**
| 模块 | 文件 | 职责 |
|------|------|------|
| 约束检查器 | `constraint_checker.py` | 检测写作内容是否违反叙事约束（时间线、角色关系、设定一致性） |
| 置信度评分器 | `confidence_scorer.py` | 为知识图谱中的实体和关系计算置信度 |
| 约束持久化 | `constraint_store.py` | 叙事约束的结构化存储与查询 |
| 影响传播器 | `impact_propagator.py` | 当某个约束被修改时，自动计算并传播影响范围 |
| 数据模型 | `models.py` | 叙事逻辑相关数据模型定义 |

---

## 18. 交互式故事系统 (Interactive Story)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 + 用户层 |
| 职责 | 图谱驱动的分支叙事引擎，支持读者选择驱动剧情走向 |
| 依赖 | Neo4j 知识图谱、LLM 网关 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/interactive_agent.py` + `src/core/interactive_store.py` |

---

## 19. 本体生成器 (Ontology Generator)

| 属性 | 内容 |
|------|------|
| 层级 | AI 层 |
| 职责 | 从知识图谱自动生成世界观本体结构 |
| 依赖 | Neo4j 知识图谱 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/ontology_generator.py` |

---

## 20. 图搜索增强 (Graph Search)

| 属性 | 内容 |
|------|------|
| 层级 | 业务层 |
| 职责 | 高级图搜索与路径分析，支持最短路径、社区发现等图算法 |
| 依赖 | Neo4j 知识图谱 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/graph_search.py` |

---

## 21. 版本更新检测 (Update Checker)

| 属性 | 内容 |
|------|------|
| 层级 | 支撑层 |
| 职责 | 通过 GitHub Releases API 检查最新版本，前端设置面板可开关 |
| 依赖 | GitHub API |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/update_checker.py` + `src/routes/update.py` + `frontend/SettingsModal.tsx` |

---

## 22. 事件存储 (Event Store)

| 属性 | 内容 |
|------|------|
| 层级 | 支撑层 |
| 职责 | 事件持久化与查询，支持事件历史回溯 |
| 依赖 | JSON 文件存储 |
| 状态 | ✅ 已实现 |
| 实现 | `src/core/event_store.py` |

---

## 23. 数据层模块化存储 (Modular Store)

| 属性 | 内容 |
|------|------|
| 层级 | 数据层 |
| 职责 | 模块化 JSON 存储层，BookStore / ChapterStore / MetaStore / SessionStore / WorldbuildingStore |
| 依赖 | JSON 文件存储 |
| 状态 | ✅ 已实现 |
| 实现 | `src/data/stores/` |
