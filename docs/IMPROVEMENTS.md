# 改进跟踪文档

> 系统性改进跟踪。完成 18/18 项基础改进 + v2.0.0 大规模扩展 + v2.6.0 质量增强。

## Phase 7: v2.6.0 AI味扫描 + 批量导入优化 + 多项修复

- [x] ~~**7.1 AI味扫描引擎** — `core/ai_flavor_scanner.py` — 7项纯规则检测，零token消耗~~
- [x] ~~**7.2 AI味嗅觉审查员** — `reviewers/ai_flavor_sniffer.yaml` — 评审团新增LLM审查员~~
- [x] ~~**7.3 AI味反馈闭环** — `knowledge_scope.py` + `context_manager.py` + `headless_loop.py`~~
- [x] ~~**7.4 质量门AI味集成** — `quality_gate.py` 评审前自动扫描~~
- [x] ~~**7.5 知识检索零匹配修复** — `_prepare_writing` 子串匹配fallback~~
- [x] ~~**7.6 Neo4j宕机防御** — `batch_add_entities/relations/foreshadows` 空驱动检查~~
- [x] ~~**7.7 启动脚本修复** — `start.bat/start.ps1` 自动创建Neo4j容器~~
- [x] ~~**7.8 评审团前端修复** — 新增"续写专项"分类区，14位评审员全部可见~~
- [x] ~~**7.9 章节拆分正则增强** — 从2种扩展到10种格式，LLM fallback三段采样~~
- [x] ~~**7.10 批量导入优化** — `batch_add_chapters` O(n²)→O(n)~~

---

## Phase 6: v2.0.0 全栈成熟化

- [x] ~~**6.1 叙事逻辑引擎** — `core/narrative_logic/` 子包（约束检查 + 置信度评分 + 影响传播）~~
- [x] ~~**6.2 交互式故事系统** — `core/interactive_agent.py` + `interactive_store.py`~~
- [x] ~~**6.3 本体生成器** — `core/ontology_generator.py`~~
- [x] ~~**6.4 图搜索增强** — `core/graph_search.py`~~
- [x] ~~**6.5 版本更新检测** — `core/update_checker.py`~~
- [x] ~~**6.6 事件存储** — `core/event_store.py`~~
- [x] ~~**6.7 会话与设置管理** — `core/session_state.py` + `settings.py`~~
- [x] ~~**6.8 线程池统一** — `core/thread_pools.py`~~
- [x] ~~**6.9 工作流 Agent** — `core/workflow_agent.py`~~
- [x] ~~**6.10 写作核心模块化** — `core/writer.py`~~
- [x] ~~**6.11 Agent 配置与上下文** — `core/agent_config.py` + `agent_context.py` + `app_context.py`~~
- [x] ~~**6.12 数据层模块化** — `data/stores/` 子包~~
- [x] ~~**6.13 前端 100% TypeScript** — 49 文件全量迁移~~
- [x] ~~**6.14 CI/CD 基础设施** — `.github/workflows/ci.yml` + `docker-publish.yml`~~
- [x] ~~**6.15 预提交钩子** — `.pre-commit-config.yaml`~~
- [x] ~~**6.16 前端组件扩展** — 68 组件 (40+ → 68)~~
- [x] ~~**6.17 测试套件扩展** — 34 文件 451 用例 (20+ → 34)~~
- [x] ~~**6.18 文档全面更新** — README/ARCHITECTURE/MODULES/ROADMAP/IMPROVEMENTS/CHANGELOG~~

---

## Phase 1: 基础架构重构

- [x] ~~**1.1 配置系统** — 提取魔法数字为配置常量，支持项目级/全局级配置合并~~
  - `src/core/config.py` — AppConfig dataclass + 环境变量 + config.json 覆盖
- [x] ~~**1.2 拆分 server.py** — 路由模块 + 工具执行器 + 数据访问层~~
  - `src/server.py` 从 1112 行 → 63 行
  - `src/routes/` — 9 个路由模块
  - `src/tools/executor.py` — 工具执行逻辑
  - `src/data/json_store.py` — 数据访问层
- [x] ~~**1.3 结构化错误处理** — 自定义异常类 + 统一错误响应格式 + 优雅降级~~
  - `src/core/errors.py` — AppError 体系 + 全局异常处理器

## Phase 2: 核心能力补齐

- [x] ~~**2.1 权限/确认机制** — 危险操作执行前需确认（delete_all_chapters 等）~~
  - `src/core/permissions.py` — PermissionManager + 规则系统 + session 级审批
