# AnySpark v4 — 接口全清单（Interface Extraction）

> 基于 UML 类图/顺序图/状态机图提取。分为 **协议接口（Protocol/ABC）**、**HTTP API 接口**、**存储接口** 三大类。

---

## 一、协议接口（Protocol / ABC）— 核心解耦点

### 1.1 `Model` — 模型协议（core.protocol）

```python
class Model(Protocol):
    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput: ...
```

**实现者**：
| 实现类 | 位置 | 说明 |
|--------|------|------|
| `DeepSeekModel` | `models/deepseek.py` | 真实 DeepSeek 调用器（OpenAI SDK） |
| `RetryingModel` | `core/retry.py` | 组合式重试包装（任意 Model 可套） |
| `ModelProvider` | `models/registry.py` | 运行时模型注册表委托（动态切换） |

---

### 1.2 `StreamModel` — 流式模型协议（core.protocol）

```python
class StreamModel(Protocol):
    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Event], None],
    ) -> ModelOutput: ...
```

**实现者**：
| 实现类 | 说明 |
|--------|------|
| `DeepSeekModel` | 流式生成 text_delta / toolcall_delta 事件 |
| `RetryingModel` | 流式透传 + 零 delta 安全重试 |
| `ModelProvider` | 委托给当前激活 DeepSeekModel |

---

### 1.3 `Cancellable` — 可取消协议（core.protocol）

```python
class Cancellable(Protocol):
    def set_cancelled(self, check: Callable[[], bool]) -> None: ...
```

**实现者**：
| 实现类 | 说明 |
|--------|------|
| `RetryingModel` | 重试退避睡眠期间分段检查取消 |

---

### 1.4 `ToolImplementer` — 工具可调用对象协议（core.protocol）

```python
class ToolImplementer(Protocol):
    def __call__(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult: ...
```

**实现者**：所有工具函数（echo_implementer / add_implementer / 写作工具 / 领域工具等）

---

### 1.5 `ConversationStore` — 对话存储接口（core.storage）

```python
class ConversationStore(ABC):
    def create(conversation_id: str | None = None) -> Conversation: ...
    def get(conversation_id: str) -> Conversation | None: ...
    def list_conversations() -> list[Conversation]: ...
    def append(conversation_id: str, message: Message) -> None: ...
    def replace_messages(conversation_id: str, messages: list[Message]) -> None: ...
    def messages(conversation_id: str) -> list[Message]: ...
    def fork(conversation_id, fork_point?, inherit_messages?) -> Conversation | None: ...
```

**实现者**：
| 实现类 | 位置 | 说明 |
|--------|------|------|
| `InMemoryConversationStore` | `core/storage.py` | 内存实现（测试/演示） |
| `SqliteConversationStore` | `store/sqlite.py` | SQLite 持久化实现 |

---

### 1.6 `ContextCompressor` — 上下文压缩协议（core.protocol）

```python
ContextCompressor = Callable[[list[Message]], list[Message]]
```

**实现者**：
| 实现类 | 位置 | 说明 |
|--------|------|------|
| `TokenBudget.compress` | `server/context.py` | tiktoken 精确计数 + prune/summarize 两阶段 |

---

### 1.7 `NodeRunner` — 工作流节点执行器协议（workflow.engine）

```python
class NodeRunner(Protocol):
    def __call__(self, ctx: RunContext, node: WorkflowNode) -> NodeResult: ...
```

**实现者**：组合根注入的闭包函数（agent/script/approval 节点的具体执行逻辑）

---

## 二、HTTP API 接口 — 全部 REST 端点

### 2.1 健康检查 & 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stats` | 验证指标（修改率/提问率/完成率） |

### 2.2 对话 & Agent 循环

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 主对话入口（同步返回） |
| POST | `/api/chat/stream` | SSE 流式对话 |
| POST | `/api/chat/cancel` | 取消当前生成 |
| POST | `/api/chat/steer` | 运行中插话 |
| POST | `/api/chat/direction` | 方向声明（低摩擦交互） |
| POST | `/api/chat/candidates` | 候选卡堆 |
| POST | `/api/chat/rewrite` | 改写渐变条 |
| POST | `/api/chapters/{id}/wrapup` | 一章收尾 |

### 2.3 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 列出全部会话 |
| POST | `/api/conversations/{id}/fork` | 会话继承派生（S58c） |

### 2.4 模型管理（S47 运行时模型）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 列出模型配置 |
| POST | `/api/models` | 新增/更新模型配置 |
| DELETE | `/api/models/{id}` | 删除模型配置 |
| POST | `/api/models/{id}/activate` | 切换激活模型 |

### 2.5 说明书（心智模型 / 对齐系统）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/manual` | 列出说明书条目 |
| POST | `/api/manual` | 新增条目 |
| PATCH | `/api/manual/{id}` | 修改条目（内容/锁定） |
| DELETE | `/api/manual/{id}` | 删除条目 |
| POST | `/api/manual/decay` | 活跃度衰减（S61） |

