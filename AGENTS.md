# AGENTS.md — 给实现智能体的开机说明

你是 **AnySpark v4 的实现者**。本项目最终目的是 AI 写小说。设计阶段已全部完成，你的任务是**按规格实现**。

## 必读（按顺序）

1. `docs/DESIGN.md` —— **唯一主规格**，全部设计都在这里。实现时必须完整遵循，不得遗漏、不得偏离。
2. `docs/AUDIT-V1.md` —— **设计实现审计报告**（现状快照：哪些已实现/哪些缺失/优先级，动手前必读）。
3. `docs/PROGRESS.md` —— 连续推进台账（各阶段交付 commit + 踩坑记录 + 补缺计划）。
4. 需要理解"为什么这样设计"时，再查 `docs/UPGRADE-DISCUSSION.md`（讨论纪要与推理过程，不是实现依据）。
5. `docs/HANDOFF-L-SERIES.md` —— 与旧仓库的边界（v4 专用文件别人不碰，你也不碰旧仓库）。

## 当前状态与任务

**核心功能已全部完成（S0~S63，全量测试绿 + 总闸通过）**：第一版七阶段 + 全部补缺 + 实测驱动演进 + **特化路线 P1-P5**（主人 2026-08-05 拍板：把 AnySpark 做成"小说特化版 pi"）+ **架构深化 S53-S63**（主人讨论驱动）。

**特化路线已交付**（详见 PROGRESS.md S48 系）：
- P1 工作区化（每项目一路径：上传存档/章节 md 权威/卡片 + 双写 + import 同步）
- P2 领域工具化（图谱/伏笔/计划/设定查证全部 agent 可自主调用——写作闭环实证）
- P3 格式管线（零依赖 txt/md/docx/pdf 提取 + 规则拆章 + 摘要卡 + EPUB 导出携图）
- P4 角色推演（低成本多探索 + 判别选优）+ codex 只读数据环境（真实统计）
- P5 代码扩展（沙箱 run_code + 扩展工具注册表：工具=数据，人工批准生效）
- 正文检索（search_chapters：词表批量/exclude 句级排除/regex/fragment 可调 + read_context 锚点读段落）
- 运行时模型（S47：多模型注册表 + 思考强度；V4 系列 1M 上下文）

**架构深化已交付（S53-S63，详见 PROGRESS 对应阶段）**：
- 心智模型=会话规划器（manual 分类 collab/style/habit，不再全量注入写作）；全项目内容化（explore/graph/settings 维度与类别全部内容载体化）
- 叙事技巧生成器（原文提炼五段式，A 手动/B 心智联动/C 信号驱动 + 人工确认闸门）；类型 skill 生成器（mode=main，主循环看）
- **C 架构**：write_chapter 意图模式（intent+references → 干净写作调用，治多章累积毒化——实验实证 0 幻觉）；直写=轻量写作；write_file 笔记/ 前缀=纯文档
- **S60 skill 注入瘦身**：主循环只注入全部技巧索引（名字+描述）+ `skill_lookup` 按需细看 + `write_chapter` 的 `skills` 点名——**写作调用不自行选技巧，所有注入由主循环点名决定**（S61 删自动匹配规则）
- **S59 工作流扩展包**（packages/workflow）：顺序/分支/循环三结构 + 断点恢复 + 失败策略 + AI 生成（草稿→人工确认）；叙事树 + 线进度（S59）；会话继承 fork（S58c）；项目简介 + context_mode（S58）
- **S61 心智完善**：档位 L2/L3 + 活跃度衰减 + context 动态选取；**S62 哲学审查**（去垃圾补丁）；**S63 画蛇添足清理**（mood 死代码/role_card 收敛/check_text 退役）

**剩余（按主人路线，非缺陷）**：新前端创作台（他人基于后端 API 开发——本仓库已无 frontend）/ 多模态（未来计划）/ B 真自我修复（补丁应用，按需）/ httpx2 迁移（等 starlette）。

**当前任务：按主人指示推进**（新阶段开工前先确认，纪律 7）。接手先读：README 当前状态 → PROGRESS.md 最新阶段 → DEV-AGENT.md（接入通道/测试链路）。

## 重要设计约束（实现时必须遵守）

