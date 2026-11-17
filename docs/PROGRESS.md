# AnySpark v4 — 连续推进台账 (PROGRESS)

> 用途：**跨会话持久状态**。即使中断/重启，从本文件即可无缝隙续接推进到第一版。
> 铁律：每个阶段完成后更新本文件；只记录真实完成状态，不记"计划中"为"已完成"。
> 更新：用日期 + `S<阶段>-<子步>` 标注。

---

## 总目标：第一版 = T6 七阶段全部完成 (见 DESIGN.md 第 9 节)

| 阶段 | 内容 | 验收 | 状态 |
|------|------|------|------|
| 0 地基 | workspace + core 骨架 | core 最小循环跑通 | ✅ 完成 |
| 1 核心写作 | DeepSeek 真实接入 + 工具集 + 探索-判别(单模型) + FastAPI 后端 | 对话→写作→修改基础流通 | ✅ 完成 |
| 2 对齐系统 | align 包：说明书/提炼/信号/注入 | 操作→信号→说明书→注入生效 | ✅ 完成 |
| 3 探索引擎 | explore 包：多智能体探索/概念卡/方向卡 | 种子→概念卡→方向卡→固化 | ✅ 完成 |
| 4 检测+规则 | 三层检测网/多检测者/规则编译器 | 检测报告可用；用户自然语言自定义规则 | ✅ 完成 |
| 5 模式+资料 | template 包：三层模式库/材料摘要卡 | 资料上传→摘要→注入；模式库可用 | ✅ 完成 |
| 6 收尾 | 增强包 + 打包/CI | 桌面壳可用；总闸全绿 | ✅ 完成 |

---

## 现状快照（接手 AI 必读）

- **设计实现审计报告**：见 `docs/AUDIT-V1.md`（基准 `6e8df7f`：S32-S63 全复核；此后 S64-S96 进展以本文件各阶段记录为准）
- **设计演进补记**：见 `docs/DESIGN.md` §12（S32-S46 变更集中追溯；§12.22-12.26 为 S59-S63，§12.39-12.42 为 S79-S82）
- **当前状态（S211）**：
  - **核心功能全部完成**（S0-S75）：七阶段 + 全部补缺 + 实测驱动演进 + 特化路线 P1-P5（工作区化/领域工具化/格式管线/角色推演/代码扩展/正文检索/运行时模型）+ 架构深化 S53-S63（心智模型=会话规划器/叙事技巧生成器/C 架构/skill 注入瘦身/工作流扩展包/哲学审查）
  - **S79-S82 后端收敛**：SQLite 连接收敛 + app.py 按领域拆 router + 双层资料库（全局池↔项目池）+ 资料库写入通道补全 + 会话绑定项目/智能体作用域隔离 + 图谱 API 项目隔离（跨书保护）
  - **S83-S96 收尾加固**：约束机制 + 审计修复 + 破限提示自编辑 + 模型注册表编辑功能（S89）+ 门禁自动分层（S96）
  - **S97-S152 深化期**：拆书三层（S114）+ DSH 借鉴四提案（S116-S121：事件溯源/沙箱/skill 生态/子 Agent）+ skill 容器统一（S127-S130）+ 工作流统一化（S129-S135）+ 规模化安全网（S138-S140）+ 第三方评审修复（S145/S146）+ 质量债修复（S147-S151）
  - **S153-S211 治理收敛期**：注释纪律固化（S153-S159）+ 项目级综合审查（S193，见 docs/REVIEW-PROJECT.md）+ app.py 瘦身 -75%（S187）+ tools_domain.py 拆分 -96%（S188）+ 路由拆分/竞态修复/空响应保护（S207-S211）+ 地图同步（S205）
  - **剩余（按主人路线，非缺陷）**：多模态（未来计划）/ B 真自我修复（补丁应用，按需）/ 实体改名（S72 主键语义，前端表单待适配）/ benchmark 自 S211 起暂搁置（体系保留，未重跑验证）
  - 测试现状：pytest 508 例全绿 + 前端 tsc/lint/build 全绿（分层门禁见 AGENTS.md）

> 📍 **接续锚点（2026-08-14，新会话必读）**：
> - **基线：总闸首次全绿**（commit `13f67ae`，S108b 以来首次）——ruff/mypy 183/pytest 508 全过，从干净起点动工
> - **S114 拆书三层已落地**（commit `faf7d4a`）：结构感知选章 + 骨架扫描 + 定点精读，猎手准则 367 万字实测发现回环（见 DESIGN §12.43）
> - **并行会话 S120-S126 已全部提交**（run_subagent/调研模板/资料库闭环/文档清洗），门禁红已清零
> - **两个规划已拍板待实施**（12 决策点主人全部确认）：
>   - `docs/archive/plans/PLAN-SKILL-UNIFY.md`：统一 skill 容器（type 分流 writing/main/plot + 书名包 + templates 并入；消费方等价性三纪律见 §6.1）——S127 阶段 1 ✅ + S128 阶段 2 ✅ + S130 阶段 3 ✅ 三阶段全部完成（容器统一收官）
>   - `docs/archive/plans/PLAN-WORKFLOW-UNIFY.md`：流程工具收编为 workflow 模板（加料用例/定时通知/节点导入 skill）——S129 第 1 批（拆书模板化打样）已实施
> - **下一步开工（建议顺序）**：
>   1. ~~SKILL 阶段 1/2/3~~ ✅（S127/S128/S130）；~~WORKFLOW 第 1/2/3 批 + 收尾~~ ✅（S129/S133/S134/S135）；~~加料模板~~ ✅（S137 非敏感指令验证）
>   2. 本地 vLLM/LM Studio 适配文档 ✅（S137 已出 docs/LOCAL-LLM.md）
>   3. WORKFLOW 收尾后续：/api/batch 内存实现可再收编（前端已工作流模式并存，按需）
>   4. ~~质量债修复清单~~ ✅（S148 A 死代码 + S149 B 决策三删 + S150 C 测试装配 helper + S151 D1 _wf_run_script 拆分；D2 app.py 瘦身留待按需——见 docs/archive/plans/REPAIR-LIST.md）
### 并行声明区（开工必读/必写——改共享文件前先在此声明，提交后删除本行）
> ⚠️ S81 事故留痕（归属说明，勿删）：commit `f7cbec8`（S81 档位高亮修复）提交时裹挟了并行会话对 `frontend/src/components/SettingsModal.tsx` 的**未提交**模型编辑功能改动（EMPTY_MODEL_FORM / startEditModel / registerModel 改造，S88 系内容）。代码无丢失、可编译，但归属混在该 commit——相关会话如需单独追溯见 `git show f7cbec8` diff。
> ⚠️ S152 撞号裹挟留痕（归属说明，勿删）：并行会话 commit `ffc383a`（S152 预置模板保护）提交时裹挟了本会话对 `api/workflow.ts`/`WorkflowPanel.tsx`/`routes_workflow.py`/`test_workflow_api.py` 的**未提交**改动（工作流画布打开 setDraft/原地保存 id/运行绑 bookId）。代码无丢失、可编译；但该提交的 `req.id` 与 `startRun(bookId)` 依赖本会话的 `schemas.py`/`workflowStore.ts` 未提交改动——二者已随本会话提交 `b9xxxx` 补齐，HEAD 才完整。
> [S259] 已提交完成（commit `9706bbe`，书架改名+简介双 bug 修复，总闸全绿）
> [S162] 已提交完成（commit `9f14502`，三 bug 修复 + 前端链路补齐，门禁全绿）——声明行随 S162 提交后删除
> [S145] 已提交完成（6 commits：311e94b/5fdfa93/624a515/fd5acbb/1b3e36f/edc0984，第三方评审修复）——声明行随 S145 提交后删除
> [S146] 已提交完成（7 commits：5976551/77417f9/090dc45/09ffa40/a4ad7f4/795cc9c/588de6c，评审未修项批 E-I）——声明行随 S146 提交后删除
> 📢 [S99] 已提交完成（commit `515294a`，SSE 接力第二步）——通知 S100：useSSE.ts 的 session_tokens/nearLimit 与 routes_chat.py 的 done 帧 model 字段随本提交带走（交织无法 hunk 分离），归属见提交说明；ChatPanel.tsx 的 UsageStrip 接入已 add -p 分离留在工作区，待 S100 补交（补交前先 git diff 确认归属）
> 声明格式：`> [S6x] 正在改 <文件>：<改动内容>`（多个文件逐行写）


