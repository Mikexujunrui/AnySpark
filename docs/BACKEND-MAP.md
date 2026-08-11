# AnySpark v4 后端业务逻辑地图

> **用途**：后端 108 模块 / 22373 行的"导航图"——哪个机制在哪、数据怎么流、哪里可能重复/缺失。
> **创建**：2026-08-11（S79-S81 架构收敛后，三 worker 侦察 + 主循环整合）
> **配套**：DESIGN.md（设计规格）、PROGRESS.md（阶段台账）、DEV-AGENT.md（接入通道）

---

## 1. 分层架构总览

```
┌─────────────────────────────────────────────────────────┐
│ 装配层  app.py（601 行，组合根）                         │
│   创建 22 store + 16 engine → AppDeps → 15 router 挂载    │
│   + start_bg_worker + shutdown 连接关闭                    │
├─────────────────────────────────────────────────────────┤
│ 路由层  routes_*.py（15 个领域 router，~164 端点）        │
│   HTTP 入口 → 校验 → 调领域逻辑/engine → 响应              │
├─────────────────────────────────────────────────────────┤
│ Agent 工具层  toolkit.py + tools_*.py（23 个工具）        │
│   Agent 循环内可调用的领域能力（按 enable_* 开关点亮）      │
├─────────────────────────────────────────────────────────┤
│ 基础设施  deps/tasks/agent_factory/context/pipeline/      │
│   recorder/export/codex/stats/workspace/schemas           │
├─────────────────────────────────────────────────────────┤
│ 领域包    align（对齐） explore（探索） graph（图谱）       │
│   template（模式库） workflow（流程） play（推演）          │
│   review（评审团） check（检测网）                          │
├─────────────────────────────────────────────────────────┤
│ 内核      core（Agent 循环/工具协议/事件/存储接口/连接）    │
└─────────────────────────────────────────────────────────┘
依赖方向：core ← 领域包 ← app（单向，无环）
```

## 2. 核心业务流

### 2.1 写作主链路（chat → 落盘 → 后台）
```
POST /api/chat 或 /api/chat/stream（routes_chat）
  → ChatRequest（message/book_id/enable_*/skip_inject/context_mode）
  → make_agent(deps, ...)（agent_factory，224 行核心装配）
      ├ 心智规划 MindPlanner.plan → SessionPlan（collab/style/habit）
      ├ 工具注册 build_toolkit（按 enable_* 点亮）
      ├ 注入块装配（prepend: 项目简介/协作约定；append: 叙事树/能动性/
      │  倾向/伏笔/设定/心智/变更通知/场景记忆/技巧索引/计划/破限）
      └ 模型选择（档位温度映射 + thinking 覆盖）
  → Agent.run（core.loop 循环：模型→工具→回填→终答）
      ├ 事件流 turn_start→text_delta/tool_call→tool_execution_start/end→tool_result→done
      ├ recorder 记录（思维链只进记录不进上下文）
      └ steering 插话（/api/chat/steer → agent.steer）
  → 响应：ChatResponse / SSE 帧
  → 后台（不阻塞响应）：summarize 场景记忆 + 图谱抽取/伏笔回收/学习审查
```

### 2.2 后台任务链路（tasks.py 单例 worker 线程）
```
_bg_queue（deps.bg_queue）→ 7 种任务：
  chapter     章节落盘后：图谱抽取 + 伏笔回收 + 学习审查
  refine      信号→偏好提炼进 manual
  skill_drafts 心智联动+信号→skill 候选草稿（人工确认转正）
  summarize   会话结束→场景记忆归档
  batch_rewrite / batch_review  批量改写/审读
```

### 2.3 心智数据流（操作 → 提炼 → 注入）
```
用户操作（accept/修改/删除）→ /api/signals（SignalStore）
  → 后台 refine_from_signals（PreferenceExtractor，关键词合并防碎片）
  → manual_entries（merge_add）
  → MindPlanner.plan 读取 → SessionPlan 注入下一轮 agent
另一条：章节落盘 → review_for_learning（LLM 审出偏好/雷区）→ manual
心智变更 → manual_notices → 下一轮 agent 告知用户（知情+指导权）
```

### 2.4 探索链路（种子 → N 路 → 判别）
```
用户意图 → IntentUnderstander（种子确认）
  → StrategySet 差异化分派 → Explorer 并行 N 路（上下文隔离）
  → DirectionCard（方向卡+维度+项目档案）
  → 判别选优（LLM 判别器 + 用户在环选择）
  → path 定向再探索（A→B 桥）/ roleplay（场景内 N 路+判别）
固化：方向卡 → explore/archive（项目档案）；约束 → setting_constraints（⚠️断链见审计）
```

