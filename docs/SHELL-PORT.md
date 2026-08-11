# 壳移植计划（feat/shell-port）——旧壳配新芯

**目标**：把「自研高级时间线辅助写作agent」的产品级前端壳（视觉+交互+多项目书架）移植到
AnySparkV4 后端（新芯），激活 V4 的多项目能力（book_id 贯穿后端 245 处，前端此前写死 main）。

**原则**：壳的皮肤/交互/布局全保留；数据层重写为 V4 后端适配；对端专属功能砍掉或换 V4 对应能力。

---

## 移植资产分类

### 🟢 A类：直接搬（壳的皮肤与交互框架）
| 资产 | 文件 | 处置 |
|---|---|---|
| UI 基元 | `components/ui/*`（Icon/Toast/ConfirmModal/Modal/Skeleton/StatCard/Toggle/EmptyState/ErrorBoundary/colors/toast-utils）| 原样复制 |
| 主题系统 | `index.css` + `hooks/useTheme.tsx` + `ThemeToggle` | 复制（需适配 tailwind v3） |
| 交互层 | `CommandPalette` / `ShortcutsModal` / `BackendStatus` | 复制 |
| hooks | `useSplitLayout` / `useSSE` / `useAutoSave` / `useResizeObserver` | 复制 |
| 状态 | `storage.ts` / `store.ts` / `stores/tabStore.ts` | 复制 |
| 路由 | `App.tsx` / `main.tsx`（BrowserRouter + AnimatePresence）| 复制 |
| 布局 | `Bookshelf`（多项目书架）/ `BookDetail`（tab 分组+分屏）/ `PanelHost` | 复制骨架，tab 列表按 V4 能力裁剪 |

### 🟡 B类：API 适配层（核心工作量——壳组件调用 → V4 端点）
壳的 API 是 `/api/books/{bookId}/...` 多项目结构；V4 是 `book_id` 参数化单库多书。
写统一适配层 `src/api/v4/`：

| 壳域 | V4 端点 |
|---|---|
| books（书架 CRUD）| 无直接端点 → 用 `GET /api/workspace` 列项目 + SQLite 项目表？**需后端补书架端点**（见缺口） |
| chapters | `/api/chapters`（已有增删改/导出/定点编辑 PATCH）|
| chat/SSE | `/api/chat/stream` + `/api/chat`（SSE 协议接近）|
| knowledge/图谱 | `/api/graph/*`（entities/relations/events/types）|
| 设定档 | `/api/settings` + categories |
| 心智/偏好 | `/api/manual` + notices |
| 伏笔/关键点 | `/api/plot` + item |
| 大纲/计划 | `/api/plan` |
| 材料/资料 | `/api/materials` |
| 评审团 | `/api/review/panel` + reviewers |
| 文风/技巧 | `/api/skills` + drafts |
| 探索 | `/api/explore/*` |
| 工作流 | `/api/workflows/*` |
| 互动推演 | `/api/play/*`（替代壳的 simulation）|
| 角色推演 | `/api/role/*` |
| 上传/消化 | `/api/upload` + `/api/ingest` |
| 扩展工具 | `/api/tools/*` |
| 模板 | `/api/templates/*` |
| 批量 | `/api/batch/*` |
| 影响分析 | `/api/impact` |
| AI 倾向 | `/api/bias` |
| 项目简介 | `/api/brief` |
| 对话会话 | `/api/conversations` |

**后端缺口**（V4 需补）：书架端点——`GET /api/books`（列项目+统计）、`POST /api/books`（创建项目）、
`DELETE /api/books/{book_id}`。V4 后端有 `workspace.describe(book_id)` 可支撑。

### 🔴 C类：对端专属功能（V4 无对应，砍掉或替换）
| 壳功能 | 处置 |
|---|---|
| simulation 推演树 | 砍 → 换 V4 `/api/play` 互动推演 |
| timeline/map/metrics/insights/heatmap/pacing/依赖图 | 砍（V4 无时间线/地图数据模型）|
| Autopilot / tasks / run-ledger / cost 面板 | 砍 |
| 对端 307 端点专属面板 | 砍 |
| .spark 项目导入 | 砍（V4 决策A：不做旧数据导入）|

---

## 分阶段执行

- **P1 壳骨架落地**：依赖升级（tailwind v4? / react-router / framer-motion / react-resizable-panels / d3 等）+ A 类复制 + B 类 API 适配层 + 砍 C 类 + 后端补书架端点。产物：能跑的多项目书架 + 进入书的壳界面（tab 可用但部分空）。
- **P2 核心面板接通**：chat（SSE）+ chapters（写作闭环）两大核心先通 V4 数据。
- **P3 全面板换皮**：知识库/大纲/伏笔/文风/评审/材料/搜索/工作流 + V4 11 工具面板挂入。
- **P4 收口**：tsc/build/gate + 截图对比 + 更新 FRONTEND-GAPS/PROGRESS。

## 关键决策记录
- 保留壳的多项目书架（激活 V4 book_id 多书能力）。
- V4 前端现有实现（单页 Layout/DisplayArea 模式）**弃用**，由壳架构取代。
- 壳的 SSE/ChatPanel 保留其流式交互体验，接 V4 `/api/chat/stream`。
- 明暗主题：壳用 tailwind v4 `@theme` 语法 → 决策：**升级 V4 前端到 tailwind v4**（否则主题系统要重写，升级更省且与壳一致）。
