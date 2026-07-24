# 前端开发指南

> 本文档面向前端开发者和贡献者，说明火花前端的技术架构、组件组织、状态管理和开发规范。

---

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 框架 | React | 19.2 |
| 构建工具 | Vite | 8 |
| 类型系统 | TypeScript | 6 |
| 样式 | TailwindCSS | 4.3 |
| 状态管理 | 自研 useSyncExternalStore | — |
| 路由 | React Router | 7 |
| 富文本编辑器 | TipTap (ProseMirror) | 3 |
| 可视化 | D3.js 7 / Leaflet 1.9 | — |
| 动画 | Framer Motion | 12 |
| 面板布局 | react-resizable-panels | 4 |
| UI 组件库 | Radix UI + Lucide Icons | — |

---

## 目录结构

```
frontend/src/
├── api.ts                  # REST API 封装层（get/post/put/del）
├── sse.ts                  # SSE 流式解析器
├── store.ts                # 全局状态管理
├── storage.ts              # localStorage 工具
├── App.tsx                 # 应用根组件 + 路由定义
├── main.tsx                # 入口文件
├── index.css               # 全局样式 + TailwindCSS 指令
├── types/
│   └── index.ts            # 共享 TypeScript 类型定义
├── hooks/
│   ├── useSSE.ts           # SSE 连接管理 Hook
│   ├── useAutoSave.ts      # 自动保存 Hook
│   ├── useTheme.tsx         # 主题切换 Hook
│   ├── useResizeObserver.ts # 尺寸观察 Hook
│   └── useSplitLayout.ts   # 分栏布局 Hook
├── components/
│   ├── chat/               # 聊天界面子组件
│   ├── editor/             # 章节编辑器组件
│   ├── panels/             # 面板容器组件
│   ├── ui/                 # 通用 UI 原子组件
│   └── *.tsx               # 页面级/功能级组件
├── stores/
│   └── tabStore.ts         # Tab 状态管理
└── features/
    └── simulation/         # 剧情推演功能模块
```

---

## 组件目录详解

### `components/` 根级组件（55 个）

页面级和功能级组件直接放在 `components/` 下：

