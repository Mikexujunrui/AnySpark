# 前后端对账缺口清单（S75 审计）

**来源**：S75 后端 API 全清单 vs 前端实际调用对账（2026-08-11）。
**状态**：✅ 已补 / ⬜ 待补（供前端开发者按迭代补）。

## ✅ S75 已补

- **操作信号上报**（api/signals.ts + 接入 2 处）：
  - 选候选卡 → `accepted`（chatStore.selectCandidate）
  - 手动编辑正文保存 → `modified`（chapterStore.updateChapterContent，含 old→new）
  - 信号走 /api/signals → 对齐闭环/心智提炼（S28/S73d）/档位调节恢复运作（此前前端不
    上报，后端闭环空转）；上报失败静默（尽力而为不阻塞主流程）

## ⬜ P0 待补（断后端闭环）

| 缺口 | 后端 API | 说明 |
|---|---|---|
| 定点编辑 | PATCH /api/chapters/{id}/patch | 前端目前 PUT 全量保存（可用）；定点编辑（锚点段插入/删除/替换）省 token 且 S44 设计能力 |

## ⬜ P1 重要能力（后端已就绪，前端未展示）

| 缺口 | 后端 API |
|---|---|
| 项目简介编辑 | GET/POST /api/brief + generate |
| AI 倾向档案 | GET/POST /api/bias（DESIGN 双向黑盒：用户应能看到 AI 倾向）|
| 批量改写/审读 | /api/batch/rewrite + review |
| 文档消化 | POST /api/ingest（上传→摘要卡）|
| 上传区 | POST /api/upload |
| 模板库 | /api/templates + generate + import（S68）|
| 影响分析 | GET /api/impact（S45 改一章影响下游）|
| 扩展工具注册表 | /api/tools（P5 人工批准闸门）|

## ⬜ P2 新功能跟随（S6x 系列前端未跟上）

| 缺口 | 后端 API |
|---|---|
| 互动推演 | /api/play/sessions（S65 推演树）|
| 路径探索 | /api/explore/path（S67 节点间串联）|
| 角色推演 | /api/role/card + play（S48）|
| 评审团 | /api/review/panel + reviewers（S64）|
| 探索维度管理 | /api/explore/dims（S50）|
| 心智变更通知 | /api/manual/notices（S74c 专门为前端设计——用户知情界面）|
| chat 增强 | /api/chat/cancel + rewrite + direction |

## 标注（不算缺口）

- /api/stats（T7 验证指标）、/api/codex、/api/graph/context、/api/graph/extract、
  /api/mind/agency-suggest（agent 工具通道）、/api/health（基础设施）
- wrapup 已确认前端接入真实 API（ChapterWrapup 调 /api/chapters/{id}/wrapup）✓