- **候选清单（下一步，按优先级）**：
  1. **心智模型系统**（设计内降权，核心候选）：包罗万象（文风/喜好/毒点/边界）+ **渐进式披露**（索引常驻/正文按需，对齐 pi skills）——manual 是雏形，需设计分类与注入时机；含档位 L2（AI 看心智后建议档位）/L3（自然语言生成档位）
  2. **对比层回归**：S18 三任务（设定忠实/长书一致/偏好记忆）在 S32-S46 后重跑（成本 ~20min）
  3. **前端 UI**（主人明确不优先）：伏笔面板/图谱可视化/设定档/技巧/计划/批量/定点编辑/影响分析均无 UI（API 全）
  4. **设定档渐进式披露**：条目多时分段/按需注入（当前全量）
  5. **影响分析主角线过度报告优化**：核心实体与事件线区分报告（当前主角线=全影响提示）
  6. **list_events 默认 limit**：200 对超长书截断，调用方需显式传大 limit（当前用法已知）
  7. **工作流统一化（规划见 docs/archive/plans/PLAN-WORKFLOW-UNIFY.md，2026-08-13 主人指示先写思路；S129 拆书 ✅ + S133 批量 ✅ + S134 轻流程 ✅ + S135 收尾 ✅）**：固定流程工具（拆书/批量改写/批量审读/图谱抽取等）收编为预置 workflow 模板，工具只留 agent 决策的原子动作 + 执行器——分批迁移（拆书 ✅→批量 ✅→轻流程 ✅→工具收编 ✅），每批对拍验证可回退
  8. **统一 skill 容器（方案见 docs/archive/plans/PLAN-SKILL-UNIFY.md，2026-08-13 主人定方向；S127/S128/S130 三阶段全部完成 ✅）**：知识统一进 skill 容器按 type 分流（writing/main/plot），书名成包（pack_id 聚合，整包引用写作只取 writing/both——纪律 3），拆书一次产出整包（含剧情模式骨架派生）；templates 已并入 ✅；workflow（执行）保持独立——加 type ✅ → 并 templates ✅ → 书名包 ✅，skills/templates 归属竞争彻底消除
- ~~httpx2 迁移~~ ✅（S66 完成）；~~Autopilot~~ —— 已划掉：S59 工作流（loop+gate+approval+AI 生成流程）已吸收其全部机制价值，需要"全书自动连写"时用 workflow_generate + 人工确认 + 跑循环即可，不另起包（同评审团判断逻辑）
- 纪律：每阶段开工前向主人确认；对设计的偏离/新增先确认再改 DESIGN.md

## 关键决策记录（主人拍板，见下方日期）

- **2026-08-02 决策A**：v4 作为完全全新的项目建设，**不做旧数据导入/转移**，不背沉没成本。旧系统仅作思想参考。→ 移除了 S0 数据导入脚本验收项。
- **2026-08-02 决策B**：**全部真实实现**。用 pi 同款 DeepSeek API（DashScope 端点 + `deepseek-v4-flash` 模型），禁止任何模拟/演示/降级实现。
- **2026-08-02 决策C**：连续推进模式——不中断到第一版。用本 PROGRESS.md 做跨会话台账接续。

---

## 历史卷（S0-S186 已归档）

本文件只保留**当前卷（S187+）**及顶部导航。历史阶段已拆为两卷归档，内容未修改：

| 卷 | 覆盖 | 位置 | 内容摘要 |
|---|---|---|---|
| 卷一 | S0-S96 | [docs/archive/progress/S0-S96.md](archive/progress/S0-S96.md) | 第一版七阶段 + 特化路线 P1-P5 + 架构深化 S53-S63 + 后端收敛与加固 S79-S96 |
| 卷二 | S97-S186 | [docs/archive/progress/S97-S186.md](archive/progress/S97-S186.md) | 深化期——拆书三层(S114) + DSH 借鉴四提案(S116-S121) + skill/workflow 统一化 + 规模化安全网(S138-S140) + 第三方评审修复(S145/S146) + 质量债(S147-S151) + 前端整合 |

> 历史卷为已凝固记录，不再更新；当前工作以本文件下方各阶段为准。

---

## S187: app.py 瘦身——种子函数提取到 seeds.py + 工作流脚本提取到 wf_scripts.py + 吞异常清理（已完成 ✅）

**背景**：S186 后项目审查发现 app.py 膨胀至 1889 行（"上帝函数"问题），`except Exception: pass` 吞异常 9 处。

**改动**：
1. **seeds.py（654 行）**：提取 8 个 `_seed_*_template` 函数 + `_migrate_templates_to_skills`——纯函数（不引用 build_app 闭包），提取无行为变化。
2. **wf_scripts.py（888 行）**：提取 ~20 个 `_wf_script_*` 函数 + `_wf_run_agent`/`_wf_run_subagent`/`_wf_run_script`/`_wf_runner`/`_wf_judge`/`_wf_resolve`——从闭包提取为模块级函数，依赖通过 `WfScriptDeps` dataclass 传入（build_app 创建 wfd → 赋值 model/chapters/graph/settings/library/workspace/skills → deps 创建后回填 wfd.deps）。内部调用加 wfd 参数透传。
3. **吞异常清理**：
   - **加 logger.warning（4 处）**：routes_workflow.py 通知失败 ×2、tools_workflow.py 通知失败、tools_domain.py 设定查证失败、wf_scripts.py 参考书知识层渲染失败——排障需要这些信息。
   - **保留 pass + 注释（5 处）**：cli_chat.py 状态文件读取/cancel fire-and-forget、tools_web.py URL 提取、desktop 健康检查轮询、wf_scripts.py 双写落盘——真正 best-effort，加注释说明。

**结果**：app.py 从 1889 行 → **465 行**（-75%），组合根回归纯粹（FastAPI 实例 + router 挂载 + 生命周期 + WfScriptDeps 装配）。

**验证**：ruff + mypy 全绿（57 文件）；pytest 61 passed（test_app + workflow + workflow_api，排除既有竞态 test_chat_stream_sse_frames）。

## S188: tools_domain.py 拆分——2266 行按功能域拆到 6 个模块（已完成 ✅）

**背景**：S187 审查发现 tools_domain.py 2266 行是最大单文件（25 个 make_* 工厂函数）。

**改动**：按功能域拆分到 6 个模块（全部是独立工厂函数，接收 store 参数，不引用闭包——提取无行为变化）：
- tools_graph.py（165 行）：图谱查证/登记（graph_query/graph_register + _QUERY_LIMIT/_RELATION_LIMIT）
- tools_plot.py（358 行）：伏笔/计划/设定查证（plot_*/plan_*/setting_query）
- tools_search.py（309 行）：正文检索/锚点阅读（search_chapters/read_context + _sentence_at/_sent_has）
- tools_align.py（559 行）：心智登记/管理 + 技巧提炼（mind_*/skill_* + _run_refine_template/_locate）
- tools_reference.py（323 行）：参考书检索/批量任务（reference_lookup/batch_* + render_reference_knowledge + helpers）
- tools_explore.py（613 行）：角色推演/路径探索/推演/沙箱/资料/扩展注册（roleplay/path_explore/play/codex/ingest/material/register_tool）
- tools_domain.py（82 行）：兼容性 re-export 层（保留所有 make_* 导出，兼容 toolkit.py 等现有 import）

**结果**：tools_domain.py 从 2266 行 → 82 行（-96%）；6 个功能域文件各 165-613 行。

**验证**：ruff + mypy 全绿（16 文件）；pytest 67 passed（test_app + test_models + test_codex，排除既有竞态）。

## S188b: workflow store 补测试——14 个未测方法覆盖（已完成 ✅）

**背景**：审查发现 WorkflowStore 有 14 个方法未被测试覆盖（draft 生命周期/builtin 保护/节点状态管理）。

**改动**：新建 `packages/workflow/tests/test_store.py`（26 个测试，3 个测试类）：
- TestBuiltinProtection（6 个）：is_builtin/mark_builtin_by_name/delete_template——预置模板保护逻辑
- TestDraftLifecycle（10 个）：add/list/get/promote/reject/delete draft——草稿→人工确认→转正闸门
- TestNodeState（10 个）：update_node_state/increment_attempts/append_result/node_status/node_output——断点恢复基础

**验证**：ruff + mypy 全绿；pytest 26 passed（1.28s）。

## S189: 远程部署双 bug 修复——Anthropic tool 配对 400 + 打包版配置重启回退（已完成 ✅）

**背景**：远程打包版（PyInstaller exe）用户反馈两处问题：① Anthropic 协议调用偶发 400
`messages.N.content.0: tool_use_id found in tool_result blocks`（tool_result 无对应
tool_use）；② 界面设置的模型接口重启后回退成阿里云 DashScope。

**根因**：
1. `to_anthropic_messages` 的 S182 防御用**全局累积**合法 id 集合——一条 user 里的
   tool_result id 只要在"任意历史 assistant 的下一条"出现过就被永久放行，
   即使其 tool_use 已被压缩截断/跨协议切换重写丢失 → 孤儿 tool_result 残留在
   发送给 Anthropic 的 messages 里 400。另外 `_truncate_tail` 从头部逐条丢消息
   可能留下孤儿 tool 或悬挂 assistant(tool_use)（配对被拦腰截断）。
2. `ModelRegistry._sync_default_from_env` 每次启动**无条件**把 .env 的 DEEPSEEK_*
   覆盖进库中 `id=default` 配置——打包版 exe 目录 data/.env 固定阿里云，界面配置
   重启后被无声打回。

**改动**：
- `anthropic.py`：防御重写为**严格双向配对**——① user 的 tool_result id 必须在其
  紧邻前一条 assistant 的 tool_use 声明中（否则移除，含空 id）；② assistant 的
  tool_use id 必须出现在紧邻下一条 user 的 tool_result 中（否则移除）。两遍交集
  收敛，杜绝"任何历史 id 合法"误放行。
- `context.py`：`_truncate_tail` 按**配对单元**删（assistant + 其后连续 tool 同删；
  开头孤儿 tool 直接清）；`_find_cut_point` 保证保留段第一个非 system 必须是
  user（assistant 连同其后 tool 整单元切进压缩段，防配对截断 + messages[0] 非法）。
