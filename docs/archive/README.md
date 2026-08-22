# 归档文档

本目录存放已完成使命的历史文档——规划已落地、计划已实施、交接已完成、快照已过期。
保留供历史追溯，但**不再是当前工作依据**。

## 目录结构

```
archive/
├── progress/    PROGRESS.md 历史卷（S0-S186 已归档，内容未修改）
├── plans/        已完成使命的规划/计划/交接文档
├── snapshots/   自动生成的过期系统快照
├── decisions/    决策已落地的调研/对比文档
└── *.md          早期审计/缺口文档（第三方评审、后端/前端缺口）
```

## progress/ — PROGRESS.md 历史卷

| 卷 | 覆盖 | 拆出时间 | 内容摘要 |
|---|---|---|---|
| S0-S96.md | S0-S96 | S212 (2026-08-21) | 第一版七阶段 + 特化路线 P1-P5 + 架构深化 S53-S63 + 后端收敛与加固 S79-S96 |
| S97-S186.md | S97-S186 | S212 (2026-08-21) | 深化期——拆书/DSH 借鉴/统一化/规模化安全网/评审修复/质量债/前端整合 |

> 本卷为已凝固记录，不再更新；当前推进以 `docs/PROGRESS.md` 为准。

## plans/ — 已落地的规划与交接

| 文档 | 创建 | 归档原因（对应实施阶段） |
|------|------|-------------------------|
| PLAN-SKILL-UNIFY.md | 2026-08-13 | 统一 skill 容器——S127/S128/S130 三阶段全部完成 |
| PLAN-WORKFLOW-UNIFY.md | 2026-08-13 | 工作流统一化——S129/S133/S134/S135 四批全部完成 |
| PLAN-SCALE-SAFETY.md | 2026-08-14 | 规模化安全网——S138/S139/S140（resume+回溯+收编 batch）全部完成 |
| WORKFLOW-AUTOWRITE-PLAN.md | 2026-08-13 | 全自动续写工作流——阶段 1/2/3/4 全部完成 |
| HARNESS-UPGRADE-PLAN.md | 2026-08-13 | DSH 借鉴四提案——S116-S121（事件溯源/沙箱/skill 生态/子 Agent）全部落地 |
| REPAIR-LIST.md | 2026-08-14 | S147 质量债清单——A/B/C/D1 已修，D2 留待按需 |
| REPAIR-WF-SCRIPT-SPLIT.md | 2026-08-14 | D1 `_wf_run_script` 拆分——S151（commit `57dd2f6`）实施完成 |
| SHELL-PORT.md | 2026-08 | 壳移植计划——S75 前端并入即落地 |
| FRONTEND-HANDOFF.md | 2026-08-06 | 前端重开交接——S75 前端并入已完成 |

## snapshots/ — 过期快照

| 文档 | 生成时间 | 归档原因 |
|------|---------|---------|
| CURRENT-STATE.md | 2026-08-15 (S147) | `scripts/current_state.py` 自动生成的系统快照，已过期至 S211；重跑脚本可在 `docs/CURRENT-STATE.md` 重新生成最新版 |

## decisions/ — 已落地决策的调研

| 文档 | 日期 | 归档原因 |
|------|------|---------|
| MEMORY-SURVEY.md | 2026-08-14 | 心智模型 vs 主流记忆系统对比——S132/S132b/S132c/S132d/S132e 已落地，留作后续选型参考 |

## 根目录 — 早期审计/缺口

| 文档 | 创建 | 归档原因 |
|------|------|---------|
| BACKEND-ISSUES.md | 2026-08-10 | S75 前端测试发现的后端问题，大部分已在 S145/S146/S194/S195 修复 |
| FRONTEND-GAPS.md | 2026-08-11 | S75 前后端对账缺口，大部分已在后续迭代补齐 |
| REVIEW-THIRD-PARTY.md | 2026-08-14 | 第三方评审 P0/P1 问题清单，已逐项确认并在 S145/S146/S194/S195 修复 |
| REVIEW-THIRD-PARTY-PHILOSOPHY.md | 2026-08-14 | 第三方哲学层面审计，结论已回写 DESIGN.md 各章节 |

---

## 当前权威文档（不在本目录）

- `docs/DESIGN.md` — 唯一主规格
- `docs/PROGRESS.md` — 推进台账
- `docs/REVIEW-PROJECT.md` — 项目级综合评审报告（2026-08-19，S193 基准）
- `docs/BACKEND-MAP.md` — 系统运作地图
- `docs/uml/` — 有向逻辑图全集
- `docs/AUDIT-V1.md` — 设计实现审计
- `docs/DEV-AGENT.md` — 接入通道/测试链路
- `docs/EXTENDING.md` — 贡献者扩展指南
- `docs/UPGRADE-DISCUSSION.md` — 升级讨论纪要（持续累积）
- `docs/HANDOFF-L-SERIES.md` — 旧仓库边界
- `docs/LOCAL-LLM.md` — 本地模型适配指南
- `docs/PACKAGING.md` — 打包发布指南
- `docs/FRONTEND-SHELL.md` — 前端外壳设计规格 v3 定稿