| 组件 | 职责 | 依赖 |
|------|------|------|
| `ChatPanel.tsx` | 对话主界面，管理 SSE 收发 | useSSE, MessageList, MessageInput |
| `ChaptersPanel.tsx` | 章节列表 + 编辑器入口 | MarkdownEditor, ChapterHistoryPanel |
| `BookDetail.tsx` | 书籍详情页主容器 | 所有 Panel 组件 |
| `Bookshelf.tsx` | 书架页面 | CreateBookModal |
| `KnowledgePanel.tsx` | 知识库面板（实体/关系管理） | api.ts |
| `TimelineView.tsx` | 时间线可视化（D3.js） | D3.js |
| `FullGraphView.tsx` | 全量图谱视图（力导向图） | D3.js |
| `RelationGraph.tsx` | 角色关系图 | D3.js |
| `WorldMap.tsx` | 4D 世界地图（Leaflet + 时间滑块） | Leaflet |
| `ForeshadowBoard.tsx` | 伏笔追踪看板 | api.ts |
| `ReviewPanel.tsx` | 评审团面板 | api.ts |
| `SettingsModal.tsx` | 设置弹窗 | api.ts |
| `MarkdownEditor.tsx` | TipTap 富文本编辑器 | @tiptap/* |
| `MemoryPanel.tsx` | 项目记忆管理 | api.ts |
| `CommandPalette.tsx` | 命令面板 | React Router |
| `ShortcutsModal.tsx` | 快捷键说明 | — |
| `StatsDashboard.tsx` | 统计仪表盘 | D3.js |
| `CharacterGallery.tsx` | 角色画廊 | api.ts |

### `components/chat/` — 聊天子组件（13 个）

| 组件 | 职责 |
|------|------|
| `MessageList.tsx` | 消息列表渲染，支持 TextPart / ToolCallPart / ReasoningPart / ChapterDiffPart |
| `MessageInput.tsx` | 输入框，支持斜杠命令自动补全 |
| `SlashMenu.tsx` | 斜杠命令菜单弹出 |
| `AutopilotConsole.tsx` | Autopilot 控制台日志 |
| `PlotCardSelector.tsx` | 剧情卡片选择器（阻塞式用户交互） |
| `QuestionCard.tsx` | 确认/选择卡片 |
| `ProgressIndicator.tsx` | SSE 进度指示器 |
| `WorkflowProgress.tsx` | 工作流步骤进度条 |
| `PatchNotification.tsx` | 章节 Diff 通知组件 |
| `WritingPreview.tsx` | 写作内容实时预览 |
| `ContextBar.tsx` | 上下文状态栏 |
| `RunLedger.tsx` | Agent 运行记录 |
| `TaskListPanel.tsx` | 任务列表面板 |

### `components/editor/` — 编辑器组件（2 个）

| 组件 | 职责 |
|------|------|
| `MarkdownEditor.tsx` | TipTap 富文本编辑器，支持专注模式/打字机模式/字数目标 |
| `WordCountGoal.tsx` | 字数目标进度条组件 |

### `components/ui/` — 通用 UI 原子组件（11 个）

| 组件 | 职责 |
|------|------|
| `Icon.tsx` | SVG 图标组件（基于 Lucide Icons） |
| `Modal.tsx` | 通用弹窗 |
| `ConfirmModal.tsx` | 确认弹窗 |
| `Toast.tsx` | Toast 通知 |
| `toast-utils.ts` | Toast 工具函数 |
| `EmptyState.tsx` | 空状态占位 |
| `ErrorBoundary.tsx` | React 错误边界 |
| `Skeleton.tsx` | 骨架屏加载 |
| `StatCard.tsx` | 统计指标卡片 |
| `Toggle.tsx` | 开关组件 |
| `colors.ts` | 颜色常量定义 |

### `components/panels/` — 面板容器（1 个）

| 组件 | 职责 |
|------|------|
| `PanelHost.tsx` | 插槽式面板容器，统一管理侧面面板的注册/激活/关闭 |

---

## 状态管理

项目使用自研的 `createStore`（基于 React 19 的 `useSyncExternalStore`），无第三方状态库。

### 全局 Store

定义在 `store.ts` 中：

```typescript
interface AppState {
  books: unknown[]                // 书籍列表
  currentBookId: string | null   // 当前选中书籍
  refreshKey: number              // 刷新触发器（递增触发组件重载）
  notifications: Notification[]  // 通知队列（5s 自动消失）
  selectedTimeOrder: number       // 4D 地图时间轴选中点
  maxTimeOrder: number            // 4D 地图最大时间序
  timelineEvents: {...}[]         // 时间轴事件列表
  backendStatus: BackendStatusState  // 后端连接状态
}
```

### 使用模式

```typescript
import { appStore, useBooks, useRefreshKey, triggerRefresh } from '../store'

// 在组件中读取状态
function MyComponent() {
  const books = useBooks()
  const refreshKey = useRefreshKey()
  // ...
}

// 在任意位置更新状态
triggerRefresh()
appStore.setState({ currentBookId: 'book-123' })
```

### 模式原则

1. **全局数据 + 页面状态分离**：全局数据（书籍列表、后端状态）走 `store.ts`，页面级状态走 React 的 `useState` / `useReducer`
2. **最小订阅原则**：通过 `appStore.useStore(selector)` 精准订阅所需字段，避免不必要的重渲染
3. **`selector` 必须返回稳定引用**：避免在 selector 中构造新对象导致无限重渲染

### Tab 状态

`stores/tabStore.ts` 管理书籍详情页内的 Tab 切换状态（知识库 / 章节 / 图谱 / 设置等），使用独立的 createStore 实例。

---

## SSE 流式交互

SSE 是前端与 Agent 引擎通信的核心机制，通过 `useSSE` Hook 管理连接生命周期。

### 事件类型

| SSE 事件类型 | 触发场景 | 前端处理 |
|-------------|----------|---------|
| `chunk` | Agent 流式输出文本 | `MessageList` 实时追加显示 |
| `progress` | 工具执行进度 | `ProgressIndicator` 显示步骤状态 |
| `done` | Agent 完成 | 组装最终消息（含 `parts` 中的结构化数据） |
| `plot_cards` | 剧情卡片生成 | `PlotCardSelector` 显示卡片选择弹窗 |
| `question` | 需要用户确认 | `QuestionCard` 显示确认/选择弹窗 |
| `writing` | 写作工具输出 | `WritingPreview` 实时显示写作内容 |
| `writing_end` | 写作完成 | 触发知识库刷新 |
| `task_list` | Autopilot 任务列表更新 | `TaskListPanel` 更新任务视图 |
| `workflow` | 工作流步骤执行 | `WorkflowProgress` 更新步骤进度 |
| `patch_result` | 章节 Diff 生成 | `PatchNotification` 显示 Diff 变更 |
| `chapter_updated` | 章节变更 | 触发知识库刷新 |
| `agent_metrics` | Agent 指标更新 | 调试日志 |
| `text-correction` | 文本修正 | 特殊修正处理 |

### 使用示例

```typescript
import { useSSE } from '../hooks/useSSE'

function ChatContainer({ bookId, sessionId }) {
  const { sendMessage, cancel, streaming } = useSSE({
    bookId,
    sessionId,
    agentMode: 'normal',
    autoModeEnabled: false,
    onMessage: (msg) => { /* 处理消息 */ },
    onProgress: (data) => { /* 处理进度 */ },
    onPlotCards: (data) => { /* 处理剧情卡片 */ },
    onQuestion: (data) => { /* 处理用户确认 */ },
    onError: (err, msg) => { /* 处理错误 */ },
  })

  return (
    <div>
      <MessageList messages={...} />
      <MessageInput onSend={sendMessage} disabled={streaming} />
      {streaming && <button onClick={cancel}>取消</button>}
    </div>
  )
}
```

### 消息 Part 系统

每条 Agent 消息由多个 Part 组成，支持结构化渲染：

| Part 类型 | 渲染方式 |
|-----------|---------|
| `TextPart` | 普通文本 |
| `ToolCallPart` | ToolCallCard（可折叠工具调用详情） |
| `ToolResultPart` | ToolResultCard（工具返回结果） |
| `ReasoningPart` | ReasoningBlock（LLM 思考过程） |
| `ChapterDiffPart` | ChapterDiffBadge（章节变更 Diff） |

Part 通过 `done` 事件的 `parts` 字段传递，前端据类型选择渲染组件。

---

## REST API 封装

`api.ts` 提供统一的 REST API 调用封装：

```typescript
// 基础方法
get<T>(url)        // GET 请求
post<T>(url, data) // POST 请求
put<T>(url, data)  // PUT 请求
del<T>(url)        // DELETE 请求（自动添加 X-Confirm-Delete 头）