### 2.6 心智规划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/mind/reconcile` | 跨会话对账（条目 vs 信号） |
| POST | `/api/mind/agency-suggest` | AI 建议档位（L2） |
| GET | `/api/mind/agency-suggest` | 规则推断（不调 LLM） |

### 2.7 项目简介

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/brief` | 读项目简介 |
| POST | `/api/brief` | 写项目简介 |
| POST | `/api/brief/generate` | AI 生成简介草案 |

### 2.8 信号采集

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/signals` | 采集用户操作信号（accepted/deleted/rejected/negative/custom/modified） |

### 2.9 探索系统

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/explore/intent` | 种子 → 概念卡 + 歧义点 |
| POST | `/api/explore/cards` | 确认意图 → 4 张方向卡 |
| GET | `/api/explore/dims` | 列出探索维度 |
| POST | `/api/explore/dims` | 新增维度 |
| PATCH | `/api/explore/dims/{id}` | 修改维度 |
| DELETE | `/api/explore/dims/{id}` | 删除维度 |
| POST | `/api/explore/archive` | 固化方向 |
| GET | `/api/explore/archive` | 列出已固化方向 |

### 2.10 检测网

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/check` | AI 多检测者审读 |
| POST | `/api/check/rule` | 规则编译（确定性检测） |

### 2.11 模式库 & 剧情计划

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/templates` | 列出模板（L2+L3） |
| POST | `/api/templates/import` | 导入外部模板 |
| DELETE | `/api/templates/{name}` | 删除外部模板 |
| POST | `/api/plot` | 生成关键点 |
| GET | `/api/plot` | 列出关键点 |
| PATCH | `/api/plot/{id}` | 修改关键点 |
| POST | `/api/plot/item` | 手动添加关键点 |
| POST | `/api/plot/import-resolve` | 导入解析 |
| DELETE | `/api/plot/{id}` | 删除关键点 |

### 2.12 资料消化

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/materials` | 上传/消化资料 |
| GET | `/api/materials` | 列出资料 |
| GET | `/api/materials/{id}` | 获取单条资料 |

### 2.13 能动性协议

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agency` | 列出档位 + 当前档 |
| POST | `/api/agency` | 设置当前档位 |
| POST | `/api/agency/add` | 新增自定义档位 |
| POST | `/api/agency/generate` | AI 生成档位 |
| PATCH | `/api/agency/{id}` | 修改档位 |
| DELETE | `/api/agency/{id}` | 删除档位 |
| POST | `/api/agency/reset` | 恢复默认五级 |

### 2.14 批量任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/batch/rewrite` | 批量重写 |
| POST | `/api/batch/review` | 批量审读 |
| GET | `/api/batch/{id}` | 查询批量任务状态 |

### 2.15 世界设定

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings/categories` | 列出设定类别 |
| POST | `/api/settings/categories` | 新增类别 |
| PATCH | `/api/settings/categories/{id}` | 修改类别 |
| DELETE | `/api/settings/categories/{id}` | 删除类别 |
| GET | `/api/settings` | 列出设定条目 |
| POST | `/api/settings` | 新增设定 |
| PATCH | `/api/settings/{id}` | 修改设定 |
| DELETE | `/api/settings/{id}` | 删除设定 |
| POST | `/api/settings/extract` | AI 提取设定 |

### 2.16 写作技巧（Skill）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/skills/generate` | AI 生成技巧 |
| GET | `/api/skills` | 列出技巧 |
| POST | `/api/skills` | 手动新增技巧 |
| GET | `/api/skills/drafts` | 列出草稿 |
| POST | `/api/skills/drafts/{id}/promote` | 提升草稿为正式 |
| DELETE | `/api/skills/drafts/{id}` | 删除草稿 |
| PATCH | `/api/skills/{id}` | 修改技巧 |
| DELETE | `/api/skills/{id}` | 删除技巧 |

### 2.17 AI 倾向档案

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/bias` | 列出倾向档案 |
| POST | `/api/bias` | 新增/修改 |
| DELETE | `/api/bias/{id}` | 删除 |

### 2.18 章节管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chapters` | 列出章节 |
| POST | `/api/chapters` | 新建章节 |
| GET | `/api/chapters/{id}` | 获取章节 |
| DELETE | `/api/chapters/{id}` | 删除章节 |
| POST | `/api/chapters/{id}/patch` | 修改章节 |
| GET | `/api/chapters/{id}/export` | 导出（txt/md/docx） |

### 2.19 知识图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/graph/types` | 列出实体类型 |
| POST | `/api/graph/types` | 新增实体类型 |
| PATCH | `/api/graph/types/{id}` | 修改实体类型 |
| DELETE | `/api/graph/types/{id}` | 删除实体类型 |
| GET | `/api/graph/entities` | 列出实体 |
| GET | `/api/graph/relations` | 列出关系 |
| GET | `/api/graph/events` | 列出时间线事件 |
| GET | `/api/graph/context` | 当前时空点已知事实 |
| POST | `/api/impact` | 影响分析（连锁修改） |
| POST | `/api/graph/extract` | AI 抽取图谱 |