- `registry.py`：default 被界面保存过（updated_at != created_at）→ .env 不再覆盖；
  upsert 编辑保留 created_at（编辑不改创建时间，标记才可靠）；播种统一时间戳。
- 测试新增 5 个（orphan tool_result 穿透/空 id/截断配对/界面接管）+ 修复存量
  mypy union-attr 错误 1 处。

**验证**：ruff/mypy 全绿（213 文件）；app 全量测试 177 passed（排除既有竞态
test_chat_stream_sse_frames）+ core/align/explore/check 全绿。

## S191: 转换层"纯映射"收敛——core 共享配对守卫（讨论落地 A，已完成 ✅）

**背景（讨论落地第 A 步，向 pi 对齐）**：输入侧不变量（S189 转换/压缩 + S190 存储写入守卫）
已经保证任何路径产生的消息配对完整，转换层本应只剩"忠实映射"。但现状：anthropic 有完整
严格防御（S174/S182/S189），gemini/responses 只有"悬挂声明"半防御，OpenAI 兼容（deepseek.py）
**完全没有防御**——每个协议各自为政，未来加新协议要重写一套。

**改动**：
- 新建 `packages/core/src/anyspark/core/messages.py`：`sanitize_tool_pairing(messages)`——
  模型无关的通用配对守卫（纯函数、幂等、不改输入）。处理孤儿 tool / 悬挂声明 / 缺 id
  补配三类残缺配对。这是"宽松层"（允许被 user 插话隔开）；协议特有的"严格紧邻"
  （Anthropic）由各适配器转换防御保留。
- **四协议转换入口统一接入**（转换第一行）：anthropic/gemini/responses/deepseek——
  OpenAI 协议首次获得此前缺失的防御；gemini/responses 补上"孤儿结果"这一端。
  新增协议只需调一次 `sanitize_tool_pairing`，不再重写补丁。
- core `__init__` 导出该函数。

**验证**：core 7 个新测试 + adapters/models 全绿；ruff/mypy/format 全绿（9 源文件）。

## S192: 配置单一事实源钉死（讨论落地 B，已完成 ✅）

**背景（讨论落地 B，学 v3/pi）**：v3 用单个 `data/settings.json` 作唯一权威，`.env`
仅首启播种。v4 的等价语义在 S189 已落地（界面保存过 default → .env 不再覆盖），
本步把契约钉死、防回归，并文档化。

**改动**：
- 文档：DESIGN §12.9 明确"SQLite 是运行时模型配置唯一权威，.env 仅种子——
  界面接管后 .env 无任何覆盖权"（含 api_key 语义：resolved 库优先 env 兜底）。
