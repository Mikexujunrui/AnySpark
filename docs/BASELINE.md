# 重构基线（BASELINE）

> 生成：2026-07-31 | 对应 `.pi/plan.md` M0.1
> 用途：后续所有重构步骤的对照基准。任何"行为不变"的声明都以本文件数字为锚。

## 环境

- Python: 3.13.2（Windows C:\Python313）
- Node: 经 cmd.exe 调用（WSL→Windows interop）
- 数据: `data/` 191MB（含 15 本书章节+版本历史），已备份至 `data_backup_20260731/`（md5 抽查一致）

## 基线数字（2026-07-31 实跑）

| 检查项 | 命令 | 结果 |
|--------|------|------|
| 单元测试 | `pytest tests/ -q` | **706 passed, 3 skipped** |
| 覆盖率 | `pytest --cov=src` | **37%**（CI gate 为 30%） |
| Lint | `ruff check src/ tests/` | 0 errors |
| 类型 | `bash scripts/mypy_gate.sh` | 0 errors（baseline 320） |
| 前端类型 | `tsc --noEmit` | 0 errors |
| 前端 Lint | `npm run lint` | 0 errors, **141 warnings** |
| 构建 | `npm run build` | 未测（基线阶段跳过） |

## 关键薄弱点（重构重点）

| 模块 | 行数 | 覆盖率 | 说明 |
|------|------|--------|------|
| `src/tools/impl/writing.py` | 806 | **7%** | 最核心的写作工具实现，覆盖率最低 |
| `src/core/agent_loop.py` | 1904 | 低 | 系统心脏，行为测试刚起步（M2） |
| `src/routes/chat.py` | 1230 | 低 | SSE 交互主路径 |

## 已确认事实

- `git ls-files data/` = 0（用户数据已排除在版本库外）
- `search_fts.db` 由 `src/core/search.py` 的 `FullTextSearch` 管理（4 张 FTS 表），18 个文件引用
- `novel.db` 为 SQLite 图谱（SQLiteStore，含 entities_fts），11 张表
- 无 AGENTS.md（纪律条款见 `.pi/plan.md` 自带章节）
- git 历史含数据 commit（`create: 章一` 等），待 M5 清理（需主人确认）

## 变更日志

- 2026-07-31：ruff 修复 1 处（`asyncio.TimeoutError` → builtin `TimeoutError`，agent_loop.py）