- [x] ~~**2.2 事件总线** — 统一前后端通信，替代散落的 SSE 事件~~
  - `src/core/event_bus.py` — EventBus + 类型化事件 + 历史记录
- [x] ~~**2.3 上下文压缩** — 长对话自动压缩历史消息，保留关键上下文~~
  - `src/core/compaction.py` — token 估算 + LLM 摘要 + 尾部保留策略
- [x] ~~**2.4 会话恢复** — 浏览器刷新后恢复聊天上下文~~
  - `frontend/src/storage.ts` — localStorage 持久化 session/tab/mode

## Phase 3: 功能扩展

- [x] ~~**3.1 插件系统** — 允许用户编写自定义提取器/写作风格插件~~
  - `src/core/plugin_loader.py` — 自动发现 + 钩子系统 + 自定义工具
  - `plugins/example_style.py` — 示例插件
- [x] ~~**3.2 工作流引擎实补** — stub handler 替换为真正的 LLM 调用~~
  - `src/server.py` — 真实实现 extract/write handler
  - `src/routes/workflow.py` — 新增 SSE 流式执行端点
- [x] ~~**3.3 导出功能** — 支持 txt/docx 导出整本书或单章~~
  - `src/core/exporter.py` — txt/docx 导出器
  - `src/routes/export.py` — 下载端点
- [x] ~~**3.4 CLI 统一** — main.py 复用 server.py 的 Agent Loop~~
  - `src/main.py` — 新增 `/chat` 命令 + 默认自由对话模式

## Phase 4: 代码质量

- [x] ~~**4.1 SSE 解析改进** — 前端使用标准化 SSE 解析工具~~
  - `frontend/src/sse.ts` — async generator + 完整协议解析
- [x] ~~**4.2 前端状态管理** — 引入轻量 store 替代 useState + refreshKey~~
  - `frontend/src/store.ts` — useSyncExternalStore 零依赖方案
- [x] ~~**4.3 D3+React 改进** — ResizeObserver 替代 window.resize~~
  - `frontend/src/hooks/useResizeObserver.js` — 可复用 hook
- [x] ~~**4.4 线程安全修复** — threading.RLock 保护 JSON 文件读写~~
  - `src/data/json_store.py` — RLock 包裹所有文件 IO

## Phase 5: 工程化

- [x] ~~**5.1 测试框架** — pytest 覆盖核心模块~~
  - `tests/` — config, json_store, exporter, permissions, event_bus
  - `pytest.ini` — 配置文件
- [x] ~~**5.2 Docker Compose** — Neo4j + Backend + Frontend 一键部署~~
  - `docker-compose.yml` + `Dockerfile.backend` + `frontend/Dockerfile` + `frontend/nginx.conf`
- [x] ~~**5.3 TypeScript 渐进迁移** — tsconfig.json + JSDoc 类型注解~~
  - `frontend/tsconfig.json` — checkJs 启用
  - `frontend/src/types.ts` — 全局类型定义

---

## 变更日志

### 2026-06-24: 草稿/定稿双轨 + 叙事导演 + RunLedger + 文档修正
- 草稿/定稿双轨流程（chapters.py promote/demote API，ChaptersPanel.tsx 状态栏badge，MarkdownEditor.jsx 标识）
- 叙事导演API（styles_route.py NarrativeStrategyUpdate，6维度叙事策略）
- RunLedger增强（agent_loop.py tool_names追踪，前端工具调用分布可视化）
- TECH_STACK.md 重写为实际技术栈（移除 PostgreSQL/Redis/Celery/LangGraph/Socket.IO 等未采用技术）
- ROADMAP.md 标记已完成项、MODULES.md 修正依赖


| 日期 | 改进项 | 状态 |
|------|--------|------|
| 2026-06-11 | Phase 1: 配置系统 | 完成 |
| 2026-06-11 | Phase 1: 拆分 server.py | 完成 |
| 2026-06-11 | Phase 1: 结构化错误处理 | 完成 |
| 2026-06-11 | Phase 2: 权限/确认机制 | 完成 |
| 2026-06-11 | Phase 2: 事件总线 | 完成 |
| 2026-06-11 | Phase 2: 上下文压缩 | 完成 |
| 2026-06-11 | Phase 2: 会话恢复 | 完成 |
| 2026-06-11 | Phase 3: 插件系统 | 完成 |
| 2026-06-11 | Phase 3: 工作流引擎实补 | 完成 |
| 2026-06-11 | Phase 3: 导出功能 | 完成 |
| 2026-06-11 | Phase 3: CLI 统一 | 完成 |
| 2026-06-11 | Phase 4: SSE 解析改进 | 完成 |
| 2026-06-11 | Phase 4: 前端状态管理 | 完成 |
| 2026-06-11 | Phase 4: D3+React 改进 | 完成 |
| 2026-06-11 | Phase 4: 线程安全修复 | 完成 |
| 2026-06-11 | Phase 5: 测试框架 | 完成 |
| 2026-06-11 | Phase 5: Docker Compose | 完成 |
| 2026-06-11 | Phase 5: TypeScript 迁移 | 完成 |