- 测试：`test_registry_ui_edit_default_survives_restart` 补 context_window——
  界面接管 default 后，.env 改 base_url/model/**context_window** 重启都不覆盖
  （S178 专门加的 context_window 同步字段，同路径同样验证接管豁免）。

**验证**：test_models 19 全绿；ruff/mypy/format 绿。

## S193: 前端编辑历史能力落地——save 排序 bug 修复 + 端到端契约测试（讨论落地 C，已完成 ✅）

**背景（讨论落地 C）**：前端 InlineEditor（S80）本就能编辑 AI 输出文本，S190 写入守卫
已让"改文本不 400"安全。但**端到端回归测试暴露一个真实排序 bug**：`save_conversation_messages`
用 `(role, content)` 当 key 做 `old_seq` 重排——**编辑过内容的消息 content 变后查不到旧
序号（9999 落到末尾），被挤到对话最后、打乱顺序**。这正是 v4 扁平 Message 相对 v3
结构化 Part 的坑：改文本与配对结构耦合。

**改动**：
- `routes_conversations.py save_conversation_messages`：
  - **去掉基于 content 的 old_seq 整体重排**——前端数组相对顺序就是用户看到的顺序，直接
    作为序列主体（编辑的消息保持原位，不再被挤走）。
  - **工具轮声明按配对 id 精确插回**其 tool 结果之前（空 content 声明 S145b 前端过滤不可见，
    从旧序列按 tool_call_id 定位补回），而非靠内容关联——保证"声明→tool 结果"顺序与配对完整。
- 测试：新增端到端 `test_edit_agent_text_keeps_tool_pairing_e2e`——写自然配对历史 → 前端
  编辑终结回复文本 → 保存 200 → store 验证 [user,声明,tool,编辑回复] 顺序与 c1 配对完整、
  GET 验证编辑生效。钉死"C 编辑输出历史（不含工具）安全可用"契约。

**验证**：app 全量测试绿（排除既有竞态）；ruff/mypy/format 绿。

## S194: 对齐闭环修复 + 检测网 AI 动态检测项落地（已完成 ✅）

**背景**：项目级审查发现"操作即信号"哲学在对话写作模块断裂（选方向卡/回答歧义点不上报信号），DESIGN 机制 9 第②层"AI 动态生成检测项"未实现。

**改动**：
1. **对话信号采集修复**（`ChatPanel.tsx`）：4 个处理器加 `reportSignal`——
   - `handlePlotCardSelect` → `reportSignal('accepted', text, {context: '对话方向卡选择'})`
   - `handlePlotCardReject` → `reportSignal('rejected', cards, {context: '对话方向卡拒绝'})`
   - `handleQuestionReply` → `reportSignal('accepted', questions, {context: '对话歧义点回复'})`
   - `handleQuestionReject` → `reportSignal('rejected', questions, {context: '对话歧义点拒绝'})`
   - 此前 5 种信号只有 modified 活着，现在 accepted/rejected 在对话写作模块也活着——"操作即信号"哲学恢复。

2. **AI 动态检测项生成器**（`check/reviewers.py`）：新增 `generate_dynamic_checks(model, book_context)`——
   - 从图谱实体 Top 10 + 伏笔 must 钩子 Top 5 组装作品上下文
   - LLM 生成 2-4 条作品专属检测项（如"检查陈渡的灯塔看守人身份是否前后一致"）
   - 与静态骨架合并执行（`run_review` 加 `book_context` 参数）
   - `/api/check` 端点自动传入作品上下文激活动态检测——此前检测项恒为静态骨架 7 条，现在随作品演化

3. **审查发现的已修复项确认**（S145/S146 已落地，S194 核查）：
   - ✅ "已自动注入"过期文案：DEFAULT_SYSTEM 和 graph_query 描述已正确说"图谱不常驻注入"
   - ✅ 说明书用户编辑权：BiasPanel 已有完整 CRUD（S146 落地）
   - ✅ "校验一致性"按钮：已改调 `/api/check`（S145 修复）
   - ✅ reference_lookup 装配：agent_factory 已传 `library=deps.library`（S145 修复）

**验证**：
- 后端：ruff + mypy 全绿（6 文件）；pytest 34 passed（test_app）+ 14 passed（test_review）
- 前端：tsc + eslint + build 全绿
- 测试：新增 4 个动态检测项生成器测试（空上下文/正常解析/垃圾返回/缺字段跳过）

## S195: 用户可增删骨架检测项落地——持久化+API+测试（已完成 ✅）

**背景**：DESIGN 机制 9 第③层"用户可增删骨架"此前只有注释（skeleton.py:53），无持久化/API。审查报告标注为 🟢 轻微缺口。

**改动**：
1. **UserSkeletonStore**（`check_store.py`，133 行）：SQLite 持久化用户自定义检测项
   - additions 表：用户添加的检测项（id/category/description）
   - deletions 表：用户删除的默认检测项 category 标记（可恢复）
   - `merged_checks(defaults)`：合并默认骨架 + 用户添加项 - 用户删除项
2. **装配**：app.py 创建 `UserSkeletonStore` → 注入 AppDeps.user_skeleton
3. **API 端点**（`routes_check.py`）：
   - `GET /api/check/skeleton`：列出全部检测项（标记 builtin/user/deleted）
   - `POST /api/check/skeleton`：添加用户检测项
   - `DELETE /api/check/skeleton/{category}`：删除（默认项标记隐藏可恢复，用户项直接删）
   - `POST /api/check/skeleton/{category}/restore`：恢复被删除的默认项
4. **`/api/check` 集成**：审读时使用 `merged_checks` 合并后的检测项列表

**验证**：ruff + mypy 全绿；pytest 34（test_app）+ 7（test_check_store）passed。

## S195b: 跨层升级落地——发现跨书重复偏好+升级全局+死锁修复（已完成 ✅）

**背景**：DESIGN §6 要求"系统发现多本书重复偏好→建议升级全局→用户确认→锁定"。此前完全未实现。审查报告标注为 🟡 中优先级。

**改动**：
1. **ManualStore 新增 2 方法**（`manual.py`）：
   - `find_cross_book_candidates(min_books=3)`：跨书相似条目检测（双字窗口关键词交集≥3）
   - `promote_to_global(entry_id)`：项目级→全局级升级（默认锁定+通知原项目）
2. **API 端点**（`routes_check.py`）：
   - `GET /api/manual/cross-book-candidates`：发现候选
   - `POST /api/manual/{entry_id}/promote-global`：确认升级
3. **死锁修复**：`ManualStore._lock` 从 `Lock` 改为 `RLock`——`promote_to_global` 内部调 `self.get()` 需可重入
4. **测试**：4 个新测试覆盖发现候选+升级+边界

**验证**：ruff+mypy 全绿；pytest 15（test_manual）+ 34（test_app）+ 7（test_check_store）+ 14（test_review）= 70 passed。

## S196: 文档收敛——DESIGN.md 更新+历史归档+评审报告同步（已完成 ✅）

**改动**：
1. **DESIGN.md 更新**：§61/§211 标注氛围滑块组 S63 删除、场景拼图板（未来）
2. **历史文档归档**：BACKEND-ISSUES / FRONTEND-GAPS / REVIEW-THIRD-PARTY / REVIEW-THIRD-PARTY-PHILOSOPHY → `docs/archive/`
3. **REVIEW-PROJECT.md 更新**：差距分析表标注 S145/S146/S194/S195 修复项；功能深度评分 ⭐⭐⭐→⭐⭐⭐⭐

**归档原因**：审查报告建议"深度收敛"——冻结新功能、修设计-实现差距。S194/S195 已修复所有 P0 差距，历史审计文档完成使命归档。

## S197: 日志完善 + graph_query 属性名 bug 修复（已完成 ✅）

**背景**：端到端写作测试发现日志只记 `工具结果: graph_query ok=False`，无返回内容，无法排查原因。完善日志后发现 `graph_query` 报 `'Relation' object has no attribute 'type'`。

**改动**：
1. **日志完善**（`loop.py` 三处 emit + `routes_chat.py` 日志格式）：
   - tool_result 事件 payload 增加 `content`（截断 200 字）
   - 日志格式从 `工具结果: graph_query ok=False` → `工具结果: graph_query ok=False content=图谱查询失败：'Relation' object has no attribute 'type'`
2. **graph_query bug 修复**（`tools_graph.py`）：
   - `r.type` → `r.rel_type`（Relation schema 属性名是 `rel_type` 不是 `type`）
   - 此前所有 graph_query 调用全部失败，agent 无法查证图谱（写作有 fallback 不崩，但信息不完整）

**验证**：ruff + mypy 全绿；graph_query 工具调用从 ok=False → ok=True（返回完整图谱信息）

### S198 测试结果：高级工具全面激活（已完成 ✅）

**第 13-14 章工具调用对比**：

| 工具 | S196 前(3章) | S198 后(2章) | 说明 |
|------|-------------|-------------|------|
| explore_direction | 0 | 2 | 关键转折章主动探索方向 |
| skill_lookup | 0 | 8 | 写前查叙事技巧 |
| role_play | 0 | 1 | 推演角色反应 |
| plot_resolve | 0(失败) | 4(成功) | 伏笔回收闭环 |
| plot_register | 0 | 4 | 新伏笔登记 |
| graph_register | 0 | 3 | 真相登记到图谱 |
| graph_query | 0(失败) | 2(成功) | S197 修复后可用 |

**数据增长**：章节 33→38，图谱 33→50 实体，伏笔回收 0→11，说明书 6→7
**质量**：最新 2 章零破折号、无"正如"开头

## S200: tool_calls 悬挂 400 根因定位 + 数据落库修复 + 取消收尾自愈（已完成 ✅）

**背景**：远程自部署用户（打包版）多次报 OpenAI 400 `insufficient tool messages following
tool_calls message`，此前 S23/S158d/S158g/S158h/S169/S170/S190/S191/S193 已修 7 轮仍复发。
本次不再表面修补，做完整根因分析。

**根因分析结论**：
1. **历史数据残留**：数据库 `data/anyspark.db` 实测存在 3 个会话共 4 条悬挂声明
   （assistant 声明 tool_calls 但无 tool 结果，如「seq=28 声明 2 个 → seq=29 已中断」）。
   这是 S170 修复**之前**（取消收尾不补回填）产生的遗留数据。
2. **内存级自愈不管 DB**：当前代码 `_heal_tool_pairs`（store 层）+ `sanitize_tool_pairing`
   （模型调用前）双守卫**能修但只修内存**——每轮请求重新读残缺数据、重新修，DB 永不干净。
3. **不是打包版特有**：源码版同样会踩（路径逻辑一致，差异只在数据目录位置）。打包版用户
   更容易遇到是因为：① 用的是修复前旧版本（无 S169/S170 守卫）② 旧数据积累时间长。
4. **读路径全覆盖**：store.messages() → _heal；模型调用前 → sanitize；write 路径
   （replace_messages）→ _heal。实测修复后 0 悬挂，请求不再 400。

**修复（双层）**：
1. **脚本 scripts/repair_tool_pairs.py**：把 DB 里全部会话的悬挂声明修剪**落库**（根治，
   不再靠每轮内存修复）。幂等，可发给打包版用户手动跑。实测 DB 3 个会话 3 条消息修复，
   二次运行 0 变更。
2. **loop.py `_finish_aborted` 自愈**（S200）：取消收尾前先扫描 store 补未配对声明的
   tool 回填，再写「已中断」文本——从源头阻断新产生悬挂（异常中断/旧版遗留场景兜底）。
   新增 `_collect_dangling_decls` 辅助（模块级纯函数）。

**回归测试**：新增 test_finish_aborted_repairs_preexisting_dangling（10 次随机延迟取消，
断言任意时机收尾后无悬挂）。test_loop + test_messages 全绿，ruff/mypy 全绿。

### S200b：历史悬挂自动清理（用户零操作）（已完成 ✅）

**需求**：S200 出了 repair 脚本，但"让用户自己清理"不可行。改为**新版后端启动时自动清理**。

**改动**：
1. `sqlite.py`：`SqliteConversationStore.repair_dangling_decls()`——全库扫描未配对
   assistant tool_calls 声明并**落库修剪**（幂等；S190 写入守卫会提前修 replace_messages
   路径的悬挂，append 裸写路径靠本方法兜底）
2. `app.py` build_app：store 创建后立即调用（幂等，空库/干净库毫秒级 0 变更；失败仅告警不阻塞启动）
3. `scripts/repair_tool_pairs.py`：改为复用 store 方法（消除重复逻辑，手动巡检仍可用）
4. 测试：`test_repair_dangling_decls_persists_fix`——模拟旧版直接 append 悬挂数据 → 修复落库
   （新实例读取干净）→ 幂等二次 0 变更

**验证**：test_sqlite 8 全绿 + test_app 42 全绿（排除既有竞态 test_chat_stream_sse_frames）；
ruff/mypy 全绿；后端重启实测无悬挂（DB 已干净，repair 返回 0）。

## S201: 400 根因确认——「插话隔开配对」盲区（真实用户日志驱动）

**背景**：远程用户 8.21 日志（E:/Desktop/8.21.log，1683 行）实锤反复 400：
`insufficient tool messages following tool_calls message`，同一会话 d6c8f88a 连续
4+ 次，用户反馈"思考中继续发指令导致"。

**日志分析**：
1. 用户跑的是 **v4.0.8 打包版**（堆栈行号 loop.py:234/deepseek.py:282/retry.py:195
   与 v4.0.8 精确吻合）——**没有 S191 sanitize_tool_pairing 守卫**、没有 S190 写入守卫、
   没有 S200b 启动清理
2. 全日志 `工具调用` 0 次 = 纯对话会话（无工具回填问题）→ 400 只能来自**历史消息残残缺**
3. queue 接力 & steer 注入（日志 `queue 入队`/`queue→steer 注入` 实锤）——
   用户"思考中发指令"→ 队列接力/steer 把 user 消息插在「assistant tool_calls 声明」
   与「tool 结果」之间

**真正的 bug（当前代码也存在）**：`sanitize_tool_pairing` 的宽松层语义
「被 user 隔开的配对保留」与 OpenAI 严格模式冲突——**OpenAI 要求 tool_calls 声明后
必须紧跟一整组 tool 消息**，中间插 user 即 400。S190-S193 修了悬挂/孤儿，但
这个「隔开」盲区从没堵过。

**修复（S201）**：`sanitize_tool_pairing` 增加重排——声明窗口未闭合时遇到的
user/system 消息推迟到该组 tool 结果之后（保序、保内容、只调位置，幂等）。
Anthropic 适配器测试从"移除隔开"改为"重排后紧邻"（内容不丢，更好）。

**验证**：真实场景复现（声明→插话→tool）重排正确；多声明+插话正确；Anthropic
转换正确；test_messages/test_adapters/test_sqlite 全绿；core 58 全绿。

## S202: 关于页版本号 + 当天完整日志导出（用户反馈驱动）

**需求**：用户发现"关于"界面缺版本号标注（无法确认跑的打包版是否最新），
且排查时要自己找日志文件。升级排查体验。

**后端**：
- `/api/health` 增加 `version` 字段（复用 update_checker.get_local_version：
  源码读仓库 pyproject.toml，frozen 读打包打入的 pyproject.toml——真正暴露打包版版本，
  可直接确认用户是否最新版）
- 新增 `GET /api/logs/export?day=YYYY-MM-DD`：按行首时间戳过滤 anyspark.log 返回当天
  完整日志（缺省当天，最多 2000 行）；纯只读、无敏感字段

**前端**（Settings → 关于）：
- 版本号从 /api/health 实时拉取显示（`v${version}`，未知时提示）
- "导出当天完整日志"按钮 → 拉 /api/logs/export → 下载 `anyspark-log-<date>.log`
  文件 + 显示行数

**验证**：后端 health 返回 version=4.0.10；logs/export 当天 350 行；前端 tsc(-b) 通过、
vite build 通过；test_health + test_logs_export 2 测试绿。

## S203: v4.0.11 发布——版本 bump + 推送公开仓库

**版本**：4.0.10 → 4.0.11（S199 之后的新提交 S200-S202 发布）
**bump 三处**：pyproject.toml / uv.lock / build_release.sh
**本次发布内容**：
- S200/S200b：tool_calls 悬挂 400 根因（取消/插话隔开）+ 启动自动清理 + 收尾自愈
- S201：插话隔开配对盲区修复（真实用户日志驱动）
- S202：关于页版本号 + 当天完整日志导出
**验证**：test_update 8 全绿；三处版本同步一致

## S204: Gemini 适配器 array 参数补 items + type 大写枚举（真实用户报错驱动）

**背景**：远程用户报 Gemini 400：`*tools[0].function_declarations[20]..properties[patches].items:
missing field.`——Gemini functionDeclarations 校验拒绝。

**根因**：
1. `to_gemini_tool` 把参数 type 原样小写映射（"string"）——Gemini 要求大写枚举
   （STRING/INTEGER/NUMBER/BOOLEAN/ARRAY/OBJECT），小写可能触发校验器异常路径
2. type=array 的参数**必须提供 items**（元素 schema）——缺失报 `properties[xxx].items:
   missing field`。我们的内置工具无 array 参数，但用户环境的自定义工具（扩展工具/
   旧版打包）可能声明了 array——转换层必须防御

**修复**（gemini.py to_gemini_tool）：
- type 映射为 Gemini 大写枚举；未知类型退化为 STRING（保守不被拒）
- ARRAY 自动补 `items: {type: STRING}`；OBJECT 补空 properties
- parameters.type 用 OBJECT 大写

**验证**：新增 test_gemini_array_param_gets_items（array 参数必须含 items + 大写）；
test_adapters 30 全绿；ruff/mypy 全绿。anthropic/responses 用 JSON Schema 风格对小写
type 兼容，无需同样修复。

## S204b: 打包 ffi.dll 修复——PyInstaller binaries dest 语义坑（实测验证 exe 启动）

**背景**：v4.0.11 exe 启动即崩。第一轮 `import _ctypes: 找不到模块`——Anaconda 布局
下 _ctypes.pyd 依赖 ffi.dll（conda 只有 ffi-8.dll），PyInstaller 默认搜不到。
S203d 加 _conda_dll_binaries 收集后 → 变 `拒绝访问`（还是找不到）。

**二次根因**：PyInstaller 的 binaries `(src, dest)` 中 **dest 是目标目录不是文件名**——
传 `(ffi-8.dll, "ffi.dll")` 实际生成 `ffi.dll/ffi-8.dll` 嵌套，解压后根级无 ffi.dll。
**修复**：复制 ffi-8.dll 为临时 ffi.dll 同名收集（解压后根级同名）。

**验证**：archive_viewer 确认 `'ffi.dll'` 根级；解压运行 exe → health 200
（model=deepseek-v4-flash, version=4.0.11）；/api/logs/export 正常。
至此打包版（Anaconda 环境）启动链路全通。

---

## S205-S210: 项目审查打磨——地图同步/测试补全/复杂度拆分/类型安全/竞态修复

**背景**：S204b 后做了一轮全项目审查，按优先级打磨六处。

### S205: BACKEND-MAP + uml 地图同步
地图最后更新 S96，代码已到 S204——多处失同步违反 AGENTS.md「改后端必须同步
地图」纪律。补全：路由 15→20（补 routes_check/library/update）、端点 ~164→~207、
工具 47→48、app.py 601→500 行、补 S200/S201 配对修复机制记录。

### S206: 补 template 包测试
template 包此前仅 materials.py 有测试（111 行测 3 源文件，比例全项目最差）。
新增 test_patterns.py（6）+ test_plot.py（25），src:test 10:1→3:1。覆盖 PlotStore
前缀匹配/分级渲染/resolve_all、PlotGenerator 宽容解析、PlotResolver 静默失败。

### S207: 拆分 routes_chat
make_chat_router 600 行塞 14 端点（全项目最大单函数）。拆出 routes_chat_queue
（4端点）/routes_chat_stats（2）/routes_chat_aux（3），主函数 600→451 行。
router 总数 20→23，地图同步。

### S208: 前端类型安全——api 层
api/*.ts 的 `as any` 是后端返回未类型化就强转。定义 5 个 response 接口
（ChapterDetail/ChapterVersion/PlanItem/MaterialSummary/SkillItem），用 get<T>
泛型替代强转。any 总数 68→61。

### S209: 修复 test_chat_stream_sse_frames 竞态
SSE done 帧发出时图谱抽取后台任务可能未完成，直接断言实体存在会竞态失败
（改动前已复现）。采用项目已有模式（轮询 8s），3 次连跑稳定。全量 739 全绿。

### S210: 前端类型安全——组件层
延续 S208，BookDetail sessions state Record<string,any>[]→SessionData[]，
ChaptersPanel getChapters 不再 as any[]。any 61→52。

**_loop 400 行未动**：复杂性是领域复杂性的真实反映（配对完整性/死循环检测/压缩/
steering/取消/重试），配对修复等已抽成独立方法，强行拆只会破坏可读性。

---

## S233: v4.0.13 发布——版本 bump + 推送公开仓库 + EXE 打包

**版本**：4.0.12 → 4.0.13（代码 S212 已置 4.0.12 但从未发布；本次 +0.0.1）
**bump 三处**：pyproject.toml / uv.lock / build_release.sh（缺省版本 v4.0.11→v4.0.13）
**范围**：feat/shell-port 相对 public/main(S211) 领先 10 个提交（S212-S232）：
  文档收敛 / PROGRESS 拆分归档 / 意图模式 write_chapter 图谱抽取 /
  SQLite 线程安全修复 / 并发流损坏会话历史修复 / 思考模式 reasoning_content 回传 /
  章节编辑器多次保存排版丢失修复 / Anthropic thinking block 未回传修复
**打包**：`bash scripts/build_release.sh v4.0.13` → `AnySpark_Windows_x64_v4.0.13.zip`
  （PyInstaller 独立 exe，双击即用；含前端 dist + 后端，零依赖）
**推送**：`git push public feat/shell-port:main`（快进 public/main 至 S232）+ 打 tag `v4.0.13`
**验证**：frontend 构建（tsc -b + vite build）通过；exe PyInstaller 构建成功（25MB）；
  exe 启动生成 .env 模板并起服务（health 需填 API Key 后方可用）。
  ⚠️ 门禁分层判定仅查未提交改动、本发布提交已落地故跳过实检；分支现存 46 处历史 ruff
  错误（S232 等累积引入，非本次发布引入），建议后续 `ruff check --fix` 清理后再发下一版。

---

## S234: ruff --fix 清理 46 处历史 lint 错误

**背景**：S233 发布记录披露分支现存 46 处 ruff 错误（S232 等累积；门禁分层只查未提交改动故漏检）。
**处理**：`ruff check --fix` 自动修 36 处 + 手动修 10 处：
- subprocess.run 补 `check=False`（run_parity.py / run_unit.py 的 taskkill）
- 未用解包变量 `db_path` → `_`（learn_curve.py）；死代码 `tp_pred` 删除（tasks/graph.py）
- `_wait_health` 盲捕 `Exception: pass` → `except httpx.HTTPError` + 命名 logger（LOG015/S110/BLE001）
- 任务循环盲捕 `Exception` 加 `noqa: BLE001`（benchmark 故意全捕记录 FAIL，非盲错）
- E501 长行包裹：anthropic.py `_parse_content` 返回类型、test_adapters.py tool_calls 字面量
**验证**：`ruff check .` 全绿（All checks passed）；test_adapters.py 全过（exit 0）。

---

## S235: v4.0.14 发布——版本 bump 4.0.13→4.0.14 + 推送公开仓库 + EXE 打包

**版本**：4.0.13 → 4.0.14（相对 v4.0.13 仅叠加 S234 ruff 46 处历史错误清理，无功能变更）
**bump 三处**：pyproject.toml / uv.lock / build_release.sh（缺省版本 v4.0.13→v4.0.14）
**范围**：feat/shell-port 相对 v4.0.13 tag 领先 2 个提交（S234 + S234b ruff 清理）
**打包**：`bash scripts/build_release.sh v4.0.14` → 触发 CI 自动构建三平台独立 exe
  （Windows/macOS/Linux，双击/直接运行即用，零依赖）
**推送**：`git push public feat/shell-port:main`（public/main 至 S234b 干净态）+ 打 tag `v4.0.14`
**验证**：`ruff check .` 全绿（All checks passed）；仓库已无历史 lint 债务

---

## S243: AI 自主规划写入渠道（原编号 S242，撞号让位改 S243）——叙事树/计划/设定的 agent 写工具 + 叙事树按需提炼

**背景**（主人复盘哈利波特项目）：规划产物生产渠道不对称——图谱全自动、伏笔有
agent 写工具，但叙事树完全没有 agent 写渠道、计划只能标完成不能建、设定只能查证
不能登记。原生项目产物不完备，导入项目（千章存量）只能手搭面板。

**交付**（DESIGN §12.46）：
- `story_node_add`：叙事树落节点（parent 缺省接主线末尾 chosen 链，空树首节点即根；
  kind 缺省 main，chosen 缺省随 kind）——tools_plot.py `make_story_tree_implementer`
- `plan_register`：补齐计划断链（同章重登=更新且保留 done 状态）
- `setting_register`：设定入档（source=agent；与 graph_register 分工：正典规则 vs 情节事实）
- 装配：ToolContext.story_tree 新字段 + agent_factory 传参 + toolkit enable_domain 注册
- 预置 workflow 模板「叙事树提炼」：tree_trajectory（章题轨迹，抽稀封顶 500）→
  agent 树形草案（严格 JSON）→ tree_commit（落库，parent 引用失效防御链最近节点）；
  轻流程直接落库（加性可删，与图谱抽取模板同哲学）
- 前端：WorkflowPanel 画布脚本目录补 tree_trajectory/tree_commit 两函数
- 测试：test_story_tools.py 5 用例（三工具 + 模板 e2e + 查证闭环）全过

**验证**：gate --pytest（story_tools/tools_domain/workflow_api/test_app）+ tsc + vitest 全绿
**踩坑**：_call 助手 `name` 形参与工具参数 name 撞名（name= 字面漏进 kwargs）→
助手改位置限定参数（`name, /`）

---

## S246: 校园智能体比赛向——学术检测规则包 + 审稿回复模板（领域拓展=内容非机制）

**背景**（主人指令：参赛文档 + 自主补全高价值功能；实现纪律追加：优先工作流/
拓展包形式，不打补丁）。第一版曾把学术七项硬编码为第二骨架+pack 选择器，
主人指出补丁味后推翻重做——改为内容种子走既有机制。

**交付**（DESIGN §12.47，详见 docs/COMPETITION.md）：
- 学术检测规则包：七项（术语一致性/论断证据/结构完备/逻辑链条/语言规范/
  数据一致/诚信自查）作为内置内容借 S195 用户骨架通道自举（幂等 + 尊重删除 +
  恢复重新物化）；check_store.py 内置包数据与自举守卫
- check_text 与 /api/check 同源（接线补缺）：toolkit 传 merged_checks，
  此前 agent 自查看不见用户自定义检测项
- 「审稿回复」预置工作流（第 10 个模板）：逐条意见→回应→汇编回复信，
  复用 read_chapter/list_split/loop/accumulate 四原语零新机制
- list_split 通用清单切分原语（JSON 数组/逐条文本→遍历源）
- docs/COMPETITION.md：参赛能力清单/缺陷清单 D1-D7/七分钟演示脚本

**测试**：test_builtin_packs.py 4 用例（种子/幂等与删除尊重/工具合并骨架/模板 e2e）

**门禁如实记录**：ruff check 与 format --check 各 1 处失败均来自并行会话
未完成文件 library/vectors.py（向量检索 WIP，非本阶段改动，未触碰）；
本阶段相关检查全绿（mypy 226 文件/pytest 73 过/tsc/vitest）。

---

## S247: 文体 profile——写作引擎/检测骨架/学习审查按项目文体切换（DESIGN §12.48）

**背景**（缺陷 D1 修复）：小说语境固化在 prompt 层；学术/报告文本硬套小说引擎。
实现路径避开并行会话持有文件（agent_factory/toolkit/app）——genre 走工作区文件
权威（文体.txt），工具层运行时读取而非装配注入（中途切换即时生效）。

**交付**：
- genres.py：GenreProfile + fiction/academic/report 三内置 profile（fiction 逐字
  保持历史行为；学术拆解七维：研究问题/方法数据/贡献结论/论证链/结构组织/表达规范/文献使用）
- workspace.read_genre/write_genre（文体.txt）+ /api/genre GET/POST（routes_mind）
- _clean_write 人设/要求按 profile（运行时读）
- check 骨架演化：ACADEMIC_CHECKS 升为内置双骨架 + get_pack（修正 S246 种子方案
  的体裁污染缺陷——种子无法表达"按体裁选择"，实测小说检测被学术项污染）；
  /api/check 按 req.genre 或项目文体选 base，用户增删叠加；CheckRequest + genre 字段
- 学习审查：academic/report 文体拼关注点提示（fiction 行为不变）
- 测试：test_builtin_packs.py 重写 6 用例（pack 选择/路由体裁感知 e2e/写作人设切换/
  genre API/check 工具注入/审稿回复 e2e）

**待接线**：check_text 工具基准集按文体（toolkit 一行，并行会话持有中暂缓）

---

## S248: 校园模板包——拆论文/文献综述/申报书起草/多平台改写（纯数据模板）

**设计**：全部复用既有原语（book_refine_*/list_split/batch_prepare/read_chapter/
chapter_by_id/write_chapter/accumulate），零新机制；模板即数据（改指令即改行为）。
seeds.py 近千行 → 校园模板拆分至 seeds_campus.py（结构改进）。

