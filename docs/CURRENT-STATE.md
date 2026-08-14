# AnySpark v4 系统当前状态（自动生成）

> 生成：2026-08-14 14:08 UTC · commit `3696140 docs: PROGRESS S147 补 commit hash（ec5ffd9）` · 阶段 S147 · **非手写**：
> 由 `scripts/current_state.py` 扫描真实代码/DB 产出，改动后重跑即更新

## 一、系统规模

| 维度 | 数值 |
|---|---|
| 已交付阶段 | **S147** |
| API 路由 | **143** 个 |
| Agent 工具 | **47** 个 |
| Workflow 模板 | **8** 个 |
| 前端入口 | **27** 个 tab |
| 测试 | **602** 个 |
| 后端代码 | **28268** 行（align 4446, app 16615, check 555, core 1529, explore 837, graph 1518, template 1083, workflow 1685） |

## 二、能力清单

### Agent 工具（47 个，全量注入主循环 LLM）

- **写作（6）**：`list_chapters` `patch_chapter` `read_chapter` `read_file` `write_chapter` `write_file`
- **领域查证/登记（10）**：`graph_query` `graph_register` `material_register` `read_context` `read_material` `read_setting` `reference_lookup` `search_chapters` `skill_lookup` `skill_refine`
- **情节/计划/探索（10）**：`explore_direction` `path_explore` `plan_list` `plan_mark_done` `plot_delete` `plot_list` `plot_register` `plot_resolve` `plot_update` `role_play`
- **心智/信号（4）**：`mind_delete` `mind_reconcile` `mind_register` `mind_update`
- **批量/检测/收编（5）**：`batch_review` `batch_rewrite` `check_text` `ingest_document` `register_tool`
- **工作流/推演/评审/委派（10）**：`panel_review` `play_choose` `play_export` `play_start` `play_status` `run_subagent` `workflow_generate` `workflow_list` `workflow_run` `workflow_status`
- **网络/工具（2）**：`fetch_page` `search_web`

### Workflow 预置模板

- 章节加料
- 会话摘要
- 信号提炼
- 图谱抽取
- 批量审读
- 批量改写
- 拆书提炼
- 自动续写（知识注入 + 审读门 + 人工出口）

### 前端入口（人类可见）

功能 tab 27 个 + 模式徽标 4 个（Pro/Split/Flash/Custom）：

- `对话`（chat）
- `探索`（explore）
- `章节`（chapters）
- `叙事树`（storytree）
- `工作流`（workflow）
- `搜索`（search）
- `知识库`（knowledge）
- `大纲`（outline）
- `伏笔`（foreshadows）
- `资料`（materials）
- `参考书`（references）
- `技巧`（styles）
- `评审团`（review）
- `简介`（brief）
- `AI倾向`（bias）
- `批量`（batch）
- `模板`（templates）
- `扩展工具`（tools）
- `互动推演`（play）
- `维度`（dims）
- `代码`（codex）
- `上传`（upload）
- `AI文件`（files）
- `Pro`（quality）
- `Split`（split）
- `Flash`（flash）
- `Custom`（custom）

## 三、数据状态（真实库 data/anyspark.db）

| 数据 | 数量 |
|---|---|
| 章节 | **32** |
| 图谱实体 | **33** |
| 说明书条目 | **6** |
| skill 技巧 | **11** |
| 资料/灵感 | **4** |
| 当前模型 | `deepseek-v4-flash` |

## 四、人类可见映射（审计成果：AI 产出 → 人能看到）

| AI 能力 | 人类查看入口 |
|---|---|
| 章节读/写/改写 | 章节 tab（稿纸）+ 版本历史/恢复 |
| 图谱查证/登记 | 知识库 tab |
| 伏笔/计划 | 伏笔 tab + 大纲 tab |
| 技巧（skill） | 技巧 tab（按 type 分组+包徽标） |
| 资料/灵感 | 资料 tab |
| 批量改写/审读 | 批量 tab（工作流模式+确认闸门+回滚） |
| 工作流模板/任务 | 工作流 tab + 任务轮询 + 断点续跑/批级回滚 |
| AI 笔记/文件（write_file 产物） | **AI文件 tab**（S141 新增） |
| 推演/评审团 | 互动推演 tab + 评审团 tab |
| 网络搜索/精确检索 | 对话流 + 搜索 tab 的 AI 检索入口 |

---
*由 `uv run python scripts/current_state.py` 重新生成*