// 示例：获取章节列表
const chapters = await get<Chapter[]>('/books/book-123/chapters')

// 示例：发送消息（非 SSE 场景）
const result = await post<{ messageId: string }>('/api/chat', { text: '你好' })
```

所有请求内置连接诊断日志（`[CONN-DIAG]` 前缀），用于排查前后端连通性问题。

---

## 路由设计

应用使用 React Router v7，定义在 `App.tsx`：

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | `Bookshelf` | 书架首页 |
| `/books/:bookId` | `BookDetail` | 书籍详情（含 Tab 切换） |
| `/books/:bookId/chapter/:chapterId` | 编辑器 | 章节编辑页 |

`BookDetail` 内的 Tab 切换不依赖路由，由 `tabStore` 管理本地 Tab 状态。

---

## 样式规范

- **TailwindCSS 4**：所有样式使用 Tailwind 工具类，禁止内联样式
- **颜色变量**：定义在 `colors.ts` 中，Dark 模式下自动切换
- **图标**：统一使用 Lucide Icons，禁止 emoji 图标（已完成 emoji → SVG 统一治理）
- **面板布局**：使用 `react-resizable-panels` 实现可拖拽分栏
- **暗色模式**：通过 `useTheme` Hook + Tailwind `dark:` 变体实现

---

## 开发命令

```bash
cd frontend

# 启动开发服务器（自动代理 API 到后端 8191 端口）
npx vite --port 8190

# 构建生产版本
npm run build

# TypeScript 类型检查
npx tsc --noEmit

# ESLint 检查
npx eslint . --max-warnings 90

# 同时启动前后端（从项目根目录）
cd .. && python -u src/server.py
```

---

## 编码规范

1. **强类型优先**：所有组件 Props 定义接口，禁止 `any`
2. **函数组件**：全部使用函数组件 + Hooks，无 class 组件
3. **命名规范**：
   - 组件文件：`PascalCase.tsx`
   - Hook 文件：`useCamelCase.ts`
   - 工具文件：`kebab-case.ts`
4. **导出规范**：每个文件默认导出主要组件，具名导出辅助类型
5. **注释**：复杂逻辑写中文注释，API 层方法写英文注释