**模板**：拆论文（学术七维→skill 草稿人工确认）/ 文献综述（逐篇要点→分主题汇编，
V1 标题轨迹口径已注明）/ 申报书起草（大纲→逐节→汇编）/ 多平台改写（一稿多平台）。
预置模板总数 14。学术润色无需新模板：批量改写 + instruction 参数。

**测试**：模板预置断言 + 多平台改写 e2e（8 用例全过）。文档：COMPETITION/BACKEND-MAP 同步。

---

## S248b: 校园场景真实模型冒烟——5 场景实测通过 + 修 list_split 围栏缺陷

**背景**：单元测试全用假模型（只证管线通），主人质问"能否真实产出示例"——
补 scripts/campus_smoke.py 用真实 DeepSeek 逐场景产出示例（临时库隔离）。

**实测结果**：persona（学术/小说产出差异显著）/ check（4 处埋瑕疵全命中+额外
14 项发现）/ review（规范英文回复信）/ multiplatform（小红书版带 emoji+话题标签）/
proposal（含合规论证完整申报书）全部通过。

**实测抓到并修复**：①list_split 漏剥 ```json 围栏（大纲 agent 输出带围栏→JSON
解析失败→按行切碎；对齐 PlotGenerator/tree_commit 先剥围栏）②冒烟取终局节点
不能 reversed（node_states 字母序非执行序）——按 merge/finish 节点名取。

---

## S250: D2/D3 学术硬能力——引用管理 + LaTeX 导出 + arXiv 连接器（文献=书库条目+cite_meta）

**架构定案（主人问"文献库与书库能否合并"→能且必须）**：不建新库，文献 =
书库条目 + cite_meta JSON 列——导入即获 RAG/reference_lookup/工作流全通道。
library_books 加列（ALTER 幂等迁移，旧库兼容）。

**D2 引用管理**：library/citation.py 纯函数格式化器（GB/T 7714-2015 顺序编码制：
>3 作者取前3加等/et al、[J][M][D][C][R][EB/OL] 标识；BibTeX：and 连接、--页码、
键=姓氏+年+题名首词、特殊字符转义）+ citation_export agent 工具（无元数据书
诚实降级「待补全」，不编造）+ POST cite-meta / GET citations 路由。
**D2 LaTeX 导出**：export_latex（ctexart 可编译骨架：section/subsection/itemize/
verbatim/转义）+ format=latex 路由。
**D3 arXiv 连接器**：library/connectors.py（Atom API，stdlib 零依赖）——
id 归一/建库书/摘要章节/cite_meta 落全；知网无公开 API 不做（诚实边界）。

**实测**：真实 arXiv 导入（Attention Is All You Need，8 作者→et al 正确、
键 vaswani2017attention）+ 24 库测试 + 12 app e2e + 42 回归全过。
campus_smoke.py 加 d2 场景。

---

## S250b: 完整示例项目真实跑通 + 修 list_split 逗号串切分缺陷

**背景**：主人再问"能否真实示例项目"——单场景冒烟已过，但拆论文/文献综述
两工作流从未吃真数据。补 campus_smoke.py project 场景：arXiv 导入×3（真实网络）→
拆论文（skill 草稿落盘）→ 文献综述（主题化综述，据标题推断标注保留）→
学术写作 → 检测（2 项发现合理）→ BibTeX/LaTeX 导出，全链路真实模型+网络通过。

**实测抓到并修复**：list_split 逗号串切分从未实现（JSON/按行两通道而已）——
multiplatform 假模型 e2e 掩盖（整串传给假模型也"通过"）。补单行含分隔符二次
切分 + 回归测试（test_list_split_comma_line）。

**启示（再次）**：假模型 e2e 只证管线拓扑，不证数据流语义——凡"参数传递"
必须真模型或显式断言 item 内容。

---

## S251: 新增功能代码自审——5 处修复（设计哲学/微 bug/健壮性）

**审核范围**：S246~S250b 全部新增（genres/seeds_campus/citation/connectors/
export_latex/list_split/冒烟脚本）。

**设计哲学问题（已修）**：
①学术七维双份文本——seeds_campus 内联拷贝与 genres.ACADEMIC 物理分离，profile
更新后模板漂移；改单一来源（模板构建时 import ACADEMIC），instruction 去重前缀。

**微 bug（已修）**：
②citation.format_note 缺字段判断绕且漏空串（嵌套 isinstance 使 title="" 不算
missing）→ 简化为 not meta.get(k)。
③fmt_gbt7714 head 重复调用 _gbt_authors 两次 → 提变量。

**健壮性（已修）**：
④import-arxiv 未捕 ET.ParseError（arXiv 非 XML 时 500 裸栈）→ 502 干净报错。
⑤export_latex 有序列表丢编号（全转 itemize）→ 有序/无序各归 enumerate/itemize，
含类型切换闭旧开新。

**自查通过项**：genres frozen dataclass 内容全自然语言/fiction 回退逐字一致；
_clean_write 整体替换人设（非行 hack）；routes_check 一行选包；store 迁移幂等；
connectors 固定域名+noqa 标注；无 YAGNI 违规。

---

## S252: 全库审核修复批①——P0 数据面（md 双写/收束导出/批量回退/人工标记绕过）

**背景**：本会话对全库做了系统代码审核（6 域并行深审 + 静态基线），本阶段起分批修复。
S252 修数据正确性类 P0 四项：

1. **routes_chapters 三处补 md 双写**（严重）：update/patch/restore 此前只写 SQLite
   镜像不回写 md 权威（create/delete 原本双写），/api/workspace/import 按文件为准会
   把旧 md 灌回——编辑器保存被静默回滚。补 workspace.write_chapter（OSError 降级
   warning 不阻断）+ API 级回归测试（test_workspace.py 四段断言 md 跟随）。
2. **play 自然收束导出丢失结局**（严重）：收束分支只 end_session 不 set_current，
   current 停在父节点，export path_to 缺最后一幕。统一 set_current(child) 后再终止；
   补回归测试 test_natural_ending_export_includes_final_scene。
3. **batch_prepare 笔误触发全书改写**（中）：传入 id 全部未匹配时静默回退全量章节。
   改为显式报错（附未解析项提示）；部分未匹配保留宽容跳过（S158 语义）但补 warning
   日志；补单测三分支断言。
4. **write_file 人工编辑标记可绕过**（中）：按原始字符串比对标记，agent 传 `./x`、
   反斜杠变体即绕过静默覆盖人工编辑（击穿 S143 不变量）。改 resolved 路径比对；
   补变体回归测试（./ 前缀/反斜杠/无标记正常写三分支）。

**测试**：涉及 5 个测试文件 41 passed；ruff 全绿。
## S253: 全库审核修复批②——多协议收尾 + 模型层健壮性

**多协议收尾（S131 遗留，审核发现三处停留在单协议时代）**：
1. resolved_api_key 跨协议 key 泄漏（严重）：此前未填 key 统一回退 DEEPSEEK_API_KEY，
   会把 DashScope key 当 x-api-key 发往 Anthropic/Gemini 端点。改只返回显式 key，
   缺省回退交适配器按协议取各自 env（openai→DEEPSEEK/anthropic→ANTHROPIC/gemini→GEMINI/
   responses→OPENAI_API_KEY）。
2. agent_factory 请求级 model_id 恒建 DeepSeekModel（严重）：指定 Claude/Gemini 配置
   会用 Chat Completions 协议打错误端点。新增 ModelProvider.build_for_config 走协议
   分发（非 provider 场景保留原路径）。
3. 新增模型 base_url 缺省恒为 DashScope（中）：registry 新增 default_base_url_for
   （按协议取各适配器 DEFAULT_BASE_URL）；顺修 temperature=0.0 被 `or` 吞掉的缺陷。

**模型层健壮性**：
4. read=None 永不超时（4 适配器）→ read=600s：S214 有意容忍长思考，但 TCP 假死
   变永久线程挂起；600s 只拦"10 分钟无字节"死连接，不误杀持续产 token 的流。
5. responses.py OpenAI 客户端 timeout=120.0 未用 _httpx_timeout（双源不一致）——
   120s 会把含长思考的正常流当超时杀掉，与 S214 设计相悖。统一。
6. anthropic message_delta usage 无条件覆盖 → 合并：帧缺 input_tokens 时保留
   message_start 已记录值（用量统计不再系统性少记）。
7. responses 推理模型 temperature=0.7 直接 400（GPT-5/o 系只收默认 1）→ 推理模式
   不发送 temperature。
8. responses 非流式 reasoning 解析失效：reasoning 是顶层 item（原在 message.content
   里找永不命中）且 summary 是 part 列表。修 _parse_output。
9. responses function_call_created 非公开流事件 → 改监听 response.output_item.added。
10. gemini 非流式同名并行 functionCall id 重复（流式 S178 已修，非流式漏修）→
    对齐 name_序号；删 thinkingConfig 重复赋值死行。
11. sqlite metadata json.loads 无容错（单行坏数据让整个会话加载崩）→ _loads_metadata。

**测试**：test_models/test_adapters 新增 5 个回归（key 泄漏/协议缺省端点/0.0 温度/
reasoning 解析/并行 id 唯一），61+58 passed；ruff 全绿。
## S254: 全库审核修复批③——agent 工具层防御

**静默改写数据类（审核重点）**：
1. mind_update 先判锁再改锁（中）：此前用过期 locked 值判锁且 set_locked 先执行，
   "解锁+改内容"同调用时解锁生效但修改被拒（副作用半套用+误导错误）。解锁后状态判断。
2. plot_update 枚举白名单校验（中）：store 会把非法值静默改默认（must→soft 等），
   主线承诺被 agent 一次笔误静默降级；工具层拒绝+回显终值。plot_resolve 的 assert
   改显式判断（-O 下被剥）。
3. story_tree_add 跨项目挂树（中）：store.get 无 book 作用域，A 项目节点可挂 B 项目
   节点下；工具层校验父节点归属。

**防挂死/防炸类**：
4. search_chapters 正则防护（中）：限长 200 + 拒绝嵌套量词（灾难性回溯无限挂起
   会话线程；Python re 无超时，同步路径只能入口拦截；粗筛有残余风险已在注释注明）。
5. execute_extension 参数注入改 repr()（中）：json.dumps 把 true/false/null 直接嵌
   Python 源码必 NameError；repr 生成合法 Python 字面量。
6. explore run_code timeout 拒 nan/inf（轻）：math.isfinite 校验回默认 10s。
7. workflow_run 每项目并发闸（轻）：同步占槽+finally 释放，防无上限孵化 daemon
   线程叠加高成本任务；create_task 失败回滚槽位。

**一致性/卫生**：
8. graph_query 关系查询 SQL 侧过滤（中）：graph 包新增 relations_among(ids)，
   known_facts 同款修复（原 limit 预取+Python 过滤，关系超限时三元组被截断/丢弃）。
9. citation_export 必填参数改 .get+诊断；check_text 加 5 万字长度闸；
   patch_chapter 补丁后复查总长（堵绕过 write_chapter 上限的通道）；
   write_file 标 execution_mode=sequential（与写类工具 S25 约定一致）。

**测试**：graph/tools 系 61+86 passed；ruff 全绿。
## S255: 全库审核修复批④——book_id 硬编码清扫 + 扫描器补盲

**逃过 S152h 扫描器的硬编码（审核发现：扫描器只查 book_id="main" 字面量形态）**：
1. toolkit 三处漏传 ctx.book_id（中）：make_data_env（扩展工具数据快照恒为 main）、
   make_mind_register/mind_manage（"记一下"落 main 心智模型）。
2. GraphExtractor 组合根绑定 main 类型集（中）：extract() 新增 types 每次调用覆盖，
   tasks.extract_chapter / routes_graph 抽取端点按章节所属项目传 types_for(book_id)；
   组合根不再绑定（回退默认五类），非 main 项目自定义类型集真正生效。
3. refine_skill_drafts 硬编码 main（中）：加 book_id 参数（bg 队列透传 task.book_id），
   routes_mind 两处入队带项目——非主项目文风偏好进入候选源。
4. signal_refine 计数按 ctx.book_id（轻，仅输出文案）。

**扫描器补盲**：scan_main_hardcode 新增位置参数形态检测（manual.list("project","main")/
types_for("main")/make_data_env(...,"main")），当前检出 0（含 app.py 那处已重构）。

**同批卫生**：
5. recorder.session_dir 会话 id 消毒（Windows 反斜杠可越出 records 根，对齐 workspace 标准）。
6. plots.open_must 的 current_order 死参数真正生效（同书多钩子按植入序升序——最久的排最前）。

**已知问题（未修，记录）**：test_wrapup_lists_open_hooks 全量跑有顺序依赖 flake
（单跑/多数组合通过；:memory: 多 store 连接隔离语义 + 特定前置文件组合触发），
本批未引入，留专项排查。

**测试**：graph/app/template 相关 49+43+89 passed；ruff 全绿；扫描门禁通过。
## S256: 全库审核修复批⑤——包层修复（workflow/review/core/align）

**workflow**：
1. validate 禁 loop body 节点带出边（中）：引擎按 body 列表顺序执行，body 节点
   出边会被 _advance 提前推进——目标被提前执行且 body 再次执行=双倍 LLM 调用；
   generator NODE_CATALOG 同步提示。已核实内置 seeds 模板无违例（自带 validate）。

**review**：
2. 评审员目录兼容 repo/wheel 双布局（中）：原单一 repo 路径在 wheel 安装后解析到
   <env>/reviewers——评审团静默空转（测试从 repo 跑永远测不到）；ANYSPARK_REVIEWERS_DIR
   环境变量可覆盖。

**core（机制纯性）**：
3. 死循环判定去 workflow_status 硬编码（中）：Agent 新增 deadloop_exempt_tools
   豁免集合（default 空），app 装配注入 {"workflow_status"}——core 回归纯机制层；
   测试改为验证注入机制+未注入时拦截照常生效。

**align**：
4. skillgen 长书骨架重编号 bug（中）：>2000 章降采样后重编 1..N，而定点精读按
   笔记引用章号映射真实章节——S114 实测书 1281 章低于阈值未暴露。行号改真实章号。
5. storytree choose 保留锚点身份（中）：锚点被选为主线时不再被改写为 main
   （对齐 docstring"锚点不受影响"承诺）。
6. 测试层反向依赖解除（中）：5 个 build_app HTTP 集成测试迁往 app/tests
   （test_align_*.py），删除无引用的 align conftest——align 可独立装包跑测；
   test_node_add_and_choose 补真实断言（原零断言）。

**测试**：core/review/workflow/align 187+ passed；ruff 全绿。
## S257: 全库审核修复批⑥——前端回归 + 伪实现转真（决策 B 对齐）

**ChatPanel 必现回归（审核 git blame 实证为 S213 重构漏删）**：
1. start 事件旧代码重复 push——每条流式回复首个 text_delta 渲染成孤儿气泡（一行删除）。
2. runWorkflow 硬编码 'main'——非 main 项目批量提议批准落错项目，改传 bookId prop。
3. 批量轮询 interval 随会话切换/卸载统一清理（batchTimersRef）——原跨会话 setMessages
   污染 + 泄漏。
4. beforeunload beacon 改用 SSE 会话内实际激活会话 id（原 prop 未回传时取消信号落空）。
5. alert×5 → showToast 统一提示体系；删 5 处无开关诊断 console.log。

**伪实现转真（决策 B「禁止模拟实现」对齐）**：
6. 章节 status（draft/final）真实落库：chapters 表 ALTER 加列（幂等迁移）+
   POST /api/chapters/{id}/status + ChapterOut 携带——前端「定稿」按钮此前
   伪造成功刷新即丢。
7. 拖拽重排真实持久化：POST /api/chapters/reorder + ChapterStore.reorder
   （0 基序号对齐 next_order 约定）+ workspace.rename_chapter（md 权威文件名
   承载序号同步——防 import 回弹）；未知 id 404。
8. 搜索结果点击无反应修复：新增 chapterFocusStore（跨面板章节定位通道），
   ChaptersPanel 订阅消费；tabStore 的 no-op openTab 不再是唯一路径。
9. SkillPanel 补 bookId prop（skill 导入落当前项目——全前端唯一依赖
   bookId='main' 默认值的调用点，清扫后其余 API 默认值均无实际调用依赖）。
10. 删 streamChat 死代码（第二套 SSE 实现，0 调用方，活路径 useSSE 唯一）。

**已知遗留（显式记录不混入本批）**：tsconfig strict 开启需修 249 处隐式 any/
空值——留专项渐进开启；tools_web 默认搜索多引擎兜底 48s 罚时属产品行为决策；
workflow 引擎递归深度/并行分支耗时均摊为设计级重构。

**测试**：tsc -b 0 错误；vitest 18 passed；后端章节系 15+27 passed；ruff 全绿。
## S260: 修章节编辑未保存静默丢失 + 细纲产出落位引导/可下载

**远程用户反馈批**：①书名改不了（S259 已修）②直接修改没有保存 ③写细纲不知落在哪/导不出。

**问题②根因（章节编辑丢稿三连）**：useAutoSave.isDirty 是 ref 不是 state——markDirty 不触发渲染，UI「● 未保存」指示永不显示；切章 selectChapter 直接覆盖编辑缓冲，30 秒自动保存间隔内切章=静默丢稿；关页无提醒。另有一处隐性竞态：flush 只写服务器不同步 chapters 数组，切走再切回显示保存前的旧文。

**修复**：isDirty 改 state（翻转才 setState 防每键重渲染）；flush 成功才清 dirty；切章/建章前 flush+同步数组；beforeunload 提醒；修正与实现矛盾的「已移除自动保存」注释（实际 30 秒自动保存一直在）。

**问题③（细纲落位）**：系统有 plan_register（大纲面板）与 write_file（笔记/ → AI文件面板）但 DEFAULT_SYSTEM 无落位引导，AI 写细纲要么淹没在对话里要么写进用户不知道的笔记目录。修复：提示词增落位约定（逐章细纲→plan_register；文档型→write_file 笔记/ 并明确告知路径）+ FilesPanel 加下载按钮（细纲/笔记可导出本地）。

## S259: 修书架改名无效 + 简介被清空双 bug

**症状**：书架「编辑项目信息」改书名保存后无效；且保存会把项目简介静默清空。

**根因（两个叠加）**：① 前端 `updateBook` 丢弃 title 只调 `PUT /api/brief`，后端也无改名端点——改的名字从未落库；② 编辑弹窗简介误绑不存在的 `description` 字段（后端 `list_books` 返回的是 `brief`），弹窗恒空，保存时把空串写进 `/api/brief` → 简介被覆盖为空。

**修复**：显示名与主键解耦——book_id（目录名）是全部 project 级数据的主键，目录改名需全链路主键迁移（实体改名专项，不混在书架编辑里）。故新增：workspace 书名元数据（`书名.txt` + `read_title`/`write_title`，无文件回退 book_id 兼容历史项目）；`PUT /api/books/{book_id}`（title 必改显示名，description=None 简介不动；404 检查不经 project_dir——其 mkdir 副作用会把不存在的项目凭空建出来）；list_books title 用 read_title。前端 updateBook 接新端点 + 弹窗简介绑 brief 字段。测试三用例（改名不动主键/简介、404、简介同步）。

## S258: 全库审核修复批⑦——总闸收尾 + 测试防网络抖动

1. 测试禁打真实 API（重要）：app/tests 新增 autouse 夹具清 DEEPSEEK/ANTHROPIC/
   GEMINI/OPENAI/EMBEDDING_API_KEY——此前 test_wrapup/test_query_reference 等未注入
   fake model 的测试静默用真实 DashScope key 打线上 API（网络抖动型 flake +
   真实计费，审核发现）；需真实 env 形态的测试用 monkeypatch.setenv 自行覆盖。
   全 app 套件 500 passed 零失败（原全量跑必有 1 个顺序依赖 flake）。
2. S214 read 超时测试更新为 600s 有界约定（S253 行为变更的配套）。
3. responses OpenAI timeout 类型标注对齐 deepseek 既有模式（httpx2 与 SDK
   类型不同源，type: ignore[arg-type]）。
4. 既有测试 15 处 mypy 错误清零（get_book None 收窄/泛型参数/注解补齐/
   build_app 占位 model 标注）——mypy packages 234 文件全绿。
5. ruff format 6 文件重排 + per-file-ignores 路径随 test_align_skillgen 迁移更新。

## S261: 移除学术校园拓展（S246-S251 簇）+ 测试防真实 API 回潮修复 + 远程同步

**背景**（主人指令）：项目回归「AI 写小说」主线，删除多余的学术校园拓展；
比较远程仓库差异并同步到最新。搁置 2.5 个月后首次开工（上次提交 2026-09-05）。

**交付**（DESIGN §12.49，§12.47/12.48 加状态标注）：
- 移除：genres.py（三文体 profile）/seeds_campus.py（拆论文/文献综述/申报书起草/
  多平台改写）/审稿回复预置模板/ACADEMIC_CHECKS+CHECK_PACKS+get_pack 双骨架/
  /api/genre GET+POST/文体.txt 读写/library citation.py+connectors.py/cite_meta
  读写/citation_export 工具/import-arxiv+cite-meta+citations 路由/export_latex+
  format=latex 分支/campus_smoke.py/COMPETITION.md/学术专属测试三文件
- 保留（通用机制）：list_split 清单切分原语（逗号串回归测试迁 test_workflow_api）、
  check_text 与 /api/check 同源合并骨架接线（回归测试迁 test_check_store）、
  S195 用户骨架增删通道
- 行为回归：写作引擎人设/要求句回到小说硬编码（与 fiction profile 逐字一致，
  存量项目零变化）；检测=单一小说骨架+用户叠加；学习审查无文体提示
- **S258 回潮修复**：清密钥 fixture 实际无效——load_dotenv 缺省 override=False
  只补缺失键，delenv 反而让 .env 重新注入真实 key；改空串占位。模型下线后
  该缺陷显形：404 + 后台 embedding 重试占写锁 → database is locked 连环失败
  （stash 对照实证：6 个失败在改动前 HEAD 同样存在，非本次删除引起）。
  test_wrapup 改注入 fake 写作模型；test_mode 改 monkeypatch 占位 key
- 数据清理（备份 data/anyspark.backup-20261117-201919.db）：3 个学术演示工作区 +
  3 本 arXiv 库书 + 5 个校园模板及其任务/节点态/孤儿消息；旧库 cite_meta 列
  保留不读写（SQLite 删列成本高且无害），新库建表无此列
- 文档：BACKEND-MAP 路由表/工具表同步（routes_workflow/routes_check/
  routes_library/citation_export 行）；uml 无学术接线无需改

**门禁**：后端层全绿（ruff check+format/mypy 224 文件/scan_main_hardcode/
pytest **798 passed**）；无前端改动，前端层按 S96 自动分层跳过。

**远程同步**（2026-11-17 实测）：SSH 22/443 均被重置（与 8 月记录相反），
https 可用——origin/public  remote 改 https 地址。fetch 后核实本地严格领先：
origin/feat/shell-port +5、origin/main +136、origin/integrate-f3 +373、
public/main +34，behind 全部 0（本地包含远程全部历史）。推送 feat/shell-port+
main（本地 main 快进到 HEAD）+integrate-f3 至 origin，HEAD 至 public/main。