## 3. 路由层职责表（15 router，~164 端点）

| Router | 端点区 | 核心依赖 |
|---|---|---|
| routes_chat | chat/stream/cancel/steer/stats/direction/candidates/rewrite | model/store/chapters/active_*/bg_queue |
| routes_conversations | 会话 CRUD/fork/rename + 模型注册表 CRUD/激活 | store/models |
| routes_books | 书架（项目枚举/创建/删除） | workspace/chapters |
| routes_chapters | 章节 CRUD/patch/export/wrapup | chapters/workspace/export |
| routes_manual→routes_mind | manual/brief/signals/mind 全部 | manual/signals/workspace/mind_planner |
| routes_settings | 设定档 categories/CRUD/uncensored/extract | settings/model/workspace |
| routes_skills | 技巧 generate/CRUD/drafts + bias | skills/skill_generator/bias |
| routes_agency | 能动性 CRUD/generate + 批量改写/审读 | agency/bias/batches/bg_queue |
| routes_explore | intent/cards/path/dims/archive + check | dim_store/archive/explore |
| routes_plot | 模式库 templates/伏笔 plot/资料 materials | plots/templates_external/materials |
| routes_graph | 图谱 types/entities/relations/events/context/extract/impact | graph/graph_extractor/impact |
| routes_story | 计划 plan/叙事树 nodes/threads/layout | plans/story_tree/story_threads |
| routes_workflow | 工作流模板/草稿/任务 CRUD+run | workflow_store/engine/generator |
| routes_play | 推演 sessions/choose/branch + 评审团 review | play_engine/review_panel |
| routes_tools | 扩展工具 CRUD/approve + codex/ingest/export | ext_tools/workspace/codex/export |

## 4. Agent 工具层（23 工具 × 开关）

| 工具 | 用途 | 开关 |
|---|---|---|
| list_chapters / read_chapter / write_chapter | 章节读/写（写作主链路） | 常驻 |
| explore_direction | 方向建议（种子含糊时） | 常驻 |
| skill_lookup | 按需细看技巧全文 | enable_domain |
| graph_query / graph_register | 图谱查证/登记 | enable_domain |
| plot_list | 伏笔查看（A/B 分级） | enable_domain |
| plan_list | 剧情计划查看 | enable_domain |
| setting_query | 设定档查证 | enable_domain |
| search_chapters / read_context | 正文检索/锚点阅读 | enable_domain |
| mind_register / mind_manage | 心智登记/管理 | enable_domain |
| skill_refine | 技巧提炼候选 | enable_domain |
| role_play | 角色推演 | enable_domain |
| ingest_document | 资料消化（⚠️与端点重复见审计） | enable_domain |
| register_tool | 扩展工具注册 | enable_domain |
| path_explore | 定向再探索 | enable_domain |
| read_material | 读资料摘要卡 | enable_extras |
| search_web | 网络搜索 | enable_search |
| run_code | 代码沙箱 | enable_codex |
| workflow_* | 工作流工具 | enable_workflow |
| play_* | 互动推演工具 | enable_play |
| material_* | 资料/摘要卡 | enable_extras |

## 5. 数据载体清单（22 store / 表）

| Store | 包/文件 | 表 | 读写方 |
|---|---|---|---|
| SqliteConversationStore | app/store/sqlite | conversations/messages | chat/routes_conversations |
| ChapterStore | app/store/sqlite | chapters/chapter_versions | chapters 路由/写作工具 |
| ManualStore | align/manual | manual_entries/manual_notices | 心智全链 |
| BiasStore | align/bias | ai_bias | agent 注入/skills 面板 |
| AgencyStore | align/agency | agency_levels/agency_state | 能动性全链 |
| WritingSkillStore | align/skills | writing_skills/drafts | 技巧注入 |
| SignalStore | align/signals | signals | 信号采集 |
| StoryPlanStore | align/plan | chapter_plans | 计划 |
| StoryTreeStore/StoryThreadStore | align/storytree | story_nodes/story_threads | 叙事树/线进度 |
| WorldSettingStore | align/worldsettings | world_settings/setting_categories | 设定档 |
| MemoryStore | align/summarize | scene_memories | 场景记忆 |
| DimensionStore/ProjectArchive | explore/direction | explore_dims/archive | 探索 |
| PlotStore | template/plot | plots | 伏笔 |
| MaterialStore | template/materials | materials | 资料库 |
| ExternalLibrary | template/patterns | templates | 模式库 |
| GraphStore | graph/schema | entities/relations/events/types | 图谱 |
| PlayStore | play/tree | play_sessions/tree | 推演 |
| WorkflowStore | workflow/store | templates/drafts/tasks | 工作流 |
| ModelRegistry | app/models/registry | model_configs | 运行时模型 |
| ExtensionToolStore | app/server/tools_extensions | ext_tools | 扩展工具 |
| 全部连接 | core/db.connect | — | S79 收敛一处 |

