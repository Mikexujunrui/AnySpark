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
**验证**：全量门禁（ruff+mypy+pytest+tsc+eslint+vite build）绿；exe 启动 health 200