- 机制硬编码、内容自然语言（DESIGN.md 第 1 节：硬编码边界：A 过程控制 / B 交互载体结构 / C 数据存储结构）
- 模型无关：所有承载物为明确无歧义自然语言（DESIGN.md 第 8 节）
- core 不依赖任何包（单向依赖）
- YAGNI：增强包（评审团/Autopilot/工作流/L3 模式库）明确按需后补，不提前建

## 主人已拍板的决策（勿推翻，见 PROGRESS.md 关键决策记录）

- **决策A（2026-08-02）**：全新项目，**不做旧数据导入/转移**，不背沉没成本。旧系统仅作思想参考。
- **决策B（2026-08-02）**：**全部真实实现**（DeepSeek DashScope + deepseek-v4-flash），禁止任何模拟/演示/降级实现。
- **决策C（2026-08-02）**：连续推进模式，用 PROGRESS.md 做跨会话台账接续。

## 纪律

- 禁 `git add -A`，一律显式路径
- `data/`、`chapters/`、`data_backup_*` 绝不入库
- 依赖 pin `==` + 锁文件（uv.lock）
- 每个 commit 标注阶段编号（如 `S7: ...`）
- 每阶段跑门禁：`uv run python scripts/gate.py`（ruff + mypy + pytest；本仓库无前端，tsc/eslint/build 不再执行）
- 对设计的任何偏离/新增：先停下，向主人确认，再更新 `docs/DESIGN.md`

## 并行协作纪律（多会话共享工作区，强制——S70 固化）

> 背景：多个 pi 会话并行编辑同一工作区，实测踩坑（S60 app.py 被裹挟 / S64·S66 撞号 /
> S65 play 逃 gate 检查 / S67 漏 ruff format / S65·S67 行尾污染 3 连踩）。以下纪律
> **所有会话强制**，开工即生效。本文件由 pi 自动加载，读完即可同步工作。

### 开工第一步（必做，顺序执行）
1. `git log --oneline -5` —— 看并行会话最新提交；**撞阶段号立即让位**（如对方已用 S66，你用 S67）
2. `grep -n "^## S6[0-9]\|^## S7[0-9]" docs/PROGRESS.md | tail` —— 确认最新阶段编号
3. 读 `docs/PROGRESS.md`「并行声明区」—— 若有会话声明在改某文件，**避开**或等它提交
4. 要改共享大文件（app.py/toolkit.py/pyproject.toml 等）前，**先在声明区写**：
   `> [S6x] 正在改 app.py：<改动内容>（完成提交后删本行）`
5. 提交前跑完整 gate（见下）+ `git status --short` 确认归属后显式 add

### 提交前必跑完整门禁（不跑子集）
- `uv run python scripts/gate.py` 全量（ruff check + format + mypy + pytest）
- 禁止只跑 check/mypy/pytest 子集就提交——S67 实测漏 `ruff format --check` 导致遗留红
- gate.py 已在开头输出「最近提交 + 工作区归属」核查块（S70），跑 gate 时顺便确认

### 新包注册清单（6 处，逐项勾，漏一处就逃检查/跑不起来）
```
① pyproject.toml [tool.uv.sources]      ② packages/app/pyproject.toml dependencies
③ pyproject.toml [tool.mypy] files+mypy_path   ④ pyproject.toml [tool.ruff] src
⑤ scripts/gate.py py_pkgs               ⑥ pyproject.toml [tool.pytest] testpaths
```
（S65 漏 ④⑤ 导致 play 包逃过 ruff 检查，S67b 修复——先例勿重犯）

### 行尾纪律（S70 .gitattributes 根治）
- 仓库已配 `.gitattributes`：git 内部存 LF、checkout 转 CRLF——**行尾差异不再算内容变化**
- 发现工作区文件被编辑器改成纯 LF 属正常（checkout/commit 自动转换），**不要手动统一行尾**
- 历史教训：S65 手动转 CRLF 引发误删类/复制中间代码事故——已被 .gitattributes 取代

### 同文件冲突救火（尽量避免：靠小步提交 + 声明区）
- 小步提交：每个逻辑改动独立提交，工作区不累积（S65 累积改动导致 checkout 救火 3 连错）
- 若必须救火：备份 → checkout 重建 → 恢复对方改动 → 全程验证 `git diff` 归属
