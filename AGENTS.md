# AGENTS.md — 给实现智能体的开机说明

你是 **AnySpark v4 的实现者**。本项目最终目的是 AI 写小说。设计阶段已全部完成，你的任务是**按规格实现**。

## 必读（按顺序）

1. `docs/DESIGN.md` —— **唯一主规格**，全部设计都在这里。实现时必须完整遵循，不得遗漏、不得偏离。
2. `docs/AUDIT-V1.md` —— **设计实现审计报告**（现状快照：哪些已实现/哪些缺失/优先级，动手前必读）。
3. `docs/PROGRESS.md` —— 连续推进台账（各阶段交付 commit + 踩坑记录 + 补缺计划）。
4. 需要理解"为什么这样设计"时，再查 `docs/UPGRADE-DISCUSSION.md`（讨论纪要与推理过程，不是实现依据）。
5. `docs/HANDOFF-L-SERIES.md` —— 与旧仓库的边界（v4 专用文件别人不碰，你也不碰旧仓库）。

## 当前状态与任务

**核心功能已全部完成（S0~S58，全量测试绿 + 总闸通过）**：第一版七阶段 + 全部补缺 + 实测驱动演进 + **特化路线 P1-P5**（主人 2026-08-05 拍板：把 AnySpark 做成"小说特化版 pi"）+ **架构深化 S53-S58**（主人讨论驱动）。

**特化路线已交付**（详见 PROGRESS.md S48 系）：
- P1 工作区化（每项目一路径：上传存档/章节 md 权威/卡片 + 双写 + import 同步）
- P2 领域工具化（图谱/伏笔/计划/设定查证全部 agent 可自主调用——写作闭环实证）
- P3 格式管线（零依赖 txt/md/docx/pdf 提取 + 规则拆章 + 摘要卡 + EPUB 导出携图）
- P4 角色推演（低成本多探索 + 判别选优）+ codex 只读数据环境（真实统计）
- P5 代码扩展（沙箱 run_code + 扩展工具注册表：工具=数据，人工批准生效）
- 正文检索（search_chapters：exclude 句级排除/regex/fragment 可调 + read_context 锚点读段落）
- 运行时模型（S47：多模型注册表 + 思考强度；V4 系列 1M 上下文）

**架构深化已交付（S53-S58，详见 PROGRESS 对应阶段）**：
- 心智模型=会话规划器（manual 分类 collab/style/habit，不再全量注入写作）；全项目内容化（mood/explore/graph/settings 维度与类别全部内容载体化）
- 叙事技巧生成器（原文提炼五段式，A 手动/B 心智联动/C 信号驱动 + 人工确认闸门）；类型 skill 生成器（mode=main，主循环看）
- **C 架构**：write_chapter 意图模式（intent+references → 干净写作调用，治多章累积毒化——实验实证 0 幻觉）；直写=轻量写作；write_file 笔记/ 前缀=纯文档
- skill target 分流（writing→写作调用 / main→主循环 / both→两者）

**剩余（按主人路线，非缺陷）**：P6 前端壳（主人说后做）/ 多模态（未来计划）/ B 真自我修复（补丁应用，按需）/ 心智模型完整化（L2/L3 档位指导、渐进式披露按需引入）/ httpx2 迁移（等 starlette）。

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
- 依赖 pin `==` + 锁文件（uv.lock / package-lock.json）
- 每个 commit 标注阶段编号（如 `S7: ...`）
- 每阶段跑门禁：`uv run python scripts/gate.py`（ruff + mypy + pytest + tsc + eslint + build）
- 对设计的任何偏离/新增：先停下，向主人确认，再更新 `docs/DESIGN.md`
