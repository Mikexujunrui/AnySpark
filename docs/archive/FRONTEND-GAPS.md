# 前后端对账缺口清单（S75 审计）

**来源**：S75 后端 API 全清单 vs 前端实际调用对账（2026-08-11）。
**状态**：✅ 已补 / ⬜ 待补（供前端开发者按迭代补）。

> **S78（2026-08-11）**：以下清单已**全部补全**（前端缺口清零，commit e1deaa3，
> 11 个独立面板并行开发 + 全量 gate 通过）。新面板统一收敛进 Layout 顶栏「工具」
> 下拉坞，PathExplore 入 ExploreView，notices 入 ManualPanel 双视图。

## ✅ S75 已补

- **操作信号上报**（api/signals.ts + 接入 2 处）：
  - 选候选卡 → `accepted`（chatStore.selectCandidate）
  - 手动编辑正文保存 → `modified`（chapterStore.updateChapterContent，含 old→new）
  - 信号走 /api/signals → 对齐闭环/心智提炼（S28/S73d）/档位调节恢复运作（此前前端不
    上报，后端闭环空转）；上报失败静默（尽力而为不阻塞主流程）

## ✅ P0 待补（已补，S78）

| 缺口 | 后端 API | 前端落地（S78） |
|---|---|---|
| 定点编辑 | PATCH→POST /api/chapters/{id}/patch | chapters.ts + chapterStore.applyChapterPatch + Paper.tsx「定点编辑」面板（锚点段插入/删除/替换，不重写整章省 token） |

## ✅ P1 重要能力（已补，S78）

| 缺口 | 后端 API | 前端落地（S78） |
|---|---|---|
| 项目简介编辑 | GET/POST /api/brief + generate | api/brief.ts + briefStore + BriefPanel（AI 生成草案→人工确认写回） |
| AI 倾向档案 | GET/POST /api/bias（双向黑盒） | api/bias.ts + biasStore + BiasPanel（AI自述/用户修正 双来源 tag） |
| 批量改写/审读 | /api/batch/rewrite + review | api/batch.ts + batchStore（2s 轮询进度）+ BatchPanel |
| 文档消化 | POST /api/ingest | api/upload.ts + uploadStore + UploadPanel（auto/拆章/card三模式） |
| 上传区 | POST /api/upload + GET /api/workspace | UploadPanel 文件→base64→上传+消化一体化 |
| 模板库 | /api/templates + generate + import（S68） | api/templates.ts + templateStore + TemplatePanel |
| 影响分析 | GET→POST /api/impact（S45） | api/impact.ts + impactStore + ImpactPanel（选章分析受影响下游） |
| 扩展工具注册表 | /api/tools（P5 人工批准闸门） | api/tools.ts + toolStore + ToolsPanel（draft/active 状态 + 批准/停用） |

## ✅ P2 新功能跟随（已补，S78）

| 缺口 | 后端 API | 前端落地（S78） |
|---|---|---|
| 互动推演 | /api/play/sessions（S65 推演树） | api/play.ts + playStore + PlayPanel（会话列表/候选行动/回溯分叉/导出） |
| 路径探索 | /api/explore/path（S67） | explore.ts explorePath + ExploreView「路径探索」tab |
| 角色推演 | /api/role/card + play（S48） | api/role.ts + roleStore + RolePanel（角色卡 + N 路选优） |
| 评审团 | /api/review/panel + reviewers（S64） | api/review.ts + reviewStore + ReviewPanel（章节/文本评审 + 评分汇总） |
| 探索维度管理 | /api/explore/dims（S50） | api/dims.ts + dimStore + DimsPanel |
| 心智变更通知 | /api/manual/notices（S74c） | manual.ts listManualNotices + ManualPanel 条目/通知双视图（old→new变更展示） |
| chat 增强 | /api/chat/cancel + rewrite + direction | chat.ts + chatStore + ChatPanel（方向按钮 + AI消息改写渐变条 保原味/适中/大幅改 + cancel走后端） |

## 标注（不算缺口）

- /api/stats（T7 验证指标）、/api/codex、/api/graph/context、/api/graph/extract、
  /api/mind/agency-suggest（agent 工具通道）、/api/health（基础设施）
- wrapup 已确认前端接入真实 API（ChapterWrapup 调 /api/chapters/{id}/wrapup）✓
