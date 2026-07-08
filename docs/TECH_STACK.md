# 技术选型（v3.0 实际技术栈 — 2026-06-24 修正）

> ⚠️ 本文档之前描述的是一个从未被采用的规划技术栈（PostgreSQL、Redis、Celery、LangGraph、Socket.IO），
> 现已修正为项目实际使用的技术栈。

---

## 前端

| 层级 | 技术栈 | 版本 |
|------|--------|------|
| 框架 | React | v19.2 |
| 构建工具 | Vite | v8 |
| 类型系统 | TypeScript | v6 |
| 样式 | TailwindCSS | v4.3 |
| 状态管理 | 自研 useSyncExternalStore (store.ts) | — |
| 路由 | React Router | v7 |
| 编辑器 | TipTap (ProseMirror) | v3 |
| 可视化 | D3.js v7 / Leaflet v1.9 | — |
| 动画 | Framer Motion | v12 |
| 拖拽面板 | react-resizable-panels | v4 |
| UI组件 | Radix UI + Lucide Icons | — |

## 后端

| 层级 | 技术栈 | 版本 |
|------|--------|------|
| 语言/框架 | Python FastAPI | 3.11+ |
| ASGI 服务器 | Uvicorn | — |
| 实时通信 | SSE (Server-Sent Events, sse-starlette) | — |
| 并发执行 | asyncio + ThreadPoolExecutor | — |
| 包管理 | pip + pyproject.toml (setuptools) | v0.5.0 |

## 数据层

| 存储 | 技术 | 用途 |
|------|------|------|
| 知识图谱 | **Neo4j 5.x Community** | 角色、世界观、事件、关系的结构化存储与查询 |
| 全文检索 | **SQLite FTS5** | 章节内容搜索 |
| 文档存储 | **JSON 文件系统** (`data/`) | 会话、章节、消息、大纲、评审、任务等 |
| 版本控制 | **pygit2** (libgit2 绑定) | 章节 Git 风格版本历史（兼容 go-git / git_store.py） |

## AI / LLM

| 组件 | 实现 |
|------|------|
| 主模型 | DeepSeek (v4-pro / v4-flash，双模型分拆模式) |
| API 兼容 | OpenAI 兼容接口，可切换任何兼容 Provider |
| 模式调度 | `split`（Pro创作+Flash抽取）/ `pro` / `flash` / `custom` |
| Token 计算 | tiktoken 精确计算 |
| 工具协议 | OpenAI function calling (tool_calls) |
| Agent 架构 | 自研 while-true 自主循环 |

## 部署

| 组件 | 方案 |
|------|------|
| 容器化 | Docker Compose（三服务：neo4j + backend + frontend） |
| 前端服务 | Nginx 静态服务 (port 8190) |
| 后端端口 | 8191 |
| Neo4j | 7474 (Browser) / 7687 (Bolt) |

## 配合关系

```
React SPA (Vite, port 8190)
    │ SSE (流式Agent输出)
    │ REST (HTTP/JSON, port 8191)
    ▼
FastAPI Backend (Python 3.11+)
    │── Agent 自主循环 (while-true, 8阶段)
    │── Neo4j Driver → 知识图谱
    │── SQLite FTS5 → 全文搜索
    │── JSON 文件存储 → 章节/会话/大纲
    │── pygit2 → 版本历史
    │── LLM API → DeepSeek (OpenAI 兼容)
    ▼
DeepSeek API (v4-pro / v4-flash)
```

---

## 已废弃的规划项

以下技术栈曾在早期规划中出现，但实际实现中未采用：

| 规划技术 | 实际替代 | 原因 |
|----------|---------|------|
| Socket.IO | SSE | 更简单，Agent流式输出只需单向推送 |
| PostgreSQL + pgvector | JSON文件 + SQLite FTS5 | MVP阶段无需关系型数据库；向量检索未实施 |
| Celery + Redis | asyncio + TaskQueue | 单用户场景无需分布式队列 |
| LangGraph | 自研 Agent Loop | 更灵活，完全掌控循环行为 |
| Zustand | 自研 useSyncExternalStore | 更轻量，无额外依赖 |
| Claude API | DeepSeek | 性价比更高，中文能力出色 |
