---
name: any-spark-git
description: AnySpark 项目（Windows + WSL 双环境）的 git 操作规范。涵盖 GitHub 远程认证（WSL 必须走 Windows OpenSSH，Windows 直接可用）、push/fetch/PR 查看、项目纪律条款（禁 git add -A、data/ 不入库、commit 编号规范）。在任何 AnySpark 仓库执行 git 远程操作、提交、查看 PR 时使用。
---

# AnySpark Git 操作规范

本项目在 Windows 上开发。agent 可能在两种环境运行：
- **纯 Windows 环境**：git/ssh 原生可用，无特殊前缀。
- **WSL 环境**（bash 工具在 WSL 里）：必须走 Windows OpenSSH（见 §1）。

本 skill 是新会话接手时的权威参考。**先判断自己运行在哪个环境**：
`uname -a` 含 `Microsoft` / `WSL` 即 WSL；否则是 Windows。

## 0. 环境速查

- 仓库：`git@github.com:Mikexujunrui/AnySpark.git`（私有）
- 项目目录：`D:/总/小说/写作辅助/自研高级时间线辅助写作agent`
- Python（WSL 内）：`/mnt/c/Python313/python.exe`；Windows：`C:\Python313\python.exe`
- 前端 node（WSL 内）：`/mnt/c/Program Files/nodejs/node.exe`（WSL 的 `node` 命令不存在）

## 1. ⚠️ WSL 下 git 远程访问（最大的坑）

**WSL 的 git 默认用 WSL 的 ssh，不认 Windows 的 SSH key** → 报
`git@github.com: Permission denied (publickey)`。

**解法：WSL 环境的所有远程命令必须加 `GIT_SSH_COMMAND` 前缀：**

```bash
export GIT_SSH_COMMAND="/mnt/c/Windows/System32/OpenSSH/ssh.exe"
# 或单条命令内联：
GIT_SSH_COMMAND="/mnt/c/Windows/System32/OpenSSH/ssh.exe" git push origin main
```

Windows OpenSSH 自动用 `C:\Users\24034\.ssh\id_ed25519` 等 key 认证。
**纯 Windows 环境不需要此前缀**——直接用 `git push origin main` 即可。

## 2. 常用远程操作

```bash
# 判定环境
uname -a 2>/dev/null | grep -qiE "microsoft|wsl" && echo "WSL" || echo "Windows"

# push
git push origin main                      # Windows
GIT_SSH_COMMAND="..." git push origin main  # WSL（"..." 见 §1）

# 查看远程 PR
git ls-remote origin 'refs/pull/*/head'   # 列出 PR 编号+commit
git fetch origin refs/pull/2/head:refs/remotes/origin/pr-2
git log --oneline origin/pr-2 -5          # 看 PR 内容
git diff main...origin/pr-2 --stat        # 对比 PR 与当前 main
```

## 3. 提交纪律（项目铁律，违反会污染历史）

1. **禁止 `git add -A`**，一律显式路径：`git add src/xxx.py tests/xxx.py .pi/plan.md`
2. **用户数据 `data/` 绝不进 git**（有 pre-commit 钩子，但 `--no-verify` 可绕过）
3. commit message 注明编号：`M{x}.{y}`（重构批次）/ `L{x}.{y}`（遗留专项）/ `fix:` / `test:` 前缀
4. 每批改动后跑门禁再提交：
   ```bash
   python -m ruff check src/ tests/
   python -m mypy src/ --ignore-missing-imports --no-strict-optional --no-site-packages
   python -m pytest tests/ -q --cov=src --cov-fail-under=40
   ```
5. 提交前确认无 `data/`、`.cov_data/` 被误跟踪：`git status --short && git ls-files data/ | head`

## 4. 项目状态锚点

- 重构进度：`.pi/plan.md`（M0-M9）+ `.pi/plan_legacy.md`（L 系列遗留专项）
- 交接指南：`docs/ONBOARDING.md`（第 5 节 git 纪律、第 6 节已知问题）
- 当前基线（2026-08-01）：mypy 0、覆盖率 40%（gate 40）、前端 api 已拆分、
  ChaptersPanel 994 行 / SettingsModal 903 行。远程有 PR #1/#2 未合并。

## 5. 常见误操作与恢复

| 情况 | 处理 |
|------|------|
| `git status` 显示 `data/` untracked | 正常（data/ 有嵌套 .git 残留，.gitignore 已整体忽略） |
| push 报 publickey（WSL） | 加 `GIT_SSH_COMMAND` 前缀（§1） |
| push 报 publickey（Windows） | 检查 `C:\Users\24034\.ssh\` key 是否被 GitHub 收录 |
| 忘记显式路径误 add | `git reset <file>` 撤销暂存 |
| 外部进程污染历史 | 见 `.pi/plan.md` 风险登记；恢复至最近代码 commit |