### 2.20 剧情计划

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plan` | 列出计划 |
| POST | `/api/plan` | 新增计划 |
| PATCH | `/api/plan/{id}` | 修改计划 |
| DELETE | `/api/plan/{id}` | 删除计划 |

### 2.21 叙事树 & 线进度

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/story/nodes` | 列出叙事树节点 |
| POST | `/api/story/nodes` | 新增节点 |
| POST | `/api/story/nodes/{id}/choose` | 选择分支 |
| POST | `/api/story/nodes/{id}/anchor` | 设为锚点 |
| GET | `/api/story/tree` | 获取完整树 |
| POST | `/api/story/threads` | 新增线进度 |
| GET | `/api/story/threads` | 列出线进度 |
| PATCH | `/api/story/threads/{id}` | 修改线进度 |

### 2.22 工作流

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workflows` | 列出工作流定义 |
| POST | `/api/workflows` | 新增定义 |
| POST | `/api/workflows/generate` | AI 生成定义 |
| GET | `/api/workflows/drafts` | 列出草稿 |
| POST | `/api/workflows/drafts/{id}/promote` | 提升草稿 |
| DELETE | `/api/workflows/drafts/{id}` | 删除草稿 |
| GET | `/api/workflows/tasks` | 列出任务 |
| GET | `/api/workflows/tasks/{id}` | 获取任务 |
| POST | `/api/workflows/tasks/{id}/approve` | 人工确认 |
| GET | `/api/workflows/{id}` | 获取定义 |
| DELETE | `/api/workflows/{id}` | 删除定义 |
| POST | `/api/workflows/{id}/run` | 执行任务 |

---

## 三、存储接口 — 数据持久化层

| 存储类 | 位置 | 管理对象 | 后端 |
|--------|------|----------|------|
| `ConversationStore` (ABC) | core/storage | 会话 + 消息 | 可换（内存/SQLite） |
| `SqliteConversationStore` | store/sqlite | 同上 SQLite 实现 | SQLite |
| `ChapterStore` | store/sqlite | 章节 + 版本历史 | SQLite |
| `GraphStore` | graph/schema | 实体/关系/事件 + FTS | SQLite |
| `AgencyStore` | align/agency | 能动性档位 | SQLite |
| `ManualStore` | align/manual | 说明书条目 | SQLite |
| `BiasStore` | align/bias | AI 倾向档案 | SQLite |
| `SignalStore` | align/signals | 信号记录 | SQLite |
| `WritingSkillStore` | align/skills | 写作技巧 | SQLite |
| `WorldSettingStore` | align/worldsettings | 世界设定 | SQLite |
| `StoryTreeStore` | align/storytree | 叙事树 | SQLite |
| `StoryThreadStore` | align/storytree | 线进度 | SQLite |
| `StoryPlanStore` | align/plan | 剧情计划 | SQLite |
| `DimensionStore` | explore/direction | 探索维度 | SQLite |
| `ProjectArchive` | explore/direction | 方向 + 约束 | SQLite |
| `ExternalLibrary` | template/patterns | 外部模板 | SQLite |
| `MaterialStore` | template/materials | 资料 + 摘要卡 | SQLite |
| `PlotStore` | template/plot | 关键点 | SQLite |
| `ModelRegistry` | models/registry | 模型配置 | SQLite |
| `WorkflowStore` | workflow/store | 工作流任务/状态 | SQLite |
| `ExtensionToolStore` | server/tools_extensions | 扩展工具 | SQLite |

---

## 四、接口关系总览

```
                    ┌─────────────────────────────────────────┐
                    │           HTTP API (FastAPI)             │
                    │         80+ REST 端点                    │
                    └──────────────┬──────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │     Agent       │  │  领域服务层      │  │   工作流引擎     │
    │  (core.loop)    │  │ (explore/align/ │  │ (workflow)      │
    │                 │  │  check/graph/   │  │                 │
    │  Model ◄─────── │  │  template)      │  │  NodeRunner     │
    │  ToolRegistry   │  │                 │  │  WorkflowStore  │
    │  ConvStore      │  │  GraphStore     │  │                 │
    │  EventEmitter   │  │  ManualStore    │  │                 │
    └─────────────────┘  │  AgencyStore    │  └─────────────────┘
              │          │  SkillStore ... │           │
              │          └────────┬────────┘           │
              ▼                   ▼                    ▼
    ┌─────────────────────────────────────────────────────────┐
    │              SQLite (data/anyspark.db)                   │
    │         全部存储接口的持久化实现                           │
    └─────────────────────────────────────────────────────────┘
              │
              ▼
    ┌─────────────────────────────────────────────────────────┐
    │         DeepSeek API (OpenAI 兼容端点)                   │
    │         Model / StreamModel 协议的真实实现                │
    └─────────────────────────────────────────────────────────┘
```
