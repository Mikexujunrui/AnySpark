# 接手指南（30 分钟上手）

> 给下一个接手这个项目的人。读完本页 + 跑通一次测试，你就可以安全地改代码了。
> 本页是"入口"——需要细节时再按链接点进具体文档，**不用**先读完全部 17 个文档。

## 1. 这是什么

**AnySpark（火花）**：AI 小说写作辅助 Agent。用户在网页/桌面端对话，Agent（LLM 自主循环）调用工具写章节、建知识图谱、做推演/评审/时间线。

- 后端：Python + FastAPI（`src/`），前端：React + Vite（`frontend/`）
- 核心设计：**知识库是事实源**、**Agent while-loop 自主循环**、**人类掌控创作主权**

## 2. 立即跑起来（3 条命令）

```bash
# 后端（Windows 用 C:\Python313\python.exe）
pip install -r requirements.txt        # 依赖已 pin 精确版本
python src/main.py                     # 启动 FastAPI (端口见 docs/使用说明书.md)

# 前端
cd frontend && npm ci && npm run dev   # 开发模式；npm run build 构建
```

**检查一切是否健康**（重构后新增的统一门禁）：
```bash
python scripts/check.py --py-only --fast   # ruff + mypy gate（快）
python scripts/check.py                    # 完整：+ pytest + tsc + eslint
```

## 3. 代码地图（先看这 10 个文件）

| 文件 | 作用 | 你要改它的情况 |
|------|------|----------------|
| `src/core/agent_loop.py` (1730行) | Agent 循环骨架：while→LLM→工具→状态 | 改循环行为/取消/重试 |
| `src/core/flows/` | **领域结果分发**（7 种工具结果类型） | **加新的交互类型→在这里加 flow，别动 agent_loop** |
| `src/core/loop_event.py` | SSE 事件（前端通信单元） | 新增前端事件类型 |
| `src/core/question.py` | 问用户机制（`_await_answer` 在此） | 改确认弹窗/超时逻辑 |
| `src/core/sqlite_store/` | 知识图谱（entities/relations/…） | 改图谱查询（**注意 `_run` 返回 dict 列表**） |
| `src/data/stores/` | JSON 文件存储（章节/会话/消息） | 改章节版本/会话持久化 |
| `src/core/search.py` | 全文搜索（search_fts.db） | 改搜索；索引可重建：`python scripts/rebuild_fts.py` |
| `src/tools/impl/` | 工具实现（writing/knowledge/…） | 改工具行为 |
| `src/core/tool_defs/` + `tool_meta.py` | 工具定义 + 行为元数据（单一事实源） | **加新工具→改这里** |
| `src/routes/` | FastAPI 路由（26 个文件） | 改 REST/SSE 端点 |

前端：`frontend/src/api.ts`（端点）+ `api/http.ts`+`api/sse.ts`（基础设施）+ `components/`（面板）。

## 4. 必须知道的约定（新接手的 10 条铁律）

1. **`sqlite_store._run()` 返回 `list[dict]`**（不是 sqlite3.Row）——行有 `.get()`；**不接收 Cypher**（Cypher 会静默返回空！）
2. **加新工具**：`tool_defs/` 定义 → `tool_meta.py` 加行为标志 → `tools/impl/` 实现 → 测试
3. **加新交互类型**（弹窗/卡片）→ 在 `core/flows/` 加一个 flow，`RESULT_FLOWS` 注册；agent_loop 不用动
4. **数据三层**：JSON（章节/会话，用户数据）| novel.db（图谱，事实源）| search_fts.db（**派生索引，可重建**）
5. **check gate**：提交前 `python scripts/check.py`（CI 同款）；mypy 有 `.mypy-baseline` 增量门禁（存量 282，禁止新增）
6. **git 纪律**：禁止 `git add -A`（曾有外部会话污染历史）；`data/`、`chapters/`、`data_backup_*` 禁止入库（pre-commit 钩子拦截）
7. **依赖治理**：`pyproject.toml` 全部 pin `==`；改依赖 → `pip-compile` 更新 `requirements.lock` + `ALLOW_LOCKFILE_CHANGE=1` 提交（pre-commit 守卫）
8. **`_MEIPASS` 访问**用 `getattr(sys, "_MEIPASS", "")`（PyInstaller 打包路径，mypy 不认识裸 `sys._MEIPASS`）
9. **测试先行**：改核心行为前先补测试（历史教训：700+ 测试全绿却存在"10 秒误判取消"集成 bug）
10. **文档同步**：改架构/流程后更新 `docs/ARCHITECTURE.md` 和本页，别让下一个接手的人重新考古

## 5. 常见任务速查

- **手动测一个工具**：`tests/` 里仿照 `test_flows.py`（flow 单测）或 `test_tool_mutex.py`（prepared 层）
- **查图谱数据**：SQLite 直接 `sqlite3 data/novel.db`；章节在 `data/chapters_*.json`（带版本历史）
- **索引坏了**：`python scripts/rebuild_fts.py`（幂等，先 `--dry-run`）
- **发布**：`python scripts/release.py --dry-run patch`（然后按提示走）
- **mypy 存量**：`C:/Python313/python.exe -m mypy src/ --ignore-missing-imports --no-strict-optional --no-site-packages`

## 6. 已知问题与进行中的专项（接手时先看这里）

| 问题 | 状态 | 说明 |
|------|------|------|
| **SQLite 迁移不完整** | 🔴 进行中 | 约 40 处 Cypher 调用仍静默空转（extractor/foreshadow_matcher/search/confidence_scorer 等）。已修：impact_propagator、character_agent、narrator_agent（推演系统恢复）。**搜 `MATCH` 找剩余** |
| SQLiteStore 缺方法 | 🔴 | `schedule_foreshadow` 等 ~40 个方法被调用但未实现（Neo4j 遗留）——需逐个验证（死代码删/实现） |
| mypy 存量 | 🟡 282 | `.mypy-baseline` 兜底；清零是专项 |
| 覆盖率 | 🟡 39% | CI gate 38；40% 目标需补大文件测试 |
| 前端 | 🟡 | api.ts 已拆 http/sse，api 对象全量拆分/巨型组件（ChaptersPanel 1329 行）待做 |
| 并发 git 污染 | 🟡 | 曾有外部会话提交 chapters 数据（钩子被 `--no-verify` 绕过）；清理方法见 `.pi/plan.md` |

## 7. 文档导航（按需点入，不按顺序读）

- **架构**：`docs/ARCHITECTURE.md`（含数据层边界表）
- **前端审计**：`docs/FRONTEND_AUDIT.md`
- **重构计划/进度**：`.pi/plan.md`（M0-M9 checkbox + 风险登记）
- **健康清单**：`docs/CODE_HEALTH_ISSUES.md`
- **基线数字**：`docs/BASELINE.md`
- **测试**：`docs/TESTING.md`；**扩展开发**：`docs/EXTENDING.md`
- 历史归档（不更新）：`docs/archive/`

---

*本页由 2026-07-31 重构收尾时创建。改完大结构后记得更新本页第 3/4/6 节。*