## 6. 十大机制 → 代码落点

| 机制 | 落点 |
|---|---|
| 1 探索-判别 | explore 包 + routes_explore |
| 2 能动性 | align/agency + agent_factory 注入 |
| 3 对齐系统 | align/manual+mind+signals+summarize |
| 4 低摩擦交互 | routes_chat(direction/candidates/rewrite) + 前端 |
| 5 前端空间 | frontend/（并行会话） |
| 6 结构模式模板 | template/patterns + plot |
| 7 多智能体探索 | explore/explorers + strategy |
| 8 用户自定义规则 | check/rules + tools_extensions（人工批准） |
| 9 检测网 | check 包 + review 包（S71 有意重复） |
| 10 资料消化 | tools_domain ingest + routes_tools ingest_upload（⚠️重复） |

## 7. 审计结论（重复 / 交叉 / 冗余 / 缺失）

> 三 worker 只读侦察 + 主循环交叉核对。按严重度分级，处置需主人定夺。

### 🔴 重复（实质，建议修）

| # | 发现 | 位置 | 建议 |
|---|---|---|---|
| R1 | **JSON 宽容解析 8 处各自实现**（围栏剥离+JSON 提取+容错逻辑雷同） | align/extract:105、mindgen:121,133、mindup:61,119、skillgen:130、explore/intent:67、explore/strategy:28、graph/extract:201 | 收敛到 core 一个 `parse_llm_json()` 工具函数（纯简化，符合 S62 去垃圾补丁精神） |
| R2 | **ingest_document 工具 vs ingest_upload 端点重复实现同一套消化编排**（is_card 判别逐字重复） | tools_domain.py:329 vs routes_tools.py | 抽共享 `ingest_pipeline()` 到独立模块，两处调用 |
| R3 | explore_direction 工具 vs routes_explore 端点各自组装意图+探索+维度/模板注入（轻度） | toolkit.py vs routes_explore.py | 抽共享组装函数 |

### 🔴 断链（功能缺失）

| # | 发现 | 位置 | 建议 |
|---|---|---|---|
| G1 | **setting_constraints（探索固化约束表）生产只读不写**——add_constraint 仅测试调用，routes_explore 读它当"墙"但无生产固化入口 | explore/direction.py:224 | 补生产入口（探索结果固化 API）或删表降级为纯注入——需主人定语义 |

### 🟡 冗余 / 混淆风险

| # | 发现 | 建议 |
|---|---|---|
| Y1 | **review 包 vs check 包同名导出 run_review/ReviewReport**（S71 已标记"有意重复"：硬伤 vs 人格化，第三处才抽公共） | 低成本消歧：review 加别名导出或文档显著标注，防误 import |
| Y2 | server/retry.py 纯 re-export 兼容层；core/tools.py（echo/add）生产从不注册 | 保留（测试用）或清理，低优先 |
| Y3 | 无"工具清单单一真相"（23 工具名/开关/用途散落 6 文件） | 本地图 §4 已补——代码侧可后续建 `tools_manifest` 常量（非必须） |

### ✅ 已核查无问题

- manual vs bias vs agency 三表边界清晰（主体/来源/职责不同）
- mind/mindgen/mindup 是 manual 的读/建议/写三端，互补不重复
- skills/skillgen/skill_lookup 三链闭环
- graph 内部单向依赖（schema←extract/inject/verify）
- workflow vs play 不重叠（确定性执行管线 vs 模型自由推演）
- 包依赖无环（唯一跨层：desktop→server，正常）
- tools_writing/tools_domain/tools_extras 三层边界清晰

## 8. 快速定位索引

- **改某个机制**：查 §6 落点 → 对应领域包/路由
- **加一个 agent 工具**：tools_domain 建 implementer → toolkit 注册 → 开关分组
- **加一个 HTTP 端点**：对应 routes_*.py（15 个之一）
- **改存储结构**：core/db.connect 拿连接 → 对应 store 的 _init_schema
- **排查请求链路**：routes_chat → agent_factory → core.loop → 工具 → store
- **排查后台任务**：tasks.py 派发表 + deps.bg_queue
