# AnySpark v4 — UML 图索引

> 基于源码分析生成的 UML 图（PlantUML 格式）+ 接口提取。
> 
> 渲染方式：安装 PlantUML（`brew install plantuml` / `apt install plantuml`），然后 `plantuml -tpng *.puml`。
> 或使用 VS Code PlantUML 插件 / 在线渲染 https://www.plantuml.com/plantuml/uml/

## 类图（Class Diagram）

| 文件 | 内容 |
|------|------|
| [class_diagram.puml](class_diagram.puml) | **全系统类图**：9 个包的全部核心类、协议（Protocol/ABC）、继承/实现/组合关系 |

**关键结构**：
- **core**：`Model` / `StreamModel` / `Cancellable`（协议）+ `Agent`（循环）+ `ConversationStore`（存储 ABC）+ `EventEmitter`（事件总线）+ `ToolRegistry`（工具注册表）+ `RetryingModel`（重试包装）
- **app**：`DeepSeekModel`（模型适配）+ `ModelProvider` / `ModelRegistry`（运行时切换）+ `SqliteConversationStore` / `ChapterStore`（持久化）+ `TokenBudget`（压缩）
- **explore**：`IntentUnderstander` + `ExplorationEngine` / `ExplorationStrategy` + `DirectionCard` + `ProjectArchive`
- **align**：`AgencyStore` / `ManualStore` + `MindPlanner` / `SessionPlan` + 各种 Store
- **graph**：`GraphStore` + `Entity` / `Relation` / `GraphEvent`
- **check**：`ReviewEngine` + `SkeletonCheckItem` + `ReviewReport` / `Finding`
- **template**：`Template` + `ExternalLibrary` + `MaterialStore` + `PlotStore`
- **workflow**：`WorkflowDef` / `WorkflowNode` / `WorkflowEdge` + `WorkflowEngine` + `NodeRunner`（协议）

## 顺序图（Sequence Diagrams）

| 文件 | 内容 |
|------|------|
| [sequence_chat.puml](sequence_chat.puml) | **主对话流程**：用户 → API → Agent 循环 → 模型 → 工具执行 → 响应；含 SSE 流式 / 插话 / 取消 |
| [sequence_explore.puml](sequence_explore.puml) | **探索-判别双循环**：意图理解 → 并行 4 探索者 → 方向卡 → 判别固化 |
| [sequence_workflow.puml](sequence_workflow.puml) | **工作流执行**：任务创建 → 顺序/分支/循环调度 → 断点恢复 → 人工确认 |

## 状态机图（State Machine Diagrams）

| 文件 | 内容 |
|------|------|
| [state_agent_loop.puml](state_agent_loop.puml) | **Agent 循环状态机**：Idle → Running（构建上下文 → 调模型 → 解析 → 执行工具 → 回填 → 迭代）→ FinalAnswer / Error / Aborted |
| [state_workflow.puml](state_workflow.puml) | **工作流状态机**：TaskStatus（queued → running → done/failed/cancelled/waiting_approval）+ NodeStatus（pending → running → done/failed/skipped）+ 5 种节点行为 |

## 接口全清单

| 文件 | 内容 |
|------|------|
| [interfaces.md](interfaces.md) | **全部接口提取**：7 个协议接口 + 80+ HTTP API 端点 + 21 个存储类 |

**协议接口摘要**：
1. `Model` — 模型协议（respond）
2. `StreamModel` — 流式模型协议（respond_stream）
3. `Cancellable` — 可取消协议（set_cancelled）
4. `ToolImplementer` — 工具可调用对象协议
5. `ConversationStore` — 对话存储接口（ABC）
6. `ContextCompressor` — 上下文压缩协议
7. `NodeRunner` — 工作流节点执行器协议
