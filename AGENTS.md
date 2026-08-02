# AGENTS.md — 给实现智能体的开机说明

你是 **AnySpark v4 的实现者**。本项目最终目的是 AI 写小说。设计阶段已全部完成，你的任务是**按规格实现**。

## 必读（按顺序）

1. `docs/DESIGN.md` —— **唯一主规格**，全部设计都在这里。实现时必须完整遵循，不得遗漏、不得偏离。
2. 需要理解"为什么这样设计"时，再查 `docs/UPGRADE-DISCUSSION.md`（讨论纪要与推理过程，不是实现依据）。
3. `docs/HANDOFF-L-SERIES.md` —— 与旧仓库的边界（v4 专用文件别人不碰，你也不碰旧仓库）。

## 当前状态与任务

**设计已定稿，进入 T6 阶段 0（地基）**。七阶段计划见 DESIGN.md 第 9 节。

**阶段 0 任务清单**：
- [ ] 初始化 uv workspace（根 `pyproject.toml`，monorepo 多包：packages/core, explore, align, template, desktop）
- [ ] 创建 `packages/core`（anyspark-core）：极简 Agent 循环（while-true：读提示→调工具→回填→输出）、工具调用协议、事件协议（通用事件 + 注册钩子）、存储接口
- [ ] 轻量数据导入脚本：读取旧系统用户数据（见下），一次性导入/复制
- [ ] core 最小测试 + 门禁（ruff/mypy/pytest 就位后跑）
- [ ] **验收：core 跑通"读提示→调工具→回填→输出"最小循环；旧数据可导入**

**重要设计约束（实现时必须遵守）**：
- 机制硬编码、内容自然语言（DESIGN.md 第 1 节：硬编码边界）
- 模型无关：所有承载物为明确无歧义自然语言（DESIGN.md 第 8 节）
- core 不依赖任何包（单向依赖）
- YAGNI：先建 core + align + explore + ui 主路径，其余按需后补

## 旧系统数据（数据导入脚本的输入）

- 位置：`D:/总/小说/写作辅助/自研高级时间线辅助写作agent/data/`
- 格式：JSON（章节 `chapters_*.json` / 会话 `sessions_*.json` / 大纲/世界观/时间线等）+ SQLite 图谱（`novel.db`，含 FTS）
- 原则：**数据全是自然语言/JSON，导入成本低**；只读取，不做复杂迁移方案；切换时一次性导入，绝不丢

## 纪律

- 禁 `git add -A`，一律显式路径
- `data/`、`chapters/`、`data_backup_*` 绝不入库
- 依赖 pin `==` + 锁文件（uv.lock / package-lock.json）
- 每个 commit 标注阶段编号（如 `S0: ...`）
- 对设计的任何偏离/新增：先停下，向主人确认，再更新 `docs/DESIGN.md`