---

## 新增文件清单

```
src/core/config.py          # 集中配置管理
src/core/errors.py          # 结构化错误类
src/core/permissions.py     # 权限/确认系统
src/core/event_bus.py       # 事件总线
src/core/compaction.py      # 上下文压缩
src/core/plugin_loader.py   # 插件加载器
src/core/exporter.py        # 导出功能
src/data/__init__.py        # 数据层包
src/data/json_store.py      # JSON 持久化（含线程锁）
src/tools/__init__.py       # 工具包
src/tools/executor.py       # 工具执行器
src/routes/__init__.py      # 路由注册
src/routes/books.py         # 书籍 CRUD
src/routes/knowledge.py     # 知识库 API
src/routes/chapters.py      # 章节管理
src/routes/sessions.py      # 会话管理
src/routes/documents.py     # 文档上传
src/routes/characters.py    # 角色画廊
src/routes/workflow.py      # 工作流
src/routes/chat.py          # Agent 对话
src/routes/mode.py          # LLM 模式切换
src/routes/export.py        # 导出端点
plugins/example_style.py    # 示例插件
frontend/src/sse.ts         # SSE 解析工具
frontend/src/store.ts       # 状态管理
frontend/src/storage.ts     # localStorage 持久化
frontend/src/types.ts       # JSDoc 类型定义
frontend/src/hooks/useResizeObserver.js  # ResizeObserver hook
frontend/tsconfig.json      # TypeScript 检查配置
frontend/Dockerfile         # 前端容器
frontend/nginx.conf         # Nginx 代理配置
docker-compose.yml          # 一键部署
Dockerfile.backend          # 后端容器
pytest.ini                  # 测试配置
tests/conftest.py           # 测试 fixtures
tests/test_config.py        # 配置测试
tests/test_json_store.py    # 数据层测试
tests/test_exporter.py      # 导出测试
tests/test_permissions.py   # 权限测试
tests/test_event_bus.py     # 事件总线测试
src/routes/skills_route.py  # 技能/插件查询端点
pyproject.toml              # Python 包配置
```

---

## 二次审查修复 (2026-06-11)

对比架构二次审查发现 6 个 Bug + 5 个集成断裂，全部修复：

### Bug 修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | `_write_shortcut` 同步阻塞事件循环 | 改为 Queue + run_in_executor 异步流 |
| 2 | 死代码 `check_permission` 返回值无意义 | 已删除，逻辑合并到 `execute_tool` |
| 3 | CLI 绕过权限系统 (`confirmed=True`) | CLI 现在正确调用 `needs_confirmation` + 终端确认 |
| 4 | compaction 与 AI 共享线程池导致死锁 | 独立 `_compaction_executor`(2线程) + `compact_messages_async` |
| 5 | `sys.path` 硬编码 | 添加 `pyproject.toml`，支持 `pip install -e .` |
| 6 | CLI 无 compaction 支持 | 已添加 `needs_compaction` + `compact_messages` 调用 |

### 集成断裂修复

| # | 问题 | 修复位置 |
|---|------|----------|
| 1 | 事件总线零消费者 | `tools/executor.py` 发射 TOOL_EXECUTED/FAILED/PERMISSION_*，`data/json_store.py` 发射 CHAPTER_CREATED/DELETED，`core/extractor.py` 发射 KNOWLEDGE_EXTRACTED |
| 2 | 插件系统零调用 | `core/writer.py` 调用 on_write_before/after + modify_system_prompt，`core/extractor.py` 调用 on_extract_before/after + on_knowledge_update，`routes/chat.py` 调用 modify_system_prompt |
| 3 | Skills 系统未接入 | `routes/chat.py` 注入可用技能到 system prompt，新增 `/api/skills` 端点 |
| 4 | Agent classify 未使用 | `routes/chat.py` 对长文本(>2000字)自动分类并注入提示 |
| 5 | Compaction CLI 未接入 | `main.py` agent loop 每轮检查 + 调用 |
