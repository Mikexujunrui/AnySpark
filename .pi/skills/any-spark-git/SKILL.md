---
name: any-spark-git
description: AnySpark 项目的 git 操作规范——项目专属纪律（禁 git add -A、data/ 不入库、commit 编号）、环境速查、状态锚点、误操作恢复。通用 WSL/Windows SSH 认证坑见全局 skill `git-wsl-windows`。在任何 AnySpark 仓库做提交、push、查看 PR 时使用。
---

# AnySpark Git 操作规范（项目专属）

通用 WSL/Windows SSH 认证问题（`GIT_SSH_COMMAND` 前缀）→ 见全局 skill **git-wsl-windows**。
本 skill 只讲 AnySpark 项目特有的内容。

## 0. 环境速查

- 仓库：`git@github.com:Mikexujunrui/AnySpark.git`（私有）
- 项目目录：`D:/总/小说/写作辅助/自研高级时间线辅助写作agent`
- Python（WSL 内）：`/mnt/c/Python313/python.exe`；Windows：`C:\Python313\python.exe`
- 前端 node（WSL 内）：`/mnt/c/Program Files/nodejs/node.exe`（WSL 的 `node` 命令不存在，需绝对路径）

## 1. 提交纪律（项目铁律，违反会污染历史）

1. **禁止 `git add -A`**，一律显式路径：`git add src/xxx.py tests/xxx.py .pi/plan.md`
2. **用户数据 `data/` 绝不进 git**（有 pre-commit 钩子，但 `--no-verify` 可绕过；`data/` 含嵌套 .git 残留，.gitignore 已整体忽略）
3. commit message 注明编号：`M{x}.{y}`（重构批次）/ `L{x}.{y}`（遗留专项）/ `fix:` / `test:` / `docs:` 前缀
4. 每批改动后跑门禁再提交：
   ```bash
   /mnt/c/Python313/python.exe -m ruff check src/ tests/
   /mnt/c/Python313/python.exe -m mypy src/ --ignore-missing-imports --no-strict-optional --no-site-packages
   /mnt/c/Python313/python.exe -m pytest tests/ -q --cov=src --cov-fail-under=40
   ```
5. 提交前确认无 `data/`、`.cov_data/` 被误跟踪：`git status --short && git ls-files data/ | head`

## 2. 项目状态锚点

- 重构进度：`.pi/plan.md`（M0-M9）+ `.pi/plan_legacy.md`（L 系列遗留专项）
- 交接指南：`docs/ONBOARDING.md`（第 5 节 git 纪律、第 6 节已知问题）
- 当前基线（2026-08-01）：mypy 0、覆盖率 40%（gate 40）、前端 api 已拆分、
  ChaptersPanel 994 行 / SettingsModal 903 行。远程有 PR #1/#2 未合并。

## 3. 常见误操作与恢复

| 情况 | 处理 |
|------|------|
| `git status` 显示 `data/` untracked | 正常（嵌套 .git 残留导致，.gitignore 已整体忽略） |
| push 报 publickey | 见全局 skill `git-wsl-windows` |
| 忘记显式路径误 add | `git reset <file>` 撤销暂存 |
| 外部进程污染历史 | 见 `.pi/plan.md` 风险登记；恢复至最近代码 commit |
| CI 失败（mypy 增量超基线） | `.mypy-baseline` 仅在有意的存量增加时刷新；新增错误必须修复 |
