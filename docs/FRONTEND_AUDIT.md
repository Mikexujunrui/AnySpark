# 前端架构审计（FRONTEND_AUDIT）

> 生成：2026-07-31 | 对应 `.pi/plan.md` M7.1
> 结论先行：前端不是"完全散乱"，但存在 3 个明确的架构债务点：**api.ts 单体（502 行 73+ 端点）**、**巨型组件（4 个超 800 行）**、**SSE 消费逻辑分散**。

## 现状数据（2026-07-31 实测）

| 指标 | 数值 |
|------|------|
| 文件数 | 102（ts/tsx） |
| 代码量 | 26,314 行 |
| api.ts | 502 行，`export const api = {...}` 单体含 73+ 端点（books 域占绝大多数）+ 3 个 SSE 工厂 + 4 个文档函数 |
| 引用 api 的组件 | 25 个 |
| 状态管理 | `store.ts`（useSyncExternalStore 全局态）+ `storage.ts`（localStorage 封装）+ `stores/tabStore.ts` |
| 巨型组件 | ChaptersPanel 1329 / ChatPanel 1156 / SettingsModal 1045 / CharacterDetail 878 / ReferenceBooksPanel 788 / KnowledgePanel 752 / FullGraphView 722 |
| SSE 抽象 | 已有 3 个工厂（createSSE / createTaskSSE / createAutopilotBridgeSSE），但消费逻辑（事件分发/错误处理）散落在各调用组件 |

## 债务点

### 1. api.ts 单体（最高优先）
- `api` 对象一个文件塞了全部域（books/chapters/knowledge/memory/settings/styles/materials/update/workflows/supervisor/skills/extract）
- 后端有 26 个 route 文件，前端对应 API 却只有一个文件 → **后端已按域分层，前端没有**
- 修改风险：任何组件改动 api 都可能冲突；无法按域独立演进

### 2. 巨型组件（4 个 >800 行）
- ChaptersPanel（1329）与 ChatPanel（1156）承担了"面板 + 数据 + 渲染 + 交互"全部职责
- 与后端 agent_loop 划边界（M3）同构的问题：**UI 组件没有分片**

### 3. SSE 消费分散
- 3 个工厂函数是好的抽象起点，但消费端（MessageList/AutopilotConsole/TaskProgressPanel 等）各自解析事件流
- 缺统一的"事件 → 回调"管道和断线重连策略

### 4. 轻微
- eslint 141 warnings（react-refresh 导出规则等，非阻断）
- 无前端单元测试（后端 59 个测试文件，前端 0）

## 建议分层（M7.2 落地）

```
api/
  http.ts      # get/post/del/put 基础设施（从 api.ts 提取）
  sse.ts       # 3 个 SSE 工厂 + 统一事件管道
  books.ts     # 书的 CRUD（73 端点中的主体）
  knowledge.ts # 知识/实体/搜索
  memory.ts    # 记忆
  settings.ts  # 设置/风格/技能
  index.ts     # re-export 门面（兼容 25 个组件的 `import { api }`）
```

api.ts 保留为 `export { api } from './api/index'`（零破坏迁移）。

## 验收线（M7 完成时）

- `npx tsc --noEmit` 全绿
- `npm run build` 通过
- 25 个组件 import 不破（re-export 门面）
- 手动回归：开书 → 聊天 → 写作 → 搜索 主流程可用
