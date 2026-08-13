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
- **当前状态（S96）**：
  - **核心功能全部完成**（S0-S75）：七阶段 + 全部补缺 + 实测驱动演进 + 特化路线 P1-P5（工作区化/领域工具化/格式管线/角色推演/代码扩展/正文检索/运行时模型）+ 架构深化 S53-S63（心智模型=会话规划器/叙事技巧生成器/C 架构/skill 注入瘦身/工作流扩展包/哲学审查）
  - **S79-S82 后端收敛**：SQLite 连接收敛 + app.py 按领域拆 router + 双层资料库（全局池↔项目池）+ 资料库写入通道补全 + 会话绑定项目/智能体作用域隔离 + 图谱 API 项目隔离（跨书保护）
  - **S83-S96 收尾加固**：约束机制 + 审计修复 + 破限提示自编辑 + 模型注册表编辑功能（S89）+ 门禁自动分层（S96）
  - **剩余（按主人路线，非缺陷）**：多模态（未来计划）/ B 真自我修复（补丁应用，按需）/ httpx2 迁移（等 starlette）/ 实体改名（S72 主键语义，前端表单待适配）
  - 测试现状：pytest 424 例全绿 + 前端 tsc/lint/build 全绿（分层门禁见 AGENTS.md）
### 并行声明区（开工必读/必写——改共享文件前先在此声明，提交后删除本行）
> ⚠️ S81 事故留痕（归属说明，勿删）：commit `f7cbec8`（S81 档位高亮修复）提交时裹挟了并行会话对 `frontend/src/components/SettingsModal.tsx` 的**未提交**模型编辑功能改动（EMPTY_MODEL_FORM / startEditModel / registerModel 改造，S88 系内容）。代码无丢失、可编译，但归属混在该 commit——相关会话如需单独追溯见 `git show f7cbec8` diff。
 > 当前无会话声明。
> 📢 [S99] 已提交完成（commit `515294a`，SSE 接力第二步）——通知 S100：useSSE.ts 的 session_tokens/nearLimit 与 routes_chat.py 的 done 帧 model 字段随本提交带走（交织无法 hunk 分离），归属见提交说明；ChatPanel.tsx 的 UsageStrip 接入已 add -p 分离留在工作区，待 S100 补交（补交前先 git diff 确认归属）
> [S82] 正在改 `routes_chat.py`（chat_stream 事件订阅区：record→reasoning、done→parts）+ `useSSE.ts` + `ChatPanel.tsx`：补工具调用卡片/思考过程/步骤进度链路（不动并行会话的 create(book_id) 两行）
> 声明格式：`> [S6x] 正在改 <文件>：<改动内容>`（多个文件逐行写）

- **候选清单（下一步，按优先级）**：
  1. **心智模型系统**（设计内降权，核心候选）：包罗万象（文风/喜好/毒点/边界）+ **渐进式披露**（索引常驻/正文按需，对齐 pi skills）——manual 是雏形，需设计分类与注入时机；含档位 L2（AI 看心智后建议档位）/L3（自然语言生成档位）
  2. **对比层回归**：S18 三任务（设定忠实/长书一致/偏好记忆）在 S32-S46 后重跑（成本 ~20min）
  3. **前端 UI**（主人明确不优先）：伏笔面板/图谱可视化/设定档/技巧/计划/批量/定点编辑/影响分析均无 UI（API 全）
  4. **设定档渐进式披露**：条目多时分段/按需注入（当前全量）
  5. **影响分析主角线过度报告优化**：核心实体与事件线区分报告（当前主角线=全影响提示）
  6. **list_events 默认 limit**：200 对超长书截断，调用方需显式传大 limit（当前用法已知）
- ~~httpx2 迁移~~ ✅（S66 完成）；~~Autopilot~~ —— 已划掉：S59 工作流（loop+gate+approval+AI 生成流程）已吸收其全部机制价值，需要"全书自动连写"时用 workflow_generate + 人工确认 + 跑循环即可，不另起包（同评审团判断逻辑）
- 纪律：每阶段开工前向主人确认；对设计的偏离/新增先确认再改 DESIGN.md

## 关键决策记录（主人拍板，见下方日期）

- **2026-08-02 决策A**：v4 作为完全全新的项目建设，**不做旧数据导入/转移**，不背沉没成本。旧系统仅作思想参考。→ 移除了 S0 数据导入脚本验收项。
- **2026-08-02 决策B**：**全部真实实现**。用 pi 同款 DeepSeek API（DashScope 端点 + `deepseek-v4-flash` 模型），禁止任何模拟/演示/降级实现。
- **2026-08-02 决策C**：连续推进模式——不中断到第一版。用本 PROGRESS.md 做跨会话台账接续。

---

## S0 地基（已完成）

**交付 commit `8ecb4f4`**
- uv workspace 骨架（`[tool.uv.workspace]` + `[tool.uv.sources]` 排坑）
- anyspark-core 内核：`loop.py`(Agent循环) / `protocol.py`(工具协议) / `events.py`(事件协议+注册钩子) / `storage.py`(存储接口+内存) / `tools.py`(echo/add)
- 门禁：ruff + ruff format + mypy(strict) + pytest 全绿（25 passed）
- 验收：最小循环"读提示→调工具→回填→输出"跑通

**踩坑记录**：
- uv 0.11 workspace 必须用 `[tool.uv.workspace]`（老式 `[workspace]` 无法 discovery 成员），且根项目依赖成员需 `[tool.uv.sources] { workspace = true }`
- ruff RUF001/002/003（Unicode 混淆）会误报中文，已 ignore
- mypy 中方法名 `list()` 会遮蔽内置 list 导致 strict 报错 → 改名 `list_conversations()`

---

## S1 核心写作（已完成 ✅）

**交付 commit**：`S1 真实模型接入` + `S1 后端闭环` + `S1 前端稿纸`

**范围落实**（DESIGN 阶段1）：真实 DeepSeek + FastAPI 后端 + SQLite 持久化 + 前端稿纸

**真实实现**（无任何模拟/降级）：
- `anyspark-app` 包：DeepSeekModel（OpenAI SDK 原生 function calling，DashScope 端点 + deepseek-v4-flash，pi 同款）
- FastAPI 后端：`/api/chat`（对话→写作闭环）、`/api/chapters`、`/api/health`；CORS + Vite 代理
- 真实写作工具：list_chapters / read_chapter / write_chapter（续写/修改带版本历史）
- SQLite 真实落盘：会话/消息 + 章节/版本历史（check_same_thread=False 供多线程）
- 前端创作台：三层空间骨架（稿纸+写作上下文占位+抽屉占位），TipTap 稿纸，Zustand 领域 store，api 唯一出入口

**门禁**：ruff + mypy + pytest(30) + tsc + eslint + vite build 全绿

**真实端到端验证**（多次）:
- DeepSeek 自主调工具写出并落盘章节（《雾都来客》雨夜侦探；《月狐》月下白狐）
- 续写闭环：329 字 → 1011 字，旧版进版本历史
- 前端 Vite 代理 → 后端 → DeepSeek → SQLite 全链路跑通

**踩坑记录**：
- `PROJECT_ROOT = parents[5]`（不是 [4]）——否则 .env/data 路径错位
- SQLite 跨线程：FastAPI sync endpoint 跑在 threadpool → 需 check_same_thread=False + 锁
- mypy namespace：src 多包需 `explicit_package_bases` + `mypy_path` 双 src；`py.typed` 每个子包
- Vite 6 默认绑 localhost(IPv6 ::1)，curl 127.0.0.1 会 HTTP 000，用 localhost 访问

---

## S2 对齐系统（已完成 ✅）

**交付 commit**：`S2 后端对齐` + `S2 后端集成+前端说明书`

**范围落实**（DESIGN 第 6 节 / T3）：anyspark-align 包 + 后端集成 + 前端说明书界面

**实现**：
- 说明书（manual）：条目模型（内容/来源/置信度/活跃度/锁定）+ SQLite + 可读渲染
- 信号采集（signals）：操作→信号（accepted/modified带delta/deleted/rejected/custom/locked）
- 提炼器（extract）：真实 DeepSeek 对话+操作→偏好条目（JSON 宽容解析+SKIP 过滤）
- 摘要器（summarize）：对话→场景记忆→项目档案（跨会话延续）
- 注入器（inject）：项目级>全局级说明书注入 + 场景记忆注入
- 后端 API：/api/manual CRUD + /api/signals；ManualInjector 接入每次写作
- 前端：ManualPanel（可读可改：编辑/新增/锁定/删除），说明书抽屉

**门禁**：ruff + mypy + pytest(47) + tsc + eslint + vite build 全绿

**真实链路验证**：
- 信号→DeepSeek 提炼（'避免血腥''克制内敛'）→说明书→注入→写作生效（AI 遵守约束）
- 后端 API 全链路：新增/锁定/删除/信号采集/注入写作

**踩坑**：
- 同毫秒时间戳导致 recent() 排序不稳定 → 改 ORDER BY rowid
- sqlite Row factory 需每个 store 单独设置

---

## S3 探索引擎（已完成 ✅）

**交付 commit**：`S3 探索引擎包` + `S3 后端API+前端探索面板`

**范围落实**（DESIGN 机制 7）：anyspark-explore 包 + 后端 API + 前端探索面板

**实现**：
- 意图理解（intent）：种子→概念卡（画面/基调/类型/种子位置）+ 关键歧义点
- 策略集（strategy）：差异化分派（维度×三来源），探索者不知自己维度避免自证偏见
- 探索者（explorers）：asyncio.gather 并行 4 路，轻量单次 LLM 调用（上下文隔离→真多样性）
- 方向卡+档案（direction）：术语标注/三来源 + 固化（已选方向+设定约束，探索不撞墙）
- 后端 API：/api/explore/intent + cards + archive
- 前端：ExplorePanel（种子→意图确认→方向卡选择→固化），WritingContext 第二层填充

**门禁**：ruff + mypy + pytest(56) + tsc + eslint + vite build 全绿

**真实链路验证**（两次）：
- 雾城侦探：意图确认（noir/潮湿阴郁+3关键问题）→4卡（复仇/赎罪/氛围/记忆碎片）
- 预言死亡的书：4卡（宿命悖论/倒影之书/尘埃与低语/循环流）三来源混合，并行17.5s≈单次

---

## S4 检测+规则（已完成 ✅）

**交付 commit**：`S4 检测网包+后端API` + `S4 前端检测面板`

**范围落实**（DESIGN 机制 8/9）：anyspark-check 包 + 后端 API + 前端检测面板

**实现**：
- 骨架：7 类硬编码检测项（一致性/动机因果/情感连贯/信息流/结构节奏/预期管理/主题连贯）
- 检测者：asyncio 并行多检测者，AI 动态生成检测项，宽容 JSON 解析
- 轻量规则编译器：用户自然语言→检测函数（禁用词/术语偏好/段落句数，中文数字+写作术语词典）
- 报告：hard/suggestion 分级，建议而非门禁，硬伤标红
- 后端：/api/check + /api/check/rule；前端：CheckPanel（审读+自定义规则）

**门禁**：ruff + mypy + pytest(69) + tsc + eslint + vite build 全绿

**真实链路验证**：孤儿→母亲设定矛盾被 6 检测者同时发现（6硬伤+1建议，含证据与可执行建议）

---

## S5 模式+资料（已完成 ✅）

**交付 commit**：`S5 模式库包+后端API` + `S5 前端资料库面板`

**范围落实**（DESIGN 机制 6/10）：anyspark-template 包 + 后端 API + 前端资料面板

**实现**：
- 模式库：模板四要素元数据（粒度/位置/功能/可变参数）+ L2 默认库 5 模板（废柴流/三幕/双线/误会揭示/氛围先行）
- 资料消化：上传→真实 LLM 摘要卡（主题/要点/设定/角色/术语）→入库原文保留；summarize() 注入省 token
- 后端：/api/templates + /api/materials CRUD；前端：MaterialsPanel（上传消化+摘要卡列表+模式库展示）

**门禁**：ruff + mypy + pytest(75) + tsc + eslint + vite build 全绿

**真实链路验证**：雾城设定 171 字 → 摘要卡（雾瘴术语/失踪七人关键设定）→ 注入 ~200 字省 token

---

## S6 收尾（已完成 ✅）

**交付 commit**：`S6 收尾`

**范围落实**（DESIGN 阶段 6）：总闸/CI/一键启动/桌面壳/PyInstaller 打包

**实现**：
- scripts/gate.py：一键总闸（ruff+mypy+pytest+tsc+eslint+build）
- .github/workflows/ci.yml：GitHub Actions 全门禁
- scripts/dev.sh：一键启动后端+前端
- anyspark-desktop：Python WebView 轻量桌面壳（后端子线程 + 前端产物）
- anyspark.spec：PyInstaller 打包配置

**验收**：总闸全绿（后端 75 tests + 前端全门禁）；桌面壳装配 23 路由 OK

---

## 🎉 第一版完成（v4.0.0 七阶段全部通过）

| 阶段 | 验收 | 状态 |
|------|------|------|
| 0 地基 | core 最小循环 + workspace | ✅ |
| 1 核心写作 | DeepSeek 真实接入 + 对话→写作→修改闭环 | ✅ |
| 2 对齐系统 | 操作→信号→说明书→注入生效 | ✅ |
| 3 探索引擎 | 种子→概念卡→方向卡→固化 | ✅ |
| 4 检测+规则 | 检测报告 + 自然语言自定义规则 | ✅ |
| 5 模式+资料 | 资料摘要卡 + 模式库 | ✅ |
| 6 收尾 | 总闸全绿 + 桌面壳 | ✅ |

**完整系统能力**：
- 写作即对话：真实 DeepSeek 原生工具调用，对话→正文→落盘→版本历史
- 多智能体探索：意图理解→并行4探索者→方向卡（三来源混合）→固化
- 对齐系统：信号采集→提炼→说明书（可读可改锁定）→注入生效
- 检测网：7 类并行审读（硬伤标红/建议）+ 用户自然语言规则编译
- 模式库 + 资料消化：模板四要素 + 上传→摘要卡→省 token 注入
- 前端创作台：稿纸（TipTap）+ 三层空间 + 对话流纸边批注（ChatThread）+ 探索/说明书/审读/资料抽屉
- 桌面壳 + CI + 一键启动

---

## 补缺阶段规划（S7+，进行中）

> 依据：AUDIT-V1 §3 未实现清单（P0-P3）。补的是 DESIGN 已明确要求但未进七阶段清单的硬编码组件/交互机制，**设计本身不变**。
> 铁律：每个阶段开工前先向主人确认；完成后更新 AUDIT-V1 对应条目状态 + 本台账。

| 阶段 | 内容 | 验收（草案） | 状态 |
|------|------|------------|------|
| S7 知识图谱 | 图谱 schema（实体/关系/时间线 + FTS）；LLM 实体抽取入库；写作时"当前时空点已知事实"检索注入；资料摘要卡图谱关联（机制 10 补齐）；检测设定冲突图谱比对（确定性校验基础） | 章节落盘后实体自动入库；写作注入当前时空点已知事实；资料卡关联图谱实体 | ✅ 完成 |
| S8 token+流式 | token 预算（精确计算）；prune/summarize 两阶段压缩；SSE 流式传输（core 事件协议→后端 SSE→前端 EventSource） | 长对话历史自动压缩不超窗；chat 流式输出前端逐字显示 | ✅ 完成 |
| S9 能动性+倾向 | 能动性协议（0-4 级：声明/解析/温度映射/反馈自动调节）；AI 倾向档案（AI 主动暴露当前倾向）；前端能动性选择器 | 写作可调档位；档位影响生成；倾向档案可读 | ✅ 完成 |
| S10 交互层+T2 收尾 | 低摩擦组件（氛围滑块/候选卡堆/改写渐变条/建议卡拖入）；方向声明（阶段 5）；一章收尾（更新图谱/一致性摘要卡/下一章衔接提示） | 写作中候选卡可拖入稿纸；一章完成自动收尾提示 | ✅ 完成 |
| S11 基建+安全+工具 | 请求级超时/重试/指数退避；幻觉检测 fake_tool/fake_write + 越界保护；工具扩展（文件读写/文档解析 txt-docx-md/多格式导出/网络搜索） | 断流自动重试；伪造工具调用被拦截；新工具可用 | ✅ 完成 |
| S12 收尾 | 总闸全绿；CI 同步；AUDIT-V1 全文复核更新；桌面壳/PyInstaller 回归 | 总闸全绿；AUDIT-V1 无 ❌ 遗留（除设计明确降权/后补项） | ✅ 完成 |
| S13 补全遗留 | 网络搜索/时序校验/氛围滑块/L3 模式库/关键点图谱 | 全部真实链路验证 | ✅ 完成 |
| S14 T7 指标 | 修改率/提问率/完成率（纯 SQL 统计现有表 + /api/stats）+ DESIGN 与决策A 对齐 | 137 测试全绿；真实数据可查 | ✅ 完成 |
| S15 拼接落地 | 增强按需装配/重试可拼接/氛围归位/前端懒加载 | 总闸全绿 | ✅ 完成 |
| S16 benchmark 单元层 | 黑盒 17 任务 + 修图谱抽取无重试缺陷 | 17/17 | ✅ 完成 |
| S17 伏笔闭环 | 注入写作/自动回收/关注度 | 真实链路回收成功 | ✅ 完成 |
| S18 benchmark 对比层 | 裸 LLM 基线三任务（诚实：短程相当） | 报告已生成 | ✅ 完成 |
| S19 人工层 | 盲测材料（匿名A/B+三档打分表） | 材料待主人打分 | ✅ 完成 |
| S20 状态演化 | 角色/地点 state 增量+历史表+注入 | 真实链路验证 | ✅ 完成 |
| S21 系统层 | 分支剧本测哲学过程指标（修改率↓/说明书累积/偏好遵从），复用 /api/stats；另修复信号→说明书提炼闭环缺口 | 真实链路 A/B 分支验证通过（A:1条说明书/B:0，破折号 4→2） | ✅ 完成 |
| **Backlog**（按需） | 仅剩 httpx2 迁移（工程性，等 starlette 原生支持再迁；多线叙事已随 S29、后台独立 worker 已随 S21c 完成划除） | | ⏳ |

---

## S49 对话 CLI（独立入口，已完成 ✅）

**背景（主人问 TUI 价值 → 判断）**：pi TUI 是编码场景壳（文件树/diff），写作要稿纸+对话，抄它=抄错壳；主人用 agent 对话驱动不需要界面。若需独立入口，轻量 CLI 比 TUI 便宜 10 倍且贴"写作即对话"。主人拍板：做 CLI。

**实现**（`server/cli_chat.py` + `anyspark-chat` console script）：流式 SSE 打字机 + 工具执行状态 ✓/✗ + Ctrl+C 取消当前轮（可续"继续"）+ conversation_id 多轮延续（~/.anyspark_cli.json）+ /quit /reset /tools；-m 单条消息模式；--base 覆盖；默认 enable_domain。

**门禁**：pytest 264；总闸 ✅。**真实链路**：写《CLI测试章》→ 流式 + write_chapter ✓。

**意义**：独立入口 = 真实使用场景放大器——撞出的 bug 是修复闭环素材（回归测试锁死防再犯）。

---

## S49b 运行记录 + 修复链（思维链保留/update/src_read，已完成 ✅）

**背景（主人两个指示）**：① 扩展工具 update + codex 只读源码；② 审计日志——完整运行日志（上下文/工具调用/思维链）是否保留，辅助修 bug + 未来训练心智模型。主人判断：思维链保留但**不注入上下文**（推理过程不是输出，注入会污染）。

**实现**：
- **思维链进 ModelOutput**（core `reasoning` 字段）+ deepseek.py 非流式/流式收 reasoning_content
- **运行记录器**（`server/recorder.py`）：core loop 发 `record` 事件（每轮完整快照：prompt 上下文 + output 含 reasoning + tool_calls + 工具结果），app 订阅落 `data/records/<conv>/`（meta.json + events.jsonl）——修 bug 完整可回放、训练心智模型素材；**reasoning 不注入**（不进 store）
- **扩展工具 update**：`PATCH /api/tools/{id}`——改后自动回 draft 重新批准
- **codex src_read**：沙箱只读 packages/（限大小防越界）——修 bug 定位/验证
- **隔离**：recorder 与 db 配对（同 workspace 逻辑）防测试污染全局

**门禁**：pytest **267**（+3：记录器含思维链不注入/update 回 draft/src_read 越界）；总闸 ✅

**真实链路**：data/records/<conv>/——meta ✓ events.jsonl：turn1 思维链完整（"我直接写30字左右的正文，然后保存为一章即可"）+ write_chapter ✓ turn2 终答 + 结果回填 ✓

**踩坑**：`_emit_record` 放异常路径引用未定义 output → UnboundLocalError；uv run 装 console script 时 exe 被旧进程占用（taskkill //F //T）

---

## S48g 正文检索 + 扩展工具注册表（人工批准，已完成 ✅）

**背景（主人两个问题）**：① 编码系统能否给自己写扩展/修 bug/加工具——诚实答：S48d 只是执行器不能；正确形态是"工具=数据"注册表。② 长书正文定位——图谱是结构化事实检索，正文定位（意象/短语/一致性）需要新工具。

**实现**：
- **search_chapters**（enable_domain 内置）：全书关键词定位+计数+上下文片段
- **tools_extensions 扩展注册表**：工具=数据（SQLite），生命周期 draft→pending→active（**人工批准才注入 Agent 工具集**，无需重启生效）；执行复用 codex 沙箱（白名单+ws_* 数据环境+超时）双保险
- **主人设计：不做全自动**（工具进工具集后模型每轮可见，错误/幻觉代码污染主链路 S32 实证）；人工批准=低频低成本且符合用户主权哲学
- register_tool agent 工具：Agent 写代码给自己加工具（提交待审）；API：GET/POST /api/tools、approve/disable/delete

**门禁**：pytest 261（+6）；总闸 ✅

---

## S48h search_chapters 增强 + read_context（正文检索实用化，已完成 ✅）

**背景（主人实测修正）**：S48g 的 search_chapters 是纯字面匹配——否定/比喻/指代误伤、片段过长浪费。主人拍板：片段默认 20 字（不幻想）、看情况可调、支持模糊匹配、加"看上下段落"能力。

**实现**：
- **search_chapters 增强**：`fragment` 参数（上下文宽度，默认 20，0=只要统计）；`exclude` **句级排除**（命中所在分句含排除词才算，逗号/句号等切分——防短句互相污染）；`regex` 正则模糊匹配（`怀表(盖|链)`）；描述写明"字面命中需判断，选独特短语"
- **read_context**（新工具）：锚点定位读某章前后 N 段（before/after 上限 5，段落=空行分隔）——检索定位→锚点看段落→必要时读全文三步法，不读全文省 token

**门禁**：pytest **264**（+3：exclude/fragment、regex、read_context）；总闸 ✅

**真实链路**：DeepSeek 自主调 search_chapters 搜"雾"→ 17 章 98 次（真实 22 章主库）——意象级正文定位兑现（图谱做不到）

**踩坑**：heredoc 转义导致 `\n` 变真实换行（语法错误）——必须用 edit 工具；exclude 首次用片段级判断，短句内两命中互相污染 → 改句级判断

---

## S48f codex 只读数据环境（P4/A：真实计算数据/自定义统计，已完成 ✅）

**背景（主人评估后拍板）**：S48d 的 run_code 是"有而不常用"——沙箱碰不到数据（不能读文件/库），统计只能靠代码内置数据；主人要求"小说需要真实计算数据，或通过各种方式自定义统计"。

**实现**（`codex.py` 加 `make_data_env`，注入 ws_* 只读快照函数）：
- `ws_chapters`（全书章节全文）/ `ws_entities`/`ws_relations`/`ws_events`（图谱快照）/ `ws_read`（项目内受限只读：防越界+限 200KB）/ `ws_uploads`（上传列表）
- run_code 加 data_env 参数（命名空间注入）；/api/codex/run 与 run_code 工具都带数据环境
- 安全：只读不可写；路径限制项目目录内；超时兜底；数据进沙箱内存不占模型 token
- 文档 docstring 明确：数据快照管道，沙箱不接触文件系统原始能力

**门禁**：pytest **255**（+2：数据环境统计/ws_read 越界守卫）；总闸 ✅

**真实链路验证（关键）**：全书真实统计——23 章/23451 字 ✓ 高频词 TOP5（老头说/他说/陈渡说/沈青山/陈远山）✓ 实体类型分布（地点25/角色21/物件45/设定5）✓——run_code 从"玩具"变"真能处理工作区数据的分析工具"

---

## S48e 角色推演（P4：低成本多探索 + 选优，已完成 ✅）

**背景（主人拍板设计）**：主人指示"复用 pi 两个智能体挂载包中正确的那个"——结论是 **pi-multi-agent**（room_compare 模式：N 策略×隔离→对比推荐）；pi-subagents 是通用任务委派（无角色概念）不适用。主人设计：**低成本多探索，最后选择最好的作为参考**。

**实现**（`explore/roleplay.py` 新文件 + /api/role/card、/api/role/play + role_play 工具）：
- **资产**：角色卡（卡片/角色卡-{name}.md）+ 图谱实体 state 自动拼接
- **多探索**：4 路隔离并行（复用 explore asyncio.gather + 上下文隔离），策略=最可能/最戏剧化/最反常/最克制
- **选优**：LLM 判别器（符合角色设定+场景张力）→ best + 备选
- **作为参考**：不直接写正文；agent 工具 `role_play`（enable_domain）写作时可自主调用

**门禁**：pytest **253**（+5：策略集/多路+选优/判别解析/API+图谱兜底/空候选）；总闸 ✅

**真实链路验证（关键）**：角色卡（陈渡）+ 图谱 state（刚得知顾欣桐是目击者）→ 4 路推演（可能/戏剧/反常/克制各不相同）→ 判别选"最可能反应"（理由：契合沉默寡言性格，动作细密）→ **DeepSeek 写作时自主调 role_play，正文"直接取自最佳推演"（怀表转三圈动作细节来自推演）**——推演→参考→正文闭环 ✓

**已知**：v4-pro 推理模型 5 次调用（4 路+判别）实测 ~98s（flash 更快；低成本=轻量上下文+并行，非快模型）

**踩坑**：测试 model 关键词须匹配 instruction 文本（prompt 只含 instruction 不含策略名）；heredoc 转义导致 f-string 真实换行——用 edit 工具修复

---

## S48d 代码扩展 anyspark-codex（P5：沙箱 run_code，已完成 ✅）

**背景（主人路线 P5）**：DESIGN 机制 8 预留的"编码扩展包"落地——固定工具无法实现的东西（自定义处理）+ 自我修复（验证代码逻辑）。

**实现**（`server/codex.py` 新文件 + /api/codex/run + run_code 工具）：
- **沙箱**：白名单受限命名空间（math/re/json/random/itertools/collections/statistics，无 open/__import__ 逃逸——`__import__` 从 builtins 注入受限版，import 语句走 builtins 是踩坑点）；timeout 硬上限（默认 10s ≤60s，线程 join 超时终止）；调用即烧
- **开关**：`enable_codex` 默认关（安全按需点亮）；run_code 工具描述明确"不可用于读写文件或访问网络"
- **自我修复边界**：run_code 只验证代码；改源码=Agent 出补丁→用户确认→系统应用（沙箱不直接改）

**门禁**：pytest **248**（+6：基础/白名单/拦截/错误超时/工具/API+开关）；总闸 ✅

**真实链路验证**：codex API 统计字数分布 ✓；import shutil 拦截 ✓；open 拦截 ✓；**DeepSeek 自主调 run_code 算 1..100 平方和=338350 正确** ✓

**踩坑**：exec 里 `import` 语句从 `__builtins__.__import__` 找（不是 globals[__import__]）——必须把受限 __import__ 注入 builtins 副本，否则所有 import 报 "__import__ not found"

---

## S48c 输入消化管线（P3：原始区→格式化区，已完成 ✅）

**背景（主人路线 P3 + 拍板）**：原始区存档、格式化区操作。多模态（图片理解/OCR）不做放未来；图片只做上传存档+md 引用+导出携带（EPUB）。

**实现**（`server/pipeline.py` + `server/export.py` 新文件 + /api/ingest、/api/export/book + ingest_document 工具）：
- **零依赖提取**：txt/md 直读 / docx zipfile / pdf zlib 轻量（FlateDecode 抽 Tj/TJ 文本，扫描件提示 OCR 放未来）
- **规则拆章**：第X章/Chapter N 标题正则切分；无标题整篇一章
- **摘要卡**：短文本/资料 → MaterialDigestor → 卡片/摘要卡-*.md + materials SQLite（图谱关联兼容）
- **判别**：mode auto/chapters/card（自动：多章→拆章；单章短文本→卡片）
- **EPUB 导出**：零依赖 zipfile（xhtml+OPF+nav+container）；md 图片引用（相对章节目录 `../上传/x.png`）收集进 images/ 并改写 src；txt/md 全书导出同端点
- **agent 工具** `ingest_document`（enable_domain）：用户上传后可自主消化

**门禁**：pytest **242**（+7：txt/docx/pdf 提取/中英拆章/回退/图片引用/ingest 链路/EPUB 携图）；总闸 ✅

**真实链路验证**：docx 三章原稿上传 → ingest 拆 3 章（雾城来客/钟楼/怀表）落文件+库 ✓；短设定 → 摘要卡《雾城传说》✓；章节 md 引用封面图 → EPUB 导出携带 `OEBPS/images/*.png` ✓

**踩坑**：md 图片引用是相对**章节目录**（`../上传/x.png`）——export 的 image_dir 须传 chapters_dir 而非 project_dir（语义错位导致收集失败）

---

## S48b 领域能力工具化（P2：写作 Agent 自主闭环，已完成 ✅）

**背景（主人路线 P2）**：图谱/设定/伏笔/计划此前是 HTTP API（人驱动），写作 Agent 看不到——补齐为 agent 可自主调用的工具，小说特化闭环成立。

**实现**（`server/tools_domain.py` 新文件 + ChatRequest `enable_domain` 默认开）：
- `graph_query`：图谱查证（实体含 state/关系，模糊匹配别名；limit 裁剪防 token 爆炸）
- `plot_register`/`plot_list`：登记伏笔（must/soft 分级）+ 看开放承诺（must ★ + 开放章数，soft 只汇总数量——S31 设计）
- `plan_list`/`plan_mark_done`：看计划（当前+后续）+ 标记完成推进
- `read_setting`：查设定档正典（人物卡/能力体系/规则，关键词/列出全部）
- **边界**：只读/轻量登记，无删除修改权限（内容裁决权在用户/API）；自然语言 IO；`enable_domain` 默认开，`enable_extras`（查资料/自查）维持默认关

**门禁**：pytest **235**（+5：图谱查证/伏笔登记列表/计划推进/设定查证/开关探测）；总闸 ✅

**真实链路验证（关键）**：预置设定档+计划+must 伏笔 → 真实 DeepSeek 写《第一章 雾渡》**自主调用**：plan_list→plot_list→list_chapters→read_setting→graph_query→write_chapter→**plot_register×3**（新埋 3 个伏笔：画像秘密/守夜人失踪/红绳旧俗）→plan_mark_done——查证→写作→埋钩子→推进计划**全闭环**；835 字落库+落文件

---

## S48 工作区化：每项目一路径（小说特化版 pi 第一步，已完成 ✅）

**背景（主人战略）**：把 AnySpark 做成"小说特化版 pi"——舍弃通用能力（代码/媒体/TUI），增加小说必须工具（已有图谱/对齐/检测/设定/伏笔/计划），保留核心哲学（智能体驱动/机制硬编码内容自然语言/模型无关/极简）。第一步=形态变革：每项目一路径，章节 md 文件为操作主场。

**实现**（`server/workspace.py` 新文件 + tools_writing 双写 + app.py 端点）：
- **Workspace**（每项目一路径）：上传/（原始存档，只读不碰）、章节/（md 正文权威，文件名 `{order:03d}-{title}.md`）、卡片/（可读产物）
- **双写**：write_chapter/patch_chapter 写 md 文件（权威）+ SQLite chapters 表（镜像）——图谱抽取/检测/伏笔回收/影响分析等既有管线**零改动**（读库镜像）
- **import 单向同步**：`POST /api/workspace/import` 扫描章节 md → 入库（内容变化才写版本历史）——人工直接编辑 md 后调用
- **上传存档**：`POST /api/upload`（base64 JSON 零新依赖）→ 上传区；`GET /api/workspace` 结构总览
- **隔离**：build_app 的 workspace 默认与 db 配对（默认 db→data/workspace；临时 db→db 同目录；:memory:→临时目录）——防测试污染全局（实测抓到的坑：真实模型测试写《第一章》双写到全局工作区）
- **Token/效率**：注入（token 大头）只依赖状态库；md 化买的是 agent 文件本能 + 人工可编辑 + git 友好（主人拍板：不搞 front-matter/卡片双轨/隐藏目录/原件复制）

**门禁**：ruff + mypy + pytest **230**（+7：结构/文件名/读写/上传卡片/双写往返/patch 双写/API+import）+ 前端全绿

**真实链路验证**：上传设定.txt → 真实 DeepSeek 写《测试章W》落 md 文件 → 人工改写 md → import 同步（changed=1，库镜像更新）→ 结构总览正确

**遗留（后续阶段，按主人路线）**：P2 领域能力工具化（图谱/设定/伏笔/计划/检测全部 agent 可自主调用）；P3 格式管线（docx/pdf/md→章节 md 的输入消化，原始区→格式化区）；P4 人格推演；P5 代码扩展 anyspark-codex（自我修复，DESIGN 机制 8 预留）；P6 前端壳

---

## S47 运行时模型配置 + 思考强度（已完成 ✅）

**背景（主人需求）**：此前模型固定 DeepSeek（`.env` 启动时静态配置 DEEPSEEK_*），无运行时切换供应商/模型、无思考强度选择。本次补齐：运行时模型注册表（可增删改/切换激活）+ 请求级 model_id/thinking 覆盖 + 前端模型选择器。

**实现**（`packages/app/src/anyspark/models/registry.py` 新文件 + deepseek.py 扩展 + app.py 装配/API + 前端）：
- **ModelRegistry**：SQLite 持久化 `model_configs`（供应商端点/模型名/api_key/窗口/温度/思考强度），空库从 `.env` 播种默认 DeepSeek——升级即用、旧行为不变；CRUD + 激活（仅一个 is_active，删除保底回落）
- **ModelProvider**：实现 core Model 协议，**委托给当前激活配置**——切换后所有持有它的组件（Agent/图谱抽取/检测/探索/后台任务）即时跟随，无需重启/改组件；实例按 (config, temp, thinking) 组合缓存
- **思考强度**：DeepSeek v4 系列默认开思考——`reasoning_effort`（OpenAI 标准参数顶层直传，low/medium/high/xhigh/max）；`off` 用 `extra_body={"enable_thinking": False}` 显式关闭（非标准参数）；思考内容经 `reasoning_content` 返回
- **请求级覆盖**：ChatRequest 加 `model_id`（指定模型，缺省用激活）+ `thinking`（覆盖模型默认强度）；`_make_agent` 解析：显式 model_id > 当前激活配置（+档位温度）> 共享模型
- **API**：GET/POST /api/models、DELETE /api/models/{id}、POST /api/models/{id}/activate（切窗口不同模型时日志提示预算重启生效）；health 的 model 字段跟随激活
- **前端**：ModelPicker（模型下拉 + 思考强度下拉，WritingContext 第二层），随 chat 请求带 model_id/thinking
- **顺带修复**：全局异常处理器（未捕获异常打 ERROR 日志，此前 try 外异常静默 500 零日志）；`AgencyStore._migrate_legacy_state`（S35 遗留：agency_state 旧库缺 level_id 列，主库 500——补 ALTER + 旧数字档位迁移 default-N）；`GraphStore` 补 weight 列迁移（S37 声称做了实际漏写）

**门禁**：ruff + mypy + pytest **223**（+14：registry 种子/CRUD/保底/activate、thinking 参数映射、Provider 跟随/覆盖、API 端点）+ 前端 tsc/eslint/build 全绿；总闸 ✅

**真实链路验证**（anyspark_api 实测，真实 DeepSeek）：
- `model_id=deepseek-v4-pro + thinking=max` → 写《测试章A》落盘 ✓（请求级指定+思考强度）
- `model_id=default + thinking=off` → flash 关思考 ✓
- 缺省（激活=v4-pro）→ 自动用 v4-pro ✓；health 跟随 `deepseek-v4-pro` ✓
- 裸调确认：v4-pro + reasoning_effort=max 返回 reasoning_content（思考真实开启）

**遗留**：token 预算窗口按启动时激活模型计算（切不同窗口模型需重启生效，activate 已日志提示）；非 DeepSeek 兼容供应商需新适配器（YAGNI 不预建）；思考内容（reasoning_content）当前不展示给用户（仅影响生成）

---

## S7 知识图谱（已完成 ✅）

**交付 commit**：`62246b1`

**范围落实**（DESIGN §8 数据设计 3/7 + 模型局限弥补）：anyspark-graph 包 + 后端接线 + 资料关联 + 校验证据

**实现**：
- 新包 `packages/graph`：实体（角色/地点/事件/物件/设定）/ 关系 / 时间线事件 + FTS5 trigram 派生索引（≥3 字子串，2 字 LIKE 回退）
- 幂等落库：实体按名合并（别名并集/章节范围累计）、关系三元组去重、事件按章节替换；引用完整性（关系/事件引用的缺失名字自动补建占位实体）
- GraphExtractor：真实 DeepSeek 章节抽取（已有实体防重复/宽容 JSON 解析/非法类型映射"设定"）
- GraphInjector：当前时空点已知事实注入（写作时拼进系统提示，复刻对齐注入模式）
- GraphVerifier：确定性校验证据——文本涉及的已知实体/关系，接入 `/api/check` 返回 `graph_evidence`（检测设定冲突比对基础）
- 后端：write_chapter 落盘后 BackgroundTasks 自动抽取（失败只记日志不阻断写作）；`/api/graph/{entities,relations,events,context,extract}` 路由
- 机制 10 补齐：材料摘要卡角色/设定/术语 → 图谱实体关联（`MaterialCard.graph_entities`，旧库 ALTER 兼容）

**门禁**：ruff + mypy 全绿；pytest **94**（新增 16：store 幂等/检索/抽取解析/注入/校验证据/API 集成）

**真实链路验证**（`scripts/graph_smoke.py`）：雾城章节 8 实体（含"沈青山 身份不明"正确识别未展开信息）/ 4 关系 / 4 事件抽取入库；重复 ingest 幂等；注入块渲染完整；FTS 检索三词全命中；证据比对正确

**遗留**（非本阶段）：完整确定性校验规则（时间线顺序/伏笔匹配）；关键点图谱（T2 阶段 3，作品级规划，设计标注可选）——留 S10+

### S7 补充：智能体接入层 + 记录基础设施（commit `3f021d5`）
- **pi-anyspark** pi package（`E:\Desktop\pi\pi-main\packages\pi-anyspark\`，已注册 settings.json）：4 工具——`anyspark_server`（生命周期）/ `anyspark_api`（任意端点+链路记录）/ `anyspark_gate`（总闸）/ `anyspark_state`（状态快照）
- **记录基础设施** `data/dev/`：`runs/<时间戳>_<标签>/`（request/response/summary）、`gate/`、`state/`、`server.pid`
- **接入说明**：`docs/DEV-AGENT.md`（工具清单/推荐测试链路/踩坑：图谱抽取后台异步需等 15-30s）
- **验证**：真实链路全通——chat 写《第一章 雨夜》400 字正文（4 工具调用）→ 后台抽取 10 实体/7 关系/2 事件 → 注入块 584 字 → 检测带 graph_evidence；记录文件正确落盘

---

## S8-S12 补缺（已完成 ✅）

| 阶段 | 交付 commit | 核心交付 | 验证 |
|------|------------|---------|------|
| S8 token+流式 | `8235caa` | core 可选 context_compressor（零依赖）；TokenBudget（tiktoken+prune/summarize 两阶段）；DeepSeekModel stream+on_delta；/api/chat/stream SSE（事件协议→帧）；前端 streamChat 打字机 | 21 帧逐字流式，拼接与完整事件一致；压缩降级链完整 |
| S9 能动性+倾向 | `d47df60` | align/agency.py（五级协议/温度映射/反馈调节/声明解析）；align/bias.py（倾向档案）；/api/agency、/api/bias；AgencyPicker | 档位 CRUD、只听写档克制输出、接受信号 0→1 |
| S10 交互层 | `f0ccd9f` | /api/chat/{direction,candidates,rewrite} + /api/chapters/{id}/wrapup；InteractionTools 面板 + insertBus 拖入稿纸 | 候选卡 3 风格并行 9s≈单次；bold 改写重构；收尾含下章建议 |
| S11 基建+安全 | `866dd66` | retry 指数退避；DeepSeekModel timeout+重试；沙箱文件工具（越界/超长/docz 解析）；fake_write 落盘自校验；导出 RFC5987 中文名 | DeepSeek 自主沙箱落盘；导出含中文文件名 |
| S12 收尾 | 本文档 | gate.py 补 graph 包；CI 通配已覆盖；AUDIT-V1 复核；桌面壳 32 路由 | 总闸全绿（pytest 123） |

**剩余缺口**（设计明确降权/后补，非缺失）：~~关键点图谱~~ ✅ ~~确定性校验完整规则~~ ✅ ~~网络搜索~~ ✅ ~~L3 模式库~~ ✅ ——S13 已全部补齐，见下方；仅增强包（评审团/Autopilot）与场景拼图板画布仍按设计降权

---

## S13 补全遗留（已完成 ✅）

**交付 commit**：`补全后提交`

- **网络搜索工具** `search_web`（参考 pi-web-toolkit 搜索包思想）：360 主引擎 + Bing 兜底 + UA 伪装 + 正则解析（data-mdurl/ck跳转解真实URL），零依赖 urllib；注册进写作 Agent，DeepSeek 可自主调用
- **时序校验**（确定性规则）：`GraphVerifier.check_temporal`——文本提及的实体若在图谱中首现于更晚章节 → "时空倒置"警告；接入 `/api/check?chapter_order=`
- **氛围滑块**（机制 4 补齐）：后端 `mood` 注入（紧张/温暖/舒缓/压抑 0-100）+ 前端 MoodSliders，随 chat 请求注入系统提示
- **L3 外部模式库**（机制 6）：`ExternalLibrary`（SQLite）+ POST /api/templates/import，与 L2 合并供探索
- **关键点图谱**（T2 阶段 3）：`PlotStore` + `PlotGenerator`（LLM 生成草案）+ /api/plot CRUD + 状态流转（open/resolved）
- **门禁**：pytest **131**（新增 8：搜索解析/时序校验/L3 导入/plot/氛围）；总闸全绿
- **真实验证**：DeepSeek 自主 search_web 考据；L3 导入 6 模板；关键点图谱 7 项（含自动补全"档案被篡改"悬疑设定）

**踩坑**：Pydantic 模型定义在 build_app 函数内会 ForwardRef 解析失败（须模块级）；PlotGenerator 须在 model 初始化后装配

---

## S15 拼接哲学落地（已完成 ✅）

**交付 commit**：`S15 增强按需装配 + 重试可拼接`

**背景**：设计哲学要求"极简可拓展的拼接方式"（你要什么再装什么、机制硬编码内容自然语言、core 极简）。架构骨架（8 包单向依赖）本就符合，但组合根里**两处增强无条件挂进主链路、两处基础设施没做成可拼接组件**。本次全部修正：

**实现（C1-C6）**：
- **C1 搜索按需注册**：`enable_search: bool = False`（默认关）——写作 Agent 不再无条件背 search_web，需要考据时点亮（机制 7 轻量优先）
- **C2 图谱抽取开关**：`extract_graph: bool = True`（默认开保持现状）——可关省 token，手动 /api/graph/extract 兜底
- **C3 氛围滑块归位**：`_mood_block`/MOOD_DIMS 从组合根挪进 `align/mood.py`（B 类交互载体与 agency/bias 同包）
- **C4 重试可拼接**：`core/retry.py` 新增 `RetryingModel` 组合包装（任何 Model 协议模型可套，`.inner` 解包透明）；DeepSeekModel 不再内嵌 retry（只做单次调用+timeout）；server/retry.py 降为 re-export 兼容旧调用；build_app 装配 `RetryingModel(DeepSeekModel())`
- **C5 注入细粒度开关**：`skip_inject: list[str]`（跳过 manual/graph/agency/bias/mood 任意子集）——"只关某项注入"成为可能
- **C6 前端按需加载**：说明书/审读/资料三抽屉 React.lazy + Suspense（不打开不下载；独立 chunk 已生效，主 bundle 剥离 3 面板）

**门禁**：ruff + mypy + pytest **146**（+9：core retry 4 + 开关 5）全绿；前端 tsc/eslint/build 全绿

**同步修订**：`docs/DESIGN.md`——A 类硬编码重试组件化说明 / 模型局限表（搜索按需、重试组合包装）/ 机制 7 约束 2（写作 Agent 默认不带搜索）/ §4 核心原则新增"增强按需装配"段 / 机制 4 氛围归属 align.mood；`docs/AUDIT-V1.md` 同步

---

## S16 benchmark 单元层（已完成 ✅）

**交付 commit**：`S16 benchmark 单元层`

**背景**：主人指示 benchmark 作为**半独立子项目**（不耦合、不入库、客观指标+人工评价共存）。定位：单元层（机制能力）/系统层（哲学过程指标）/对比层（vs 裸 LLM）/人工层（三档粗筛+成对盲测）。

**实现（benchmarks/ 子项目，代码入库、产物不入库）**：
- **黑盒铁律**：只走 HTTP API，不 import 任何 anyspark 内部模块；独立 pyproject（httpx+PyYAML）；`--spawn` 自动起隔离后端（`cli --db` 新参数）
- **评测素材**：哈利波特与魔法石（人文社译本）前三章——独立性（避自产自测偏差）+可核验性（公认答案）；gold 手工标注（实体/关系/事件/预埋冲突/记忆核对点/时序测试），本地不入库
- **17 个任务**：图谱抽取 F1/幂等/注入块/时序校验、检测网冲突发现率、规则编译器、说明书载体、信号采集、探索（意图/多样性/固化）、能动性（载体/真实生效）、长书记忆保持、SSE 帧协议、资料摘要卡/图谱关联、关键点图谱
- **报告**：report/unit-<时间戳>.md，每任务 PASS/FAIL + 数值指标

**Benchmark 直接发现并修复真实缺陷（价值证明）**：
- GraphExtractor 对模型截断/非法 JSON 输出**静默返回空、无重试**（宽容解析承诺的漏洞）→ 偶发抽取 0 实体（约 50% 概率）→ extract() 解析空结果时重试一次，修复后 3/3 次非空
- 后端 cli 增加 `--db` 参数（隔离实例，benchmark 不污染主库）

**首轮成绩**：12/17 → 修复后 **17/17**（T1 图谱 F1 0.59-0.71；T5 时序 3/3 检出零误报；T13 档位 0/4 相似度 1.0 vs 0.03；T15 记忆保持率 0.67-1.0）

**踩坑**：httpx 默认走 Windows 系统代理导致 127.0.0.1 被拦 502（trust_env=False）；uv run 子进程继承 VIRTUAL_ENV=benchmarks\.venv 干扰后端环境（清 env）；taskkill /T 杀进程树防孤儿；gold 素材 OCR 噪音 → 归一化双向包含匹配。

---

## S17 伏笔闭环补缺（已完成 ✅）

**交付 commit**：`S17 伏笔闭环`

**背景**：S16 审计发现伏笔（PlotPoint）"存而不用"——DESIGN 承诺的注入/自动回收/对齐标注三项基本未落地。本次补齐（前端仍搁置，用 anyspark_api 实测）。

**实现**：
- **注入（最大断裂修复）**：`_make_agent` 注入链新增 plot 块（`plots.render("main")`，skip_inject 支持 "plot"）——写作时 AI 知道哪些伏笔还开着/刚回收；render 升级：open 全注入、resolved 只列最近 3 条、attention=ignore 不注入
- **自动回收**：`PlotResolver`（半硬编码）——章节落盘后台任务里 LLM 判断本章揭开哪些 open 伏笔 → 内容双向包含匹配防误伤 → status=resolved + chapter_ref 落章；失败静默不阻断写作；ignore 条目不参与回收
- **对齐标注**：PlotPoint 加 `attention`（care/ignore）；PATCH /api/plot/{id} 支持 status+attention；旧库 ALTER 兼容

**门禁**：ruff + mypy + pytest **148**（+2：自动回收匹配/ignore 不回收）全绿

**真实链路验证**（anyspark_api）：
- 图谱生成 7 项（含伏笔"怀表背面刻有一串数字"）→ PATCH 标记 ignore → chat 写《第三章 怀表》（AI 回复主动提到"呼应关键点图谱中怀表密码的伏笔"=注入生效）→ 后台自动回收日志 `伏笔自动回收: 《第三章 怀表》 怀表背面刻有一串数字` → 状态 ✓ resolved、章节=第三章 怀表

**踩坑**：FastAPI background_tasks 与请求**共享线程池**——LLM 慢调用（15-40s）导致后台任务**延迟排队执行**（S7 既存行为，非 S17 引入）；验证时需等 60s+。已记录，后续若需可改独立 worker。

---

## S18 benchmark 对比层（已完成 ✅）

**交付 commit**：`S18 对比层`

**背景**：项目第一命题"AnySpark 比裸 LLM 强"从未有数据。本次建立对比层：同一任务 × 同一模型 × 同输入，客观指标 + LLM 裁判（同模型双方公平）。

**实现（benchmarks/compare/）**：
- `baseline.py`：裸 LLM 客户端（httpx 直调 DashScope，零 anyspark 依赖，从主项目 .env 读 key）
- `tasks.py`：三长程任务——A 设定忠实度（哈利波特设定续写 4 章）/ B 长书一致性（原创种子 5 章）/ C 偏好跨轮记忆（禁破折号，第 2 章不重复偏好，测记忆而非指令）
- `score.py`：token 客观计数；设定违规/名字漂移用 LLM 裁判（temperature=0.2 稳定）
- `run_compare.py`：spawn 隔离后端 + 三任务 + 对比报告（含正文摘录供人工复核）

**首轮结果（诚实呈现，不夸大）**：
| 任务 | 裸 LLM | AnySpark |
|---|---|---|
| A 设定忠实度 | 0 违规 / 622 tok | 0 违规 / 1473 tok |
| B 长书一致性(5章) | 0 漂移 / 2531 tok | 0 漂移 / 4326 tok |
| C 偏好跨轮记忆 | 0 次 / 725 tok | 2 次 / 817 tok |
- **短/中程（≤5 章）质量相当，裸 LLM 便宜 1.7-2.4x**——系统开销（Agent 循环+后台抽取+注入）真实存在
- AnySpark 差异价值：长书（>10 章图谱记忆）/ 多轮对齐 / 可观测性（能动性【AI补充】标注裸 LLM 没有）
- C 暴露对齐强度不足：说明书条目在系统提示末尾，长文本中偶尔突破（2/约800字）

**踩坑**：_anyspark_write 需模糊匹配 title + AI 不落盘时后备正文（真模型波动）；LLM 裁判必须 temperature 低；长任务 3 个 ~20 分钟（成本实录）

---

## S19 人工层（已完成 ✅）

**交付 commit**：`S19 人工层`

**实现（benchmarks/human/）**：
- `generate_blind.py`：跑对比层三任务 → 每任务两篇终稿**随机匿名为 A/B**（映射锁 `_mapping.json`）→ 输出打分表 score_card.md
- 打分三步：三档粗筛（🗑垃圾/📖能读/✨不错）+ 二选一（不许平局）+ 一句话理由
- 盲测材料：`benchmarks/report/human/20260804-102022/`（A/B/C 三组完整终稿 + 打分表），**主人随时可读稿打分**

**设计依据**：AI 文章普遍垃圾→判别空间大→单评判者足够（主人确认）；盲测防自证偏见。

## S20 角色/地点状态演化（已完成 ✅）

**交付 commit**：`S20 状态演化`

**背景**：老愿景（v3 时空大图）最大差异化内核="角色随时间自然变化"，v4 此前缺失。用 v4 轻量方式补回（不搞 v3 的快照系统）。

**实现**：
- `graph_entities.state`：实体截至最新章节的状态（自然语言增量拼接"旧；本章变化"）；`entity_states` 演化历史表（每章快照）
- 抽取：EXTRACT_PROMPT 新增独立 `states` 字段——已有实体不重复抽取（规则5）但**状态变化单独更新**（防主角永不演化的设计冲突）；StateUpdate 解析
- `ingest_chapter`：states 只更新已存在实体（类型保留、章节推进），不存在则跳过（防误建）
- 注入：实体行**优先显示 state**（有状态用状态，无则静态描述）——写作时 AI 知道"沈青山目前的处境"
- 重试条件改为 entities 或 states 任一非空即接受

**门禁**：ruff + mypy + pytest **150**（+1 states 更新测试）全绿

**真实链路验证**：手动 extract 第七章 → 沈青山 state="承认与陈远山曾是搭档…看到怀表数字后脸色变化"、陈渡 state="确信父亲陈远山不会骗他"、章节推进到第七章；注入块显示实体状态；演化历史表记录每章快照

**踩坑**：① 抽取规则5（已有实体不重复）与状态演化的设计冲突→states 独立字段；② LLM 偶发不输出 states→重试条件含 states；③ upsert_entity 空类型会覆盖原类型→保留原类型

---

## S21 Agent 循环工程化（移植 pi 模式，已完成 ✅）

**交付 commit**：`S21 循环工程化`

**背景**：主人指出"当初想在 pi 技术上改"——深度对比 pi（pi-agent-core/agent-loop.js）与 AnySpark 循环：pi 全程流式+AbortSignal 贯穿+工具并行+截断防护+steering；AnySpark 非流式+串行+无中断+仅硬上限。按 pi 已验证模式移植（不引 pi 包，core 零依赖保持）。

**实现（5 项，全部 A 类过程控制）**：
1. **流式核心**：core `StreamModel` 协议（respond_stream + on_event 回调），事件名对齐 pi（text_delta/toolcall_delta/done）；DeepSeekModel.respond_stream；RetryingModel 透传；SSE 端点统一走 Agent 流式（不再构造 stream 模型）→ 打字机效果
2. **截断防护**（pi 的 failToolCallsFromTruncatedMessage）：工具参数 JSON 解析失败→`_malformed` 标记→**不执行**→错误回填让模型重发（防半截参数写坏章节）
3. **工具并行**（pi 的 executeToolCallsParallel）：ThreadPoolExecutor 并行执行 tool_calls（保序回填）；ChapterStore 读方法补锁保线程安全
4. **协作式中断**（pi 的 AbortSignal）：core `CancellationToken`（线程安全），Agent.run(token) 循环+工具前检查点；`/api/chat/cancel` 端点（空 id=取消最近活跃会话，解决新会话 id 客户端未知）
5. **已读缓存**：read_chapter 同请求内去重（日志实证 AI 反复读 4-8 次）；写后缓存失效

**门禁**：ruff + mypy + pytest **156**（+6：流式2/截断1/并行1/取消1/缓存1）全绿

**真实链路验证**：SSE 52 帧逐词打字机（第一盏→灯亮→起时…）；长写作 chat + 4 秒后 cancel → 返回"已中断（用户取消）。"

**踩坑**：① RetryingModel 也要实现 respond_stream（组合包装完整性）；② Pydantic 单字段模型被 FastAPI 当 query（Body 需 Annotated 写法）；③ CancelIn 须模块级（ForwardRef 坑 S13 重演）

### S21 补充：过度 read 真实根因与修复（主人指出分析错误后定位）

**主人洞察**：DS 模型（pi 同款）本身不会过度 read——把锅甩给"模型特性"是错的。逐层排查定位到**机制性根因**：
- **根因 1（失忆-重读循环）**：TokenBudget 超预算后 prune 一刀切丢弃中间历史（含 read 全文），模型"失忆"→ 盲目重读 → 又占 token → 又 prune → 循环
- **根因 2**：迭代上限 8 在"读多章+写"场景不够（实测 8 次迭代全 read 没写就终止）；系统提示未引导"只读相关章节"

**修复**：
- `_collect_read_note`：prune 前扫描被裁段 read 成功记录 → 生成【已读章节清单】system 提示（摘要路径也插入）——模型知道读过什么，不盲目重读
- DEFAULT_SYSTEM 引导："只需 read 最近的 1-2 章，不要读取全部历史章节（更早内容由【已固化事实】注入提供）"
- max_tool_iterations 8 → 16

**验证**：修复前写《第十章》8 次迭代全 read 无 write 终止；修复后 AI 只读相关 2 章（第八章/第六章）→ write_chapter 落盘 1407 字，且主动埋伏笔。pytest 158（+2 已读清单测试）

### S21c：后台独立 worker + steering 防护 + compaction 缓存（已完成 ✅）

- **后台独立 worker**（修 S17 排队缺陷）：`_bg_queue` + 独立线程——图谱抽取/伏笔回收不再占请求线程池，chat 请求立即返回、SSE 的 done 帧不再被抽取拖住
- **steering 防护**：会话正在处理时新消息返回 409（提示 cancel 后重发），防并发写坏上下文
- **断点续聊确认**：cancel 后历史在 SQLite，同 conv 发"继续"可续写（实测章节落盘 3040 字）
- **compaction 提前触发**：90% 预算即压缩（对齐 pi 主动压缩）；**指纹缓存**——同上下文不重复 LLM 摘要（修续聊卡住：长上下文每轮迭代 compress 都调摘要 LLM 是卡顿主因）

**验证**：steering 409 实测 ✓；cancel→续聊章节落盘 ✓；缓存单测（摘要只跑一次）✓。pytest 159

**诚实记录**：续聊长上下文（30K+ token）时单次 LLM 调用 20-40s 是模型常态；已通过指纹缓存消除"每轮重复摘要"的放大，但单次调用慢仍存在（SSE 流式可让用户看到进度）

---

## S14 T7 验证指标（已完成 ✅）

**交付 commit**：`S14 T7 指标`

**背景**：DESIGN §9 T7 明确"核心只看三个：修改率/提问率/完成率"，但此前零埋点（设计有要求、未落地）。本次补齐——**零新表、零埋点**：信号本身就是埋点（操作即语义），纯 SQL 统计现有表。

**实现**：
- `app/server/stats.py`：
  - 修改率 = 判别型信号（accepted/modified/deleted/rejected）中非接受占比，按天分桶给趋势（↓=对齐生效）
  - 提问率 = AI 消息每千字问句数（极简正则，正确处理连续问句），按会话先后排序（↓=默契度增长可视化）
  - 完成率 = 方向固化→章节产出两层漏斗（种子层未落盘，v1 不新增表，YAGNI；注释注明后续可补）
- `GET /api/stats` 端点（health 旁）
- 测试 6 个（空库默认/修改率+分桶/非判别型忽略/提问率+会话排序/完成率/API 端点）

**门禁**：ruff + mypy + pytest **137**（+6）全绿

**同步修订**（与决策 A 对齐）：
- `docs/DESIGN.md` §0 战略定位 / §9 T6 阶段0·6 验收 / §10 整节——删除"旧数据一次性导入/数据切换导入"路线，改为"不做旧数据导入/转移，绿地空库起步"（决策 A 2026-08-02，修订说明已加在 §10 开头）
- `docs/AUDIT-V1.md`：T7 指标转 ✅（§1 表 + §3 清单）


---

## S22-S24 循环健壮性对齐 pi（已完成 ✅）

**背景**：主人要求"先把本地做到和 pi 系统一样好用"。S21 移植了 pi 的 5 项循环能力，但全量对比 `E:\Desktop\pi\pi-main`（pi-monorepo 源码，与运行时 node_modules 逐字节一致）后确认：**约一半健壮性/效率机制没抄**——Agent 循环无异常处理、重试不覆盖 429/5xx、截断防护只半套、tool 消息无 tool_call_id 配对、压缩 cut 点可能落在 tool 结果上、摘要输入截断 80%。分三阶段补齐：

### S22 健壮性底线（D1/D2/D3/D5）
- **D1 异常上下文平衡**（对齐 pi `handleRunFailure`）：`core/loop.py` 模型调用包 try/except——失败不再冒泡成 500 且毒化上下文，而是 **append assistant 失败消息保持 user/assistant 配对** + `Turn.error` 字段（API 层直接读，不再文本匹配"达到最大工具迭代"）
- **D2 重试覆盖 429/5xx**（对齐 pi `pi-ai/dist/utils/retry.js` 分类）：`core/retry.py` 重试判定升级为**类型+错误文本双通道**——瞬时类（429/500/502/503/524/rate limit/overloaded/connection/timeout）可重试；quota/billing 类（insufficient_quota/out of budget/quota exceeded/billing）**立刻失败不浪费退避**。覆盖 OpenAI SDK 的 APIStatusError（非 TimeoutError/ConnectionError 子类）。退避睡眠可取消（`cancelled` 回调 + 200ms 分段检查，Agent 每轮注入 `RetryingModel.set_cancelled`）
- **D3 截断防护完整化**（对齐 pi `stopReason==="length"` 全拒）：`deepseek.py` 流式/非流式路径**读 finish_reason**，`ModelOutput.truncated` 标记；Agent 循环对 truncated 的整批工具调用**无条件拒绝**回填错误让模型重发（此前只靠 JSON 解析失败，截断可能产生 JSON 合法但语义残缺的参数）
- **D5 取消上下文平衡**：cancel 分支 append assistant "已中断（用户取消）。"——上下文永远配对，续聊不再 user 接 user

### S23 协议完整化（D4）
- `ToolCall.id` 字段 + **assistant 的 tool_calls 声明落 store**（此前只存 tool 结果，序列畸形：user→tool，DashScope 宽容模式才跑通）+ tool 结果 metadata 带 `tool_call_id` 配对
- `to_openai_message` 转换原生 `tool_calls`/`tool_call_id`（仅当全部调用带真实 id；旧数据/无 id 链路保持纯文本兼容）
- **真实链路验证**：DeepSeek 自主 list→read→write 三工具闭环正常；取消场景序列 `user → assistant(tool_calls 声明, 带原生 id) → assistant(已中断)` 平衡无畸形

### S24 压缩重构（对齐 pi compaction）
- **E1 效率**：指纹**先查**（缓存命中直接返回，连计数都不做）→ 字符粗算（高估安全，滤掉绝大多数轮次）→ tiktoken 精算仅接近预算时——省每轮全量编码
- **B1 切割合法性**：保留段按 **token 预算**（KEEP_RECENT_TOKENS=4000，至少 KEEP_RECENT_MIN=4 条）往回找，**永不切在 tool 结果上**（孤立 tool 一起切掉）
- **B2 摘要信息密度**：摘要输入**全量序列化**可压缩段（此前只喂最后 20 条×200 字，中间关键指令全丢）；**增量更新**——识别上一次摘要作 previous，UPDATE 模式追加新进展（对齐 pi previousSummary + UPDATE_SUMMARIZATION_PROMPT）

**门禁**：ruff + mypy 全绿；pytest **110**（+6：异常平衡/取消平衡/截断全拒/配对落库/无 id 兼容/重试 429·503·quota·取消 + 压缩 5 项）

**真实链路验证**：真实 DeepSeek chat（list→read→write 3 工具闭环落盘）；SSE 流式正常；cancel → `{"ok":true}` + 上下文平衡（SQLite 查证 user→assistant(声明带原生 id)→assistant(中断)）

**踩坑**：① heredoc 分隔符不加引号时 bash 会吞 `\n` 导致 Python 替换脚本静默失败——heredoc 用 'EOF' 引号；② 并发取消时"最近活跃 token"可能命中另一会话（S21 既有设计，前端传 conversation_id 即可规避）；③ cancel 若在 run_agent 线程注册 token 前到达会错过——实际使用前端总传 conv_id，不受影响

---

## S25-S27 循环体验全面对齐 pi（已完成 ✅）

**背景**：S22-S24 补齐健壮性后，主人指示"把对齐项全部做完直到完全对标使用体验"。系统性再对比 pi 全部核心机制，补齐交互层/会话层/打磨层 8 项：

### S25 交互层
- **steering 插话**（pi Agent.steer/followUp 移植）：Agent 加 steer_queue/followup_queue（线程安全）——运行中插话在当前轮工具结果后、下一轮 LLM 前注入；追问在 agent 即将停止时注入续跑。API：`POST /api/chat/steer`（空 id 取最近活跃）。SSE turn_start 帧带 conversation_id（客户端尽早知道 id）。**真实链路验证**：写作中插话"不要使用破折号"→ AI 重新覆盖章节，最终 905 字含破折号 False
- **工具执行事件**（pi tool_execution_start/end）：SSE 新增帧 + 前端 ChatThread 显示"正在执行 X…/✓ X（ms）"
- **工具 sequential 模式**（pi executionMode）：ToolSpec.execution_mode，批内含 sequential 工具（write_chapter/write_file）整批串行——读旧写新的逻辑错序防护

### S26 会话层
- **压缩持久化回写**（pi compaction entry 语义）：ConversationStore.replace_messages + Agent.persist_compression——压缩结果写回 store（摘要+保留段），跨重启/续聊用压缩后上下文，store 不再无限膨胀
- **模型窗口感知**：DeepSeekModel.context_window（环境变量 DEEPSEEK_CONTEXT_WINDOW 覆盖，默认 64K）+ context_window 属性；build_app 预算 = 窗口×0.7（不再 12K 硬编码）
- **max_tokens 4096→8192**：长章节写作不再频繁触顶截断

### S27 打磨层
- **before/afterToolCall 钩子**（pi 移植）：before 返回拦截原因（不执行）；after 可改写结果（安全统一/信号采集挂点）
- **terminate 智能停止**（pi shouldTerminateToolBatch）：批内全部工具 terminate=True → 循环立即结束，不再死磕迭代上限

### 顺带修复（S25 验证暴露的 S21 遗留 bug）
- **SSE 假 done 提前断**：DeepSeekModel._respond_stream 原来在模型流式结束就发 done——工具场景 SSE 收到假 done 提前 break，后续 tool_call/tool_result/text 全丢（纯文本场景不暴露）。修复：模型层不发 done（done 由 Agent 轮次语义发）
- **流式重试重复 delta**：RetryingModel.respond_stream 只重试"零 delta 即失败"——已发出部分文本后的失败直接上抛（loop D1 兜底），避免前端收到两段拼接重复文本

**门禁**：ruff + mypy 全绿；pytest **182**（+10：steer 注入/followUp/sequential 串行/工具事件/before 拦截/after 改写/terminate 停止/压缩回写/SQLite replace 往返）

**真实链路验证**：SSE 完整事件流（5 轮 turn_start + 82 text_delta + 5×tool_execution_start/end + 4 tool_call + 5 tool_result + text + done）；steer 插话真实生效（章节被重写且遵守新指令）；图谱后台抽取照常

**踩坑**：① Python 闭包陷阱——on_event 引用 gen() 局部 conv_id 时必须在 gen 内定义（兄弟作用域不可见）；② SSE 假 done 是 S21 就存在的隐蔽 bug（纯文本验证测不出）；③ curl 在部分 Windows 环境对 SSE 流式响应异常（httpx 流式读取正常），调试时用 Python 客户端

---

## S28 效果证明测试（pi 行为对照 + 性能基线 + 长书压力）（已完成 ✅）

**背景**：主人要求"搞点测试证明效果确实和 pi 一样"。判断：**token 速度对比无意义**（双方接同一 DeepSeek API，与实现无关）；**有意义的对照是行为语义一致性**。新建 `benchmarks/parity/`：

### 1. pi vs 本地 行为对照（7/7 PASS）
- `pi_harness.mjs`：Node 直接加载 pi-agent-core 的 `runAgentLoop`（dist 与源码逐字节一致），fake streamFn + TypeBox 工具 schema 脚本化驱动；`local_harness.py`：同场景驱动本地 Agent
- 7 个场景：无工具/单工具/多工具并行保序/截断 length 全拒/未知工具/工具抛异常/steering 插话
- **归一化轨迹逐条对比**：工具调用参数、结果回填配对（tool_call_id）、截断全拒、错误结构、插话注入位置
- **暴露并修复真实缺陷**：本地 steer 队列只在循环开头 drain——用户在模型生成期间插话且该轮恰为终答时插话**丢失**（pi 在内层循环末尾检查，终答轮也处理）→ 终答分支统一检查 steer+followUp 队列
- 错误消息文本不对比（双方自然语言措辞自由，符合"内容自然语言"哲学），只比结构

### 2. 性能基线（存档防退化）
- `perf_baseline.py`：真实 DeepSeek 写 300 字章节 ×3，记录 TTFT/总时长/字符/s → `report/perf-<ts>.md`
- 基线：平均 17.5 字符/s（TTFT 含工具轮次无文本期）。改动循环后重跑对比字符/s 是否退化

### 3. 长书压力测试（暴露并修复保留段阈值 bug）
- `stress_longbook.py --real`：真实 DeepSeek + context_window=4000（预算 2800）连写 6 章
- **暴露 bug**：KEEP_RECENT_TOKENS=4000 固定值 > 小预算 2800——保留段吞噬整个预算，压缩形同虚设，消息数持续上涨（6→15）
- **修复**：保留段阈值随预算缩放 `min(4000, 预算×40%)`——修复后压缩触发即稳定有界（22→11 条，累计字符 1630→1216 持续下降），6/6 章节落盘
- 脚本化模式（预算 400，10 轮）：消息数 8→6 触发压缩后稳定 6，有界 ✓

**门禁**：ruff + mypy 全绿；pytest 全绿；对照 7/7 PASS；压力 6/6 PASS

**踩坑**：① pi 的 fake streamFn 必须返回带 `.result()` 的 EventStream（不是 async generator）；② AgentTool 需要 TypeBox `parameters` 否则 validateToolArguments 抛 "Cannot use 'in' operator"；③ pi 侧 toolResult 消息结构与本地不同（blocks vs 字符串）——归一化为语义轨迹对比；④ 对照测试的价值：不仅证明对齐，还**反向发现本地实现缺陷**（steer 终答轮丢失、保留段阈值不缩放）


---

## S21 系统层（已完成 ✅）

**背景**：S21 主体（Agent 循环工程化）此前已完成；系统层是 T7 验证标准要求的**整书规模哲学指标验证**——修改率↓ / 说明书累积 / 偏好遵从，用分支剧本真实测。

### 修复前置缺口：信号→说明书提炼闭环（S28 发现）
**真实缺口**：`PreferenceExtractor` 存在于 align 包（S2 冒烟脚本直接调过），但 **app.py 从未接线**——`/api/signals` 只记录信号+调节能动性，说明书永不自动更新。用户在真实产品里操作，约束不会变成写作指令——**对齐闭环（操作→信号→提炼→说明书→注入）在真实链路是断的**。
**修复**：`_bg_queue` 扩展任务类型（"chapter"/"refine"），signals 端点入队提炼任务，后台 worker 调 PreferenceExtractor → manual.add（去重）；SqliteConversationStore 加 `recent_messages()`（跨会话最近对话作提炼上下文，避开 :memory: 每连接独立库的坑）。

### 分支剧本验证（benchmarks/system/learn_curve.py，真实 DeepSeek，A/B 隔离实例）
- **分支 A（对齐学习）**：轮 1 写（无偏好）→ 用户 rejected+modified（"不要破折号"）→ 后台提炼说明书 → 轮 2/3 续写（不重复指令）→ accepted
- **分支 B（对照组）**：3 轮直接写，无信号
- **结果**：
  - 说明书累积：A=1 条（"避免使用破折号（——），一律用句号断句"）✅ / B=0 条 ✅
  - 修改率趋势：A 分支 accepted=2 / changed=2（轮 1 全改 → 轮 2/3 全接受，↓ 方向）✅
  - 偏好遵从：A 分支破折号 4→2（末章 < 首章，注入真实生效，无需重复指令）✅；B 分支无学习信号
- **学习曲线真实形态**：轮 2 破折号 5（提炼注入有延迟，非立刻收敛）——符合"对齐是渐进的"预期，诚实记录

**门禁**：ruff + mypy 全绿；pytest **183**（+1：信号触发提炼 API 测试）；总闸全绿


---

## S29 多线叙事时间建模（Backlog → 已完成 ✅）

**背景**：S13 的时序校验（check_temporal）用实体的全局 first_order 判断"时空倒置"——**多线叙事误报**：A 线第 3 章提到 B 线第 5 章才首现的角色会被误报（并行叙事的时间差被当成倒叙）。

**实现（最小闭环，机制硬编码/内容自然语言）**：
- **Entity.lines**：实体出现过的叙事线集合（JSON 列，旧库 ALTER 兼容；跨线并入不覆盖）
- **chapters.narrative_line**：章节所属线（默认 main）；write_chapter 工具加可选 `line` 参数（模型/前端可声明"本章属 line_b"）
- **check_temporal(book_id, text, up_to_order, line)**：仅当 `line in e.lines` 且 first_order 超前才警告——**同线超前=真倒叙（报警），跨线首现=并行叙事（不报）**
- /api/check 加 `line` 参数；图谱抽取链路透传 line

**门禁**：pytest **184**（+1：多线时序校验单测）；总闸全绿

**真实链路验证**（`write_chapter line=line_b` 写《B线第一章 白泽》→ 白泽 lines=["line_b"] 入库）：
- main 线截止第 1 章提白泽 → **0 警告**（跨线不误报）✅
- line_b 截止第 0 章提白泽 → **2 警告**（同线超前=真倒叙）✅

**踩坑**：① bash heredoc 无引号会把 `\"` 转义吃掉——SQL DEFAULT '["main"]' 内嵌双引号与外层字符串冲突导致 SyntaxError（heredoc 分隔符必须加引号或用 edit）；② dataclass 有默认值字段不能放无默认值字段前（narrative_line 放 Chapter 末尾）；③ 验证脚本读错响应字段（temporal_warnings 非 temporal）——API 层返回结构未对齐造成误判


---

## S31 伏笔 A/B 分级（哲学修正，已完成 ✅）

**背景**：主人提出伏笔设计的三个深层问题——① 冰与火式烂尾（铺陈超出控制）② 海贼王式找补（偶然追认为伏笔）③ 护栏担忧（伏笔管理不应变成强制清单，且**伏笔管理烂不影响作品伟大性——没有完美回收的作品**）。结论设计：**伏笔 = 开放线索的影子层（镜子非警察）**，并按 A/B 分级管理：

### 设计（两条哲学红线）
1. **系统绝不输出"回收率"指标**——回收率不是质量评分（伏笔管理烂不影响伟大性）；只报告**承诺状态**（"还有 N 条主线钩子未回收"）
2. **分级不靠系统判断内容**——默认都是 B（软），作者/AI 一句话升级为 A（硬钩子）；机制不裁决"这算不算重要伏笔"，只尊重作者承诺

### A/B 分级
- **A 类剧情钩子（must，必须回收）**：作者主动声明的**主线承诺**（对读者的契约）——注入**明确列出（★）**、wrapup 收尾检查、不回收=违约风险
- **B 类细节线索（soft，可回收可不回收）**：写作中自然捕捉/生成的铺垫——**旁观不打扰**（只汇总数量），回收是加分不回收无损

### 实现
- PlotPoint 加 `priority`（must/soft 默认 soft）+ `resolved_chapter`（回收章）；schema ALTER 兼容
- render 分级：must+open 明确列出（⚠ 主线钩子 ★），soft+open 只汇总（"另有 N 条细节线索开放中"）
- `POST /api/plot/item`（主动登记，priority 可 must）+ `PATCH /api/plot/{id}` 支持 priority/resolved_chapter
- `POST /api/plot/import-resolve`（完整书导入归档：全 resolved + 归档章——书已写完线索已揭开，提取=归档验证）
- wrapup 输出 `open_hooks`（仍未回收的主线钩子清单——提醒非门禁）
- 修 PlotStore.list → list_points（方法名遮蔽内置 list 的 mypy 顽固问题，S0 已知坑复发）

**门禁**：pytest **186**（+2：分级渲染/归档 + wrapup 钩子清单）；总闸全绿

**真实链路验证**：主动登记 must 钩子（priority=must）✓；完整书归档 9 条 open → 全 resolved ✓

**踩坑**：① bash heredoc 中 `
` 会被 python 解析为换行导致替换匹配失败——涉及转义序列的文本替换必须用 edit 工具；② PlotStore.list 方法名遮蔽内置 list 导致 mypy valid-type 错误顽固——改名 list_points 一劳永逸

---

## S32 智能体扩展能力补齐 + 写作能力实测（已完成 ✅）

**背景**：主人两次指示——① 真实测试写作能力（哈利波特第 4 章续写 × 颗粒度矩阵，4 篇全跑）② 测试暴露智能体两大缺口：方向模糊时不会探索（凭记忆硬写）、探索/检测/资料只有 HTTP API（Agent 看不到）。同时对比 pi 提示词方案（分层+渐进式披露）后确认差距。

### 1. 写作能力实测（benchmarks/writing/）
- 哈利波特第 1-3 章 → 续写第 4 章「钥匙保管员」（原著 7095 字），颗粒度 4 级（无/粗/中/细）独立库实例，4 篇全部真实 DeepSeek 跑通
- 结论：**脉络越细 → 设定越稳/细节越全/字数越失控（9176~11237）；脉络越粗/无 → 文笔发挥越好/字数可控（7249/7767）但跨书知识泄漏（凤凰社/小天狼星摩托/高锥克山谷）与硬设定违规（完整魔杖/"伏地魔死了"）出现**
- 交互观察：4 篇全部直接开写零反问；【AI补充】标注长文真实生效；字数自报不可靠
- 附带发现：LLM 设定裁判漏报跨书泄漏、误报原著台词（需人工兜底）
- 报告：`benchmarks/writing/REPORT.md`

### 2. 智能体探索修复（方向模糊 → 主动探索）
- **根因**：Agent 工具集只有 list/read/write/file；探索是纯 HTTP API（人驱动）；DEFAULT_SYSTEM 直接引导"写"，无"方向不明先澄清/探索"
- **修复**：新建 `server/tools_extras.py`——`explore_direction`（意图理解+多智能体并行探索→方向卡呈现用户选择）**无条件注册**；`read_material`/`check_text` 按 `enable_extras` 点亮（默认关）
- DEFAULT_SYSTEM 收紧："首要目标是把正文写出来并落盘，不要为准备而反复调用无关工具；仅方向不明确时先 explore_direction"
- **踩坑（本次实测抓到）**：最初三工具无条件注册 → 真实模型在"写 50 字"明确任务里乱调 read_material 导致不写正文（test_wrapup 失败）→ 改按需装配（对齐 S15 哲学：能力可见≠无条件注册，防无关调用干扰主链路）
- **门禁**：pytest **195**（+9：S32 六项+既有 3 项回归）；总闸全绿
- **真实链路验证**：方向模糊（"深夜火车站等什么，你看着办"）→ Agent 主动 explore_direction 并呈现 4 方向供选 ✓；方向明确（"写第1章100字"）→ 直接 list→write 零干扰 ✓

### 3. pi 提示词方案对比（结论）
| 维度 | pi | AnySpark | 本次落地 |
|---|---|---|---|
| 常驻 vs 按需 | 索引常驻/正文按需（skills） | 全量平铺 | 扩展工具按需点亮（enable_extras） |
| 分层 | 全局/项目/会话 | 单层+说明书两级 | 未动（后续候选） |
| 能力档案 | skills | 无（模板库藏探索内） | 未动（后续候选） |
| 扩展可见性 | 全部注册成工具 | 部分仅 API | explore/check/materials 工具化 |

**遗留候选**（按需再做）：① 技能档案体系（L2/L3 模板库→Agent 可按需读取的写作技能）② 分层系统提示（全局层）③ 陌生文本测试（主人已备素材，待跑）

---

## S33 脉络粒度感知（粗脉络=自主设计，已完成 ✅）

**背景（主人诊断）**：猎手准则粗粒度测试发现——模型把粗脉络当"约束更小的细脉络"处理，只把主干扩写一遍，没有"这是需要我自己设计"的意识。主人要求：粗粒度时 AI 应自主探索/设计，而非直接写。

**修改**：`DEFAULT_SYSTEM` 新增 S33 粒度感知引导——
- 脉络越细（逐场景/要点全）→ 严格遵循、不得遗漏
- 脉络越粗（只有主干/种子）→ **场景推进、细节、节奏需自主设计**：动笔前先构思场景序列（不必输出），正文体现自主设计层次（原创细节/节奏变化/氛围经营），不把主干复述一遍

**验证（猎手准则第四章粗粒度重写 v2 vs v1）**：

| 维度 | v1（旧） | v2（新） |
|---|---|---|
| 行为 | 主干扩写 | **回复中先给出场景序列设计表**（三场次+节奏），正文体现设计 |
| 吉娜/黑铁城 | 全程无名 | ✓ 回归 |
| 水鬼定义 | 无 | ✓（溺死者怨念所化妖魔） |
| 前文呼应（羊皮纸歌谣） | 无 | ✓ |
| 反转钩子 | 逃跑（错过主线） | **眼神平静/走路无声/咧嘴到耳根/手纹发烫**——对准原著第 5 章揭面 |
| 场景覆盖 | ~5.5/10 | ~7.5/10（人工通读） |

**结论**：粒度感知引导真实生效——粗脉络下模型从"草草扩写"变为"先设计后落笔"，且设计质量（成套异常观察点服务反转）高于 v1。字数仍超标（2918/2200，+33%）——字数控制单列待修。

**门禁**：ruff ✓ pytest 25 ✓；DEFAULT_SYSTEM 改动无测试断言破坏。

---

## S35 档位记录集：可增删改 + 恢复默认 + 心智模型指导（已完成 ✅）

**背景（主人定架构）**：档位不再固定五级——① 全局可增删改（一个用户也可能希望有不同档位）② 可恢复默认（**不重置心智模型**）③ 项目级不做。哲学：档位本身是内容（自然语言）可改，机制（结构/注入/温度映射）硬编码。

### 实现
- **agency.py 重构**：`AGENCY_LEVELS` 常量 → `agency_levels` 表（id/name/description/temperature/order_index/is_default）+ AgencyLevel 记录；默认五级种子
  - CRUD：`add_level`（追加末尾）/ `update_level`（名称/描述/温度）/ `delete_level`（至少留一条，删当前回落默认）/ `reset_defaults`（**只重置档位表，manual 心智天然保留**）
  - **温度入档**：自定义档位自带温度（不再按 level 数字查表）；`temperature_for` 兼容旧数字调用
  - adjust（反馈调节）按排序位 ±1 有界
  - `build_agency_block(level, mental_notes)`：可附用户心智偏好
- **manual 加 `affect_agency` 心智标记**（ALTER 兼容）：标记"影响能动性"的偏好条目 → 注入档位块（"用户心智偏好：…"）——**心智模型指导档位的 L1 通道**
- **API**：GET /api/agency（current+levels）、POST（level_id 优先，兼容 level 数字=排序位）、/api/agency/add、PATCH/DELETE /api/agency/{id}、POST /api/agency/reset；/api/manual 支持 affect_agency
- **兼容**：旧数字档位调用（ChatRequest.agency_level int → 按 order 找档位）；前端 AgencyPicker 的 level 字段保留（=order）

### 验证
- 单测 +9（CRUD/reset/adjust 按位/删除保底/注入含心智/API 全链路），pytest **198** 全绿，总闸 ✅
- **真实链路**：新增"极简风"档位（temp 0.3）+ manual 心智条目（"不喜欢形容词堆砌"）→ chat 输出短句克制风（档位+心智组合生效）✓；恢复默认 → 档位回 5、manual 保留 ✓

### 遗留（后续）
- L2（AI 建议档位）/L3（自然语言生成档位）未做——心智接入已打通 L1（标记→注入），L2/L3 按需
- 前端 AgencyPicker 未改（API 兼容旧字段，显示自定义档位待前端按需）

### S35b 修正：档位=纯能动性，心智模型独立（2026-08-05）

**主人纠错**：S35 把心智（affect_agency 条目）附加进档位注入块，混淆了职责边界——**档位控制能动性（主动程度），文风/喜好/毒点是心智模型的职责**；心智模型应包罗万象、渐进式披露，与档位正交。

**修正**：
- `build_agency_block` 移除 mental_notes 参数——档位块只描述能动性（名称/描述/温度），不含任何用户个性化内容
- manual 回滚 `affect_agency`（字段/schema/API/测试全撤）——心智不进档位
- 职责边界写入 agency.py docstring

**心智模型架构方向（独立系统，后续设计）**：
- 包罗万象：文风/喜好/毒点/边界/目标/信息偏好……不限于"说明书"（manual 是雏形）
- 渐进式披露：索引/摘要常驻上下文，完整条目按需注入（对齐 pi skills 模式）——避免心智条目多了全量注入爆 token
- 与档位正交：档位管"敢不敢做"，心智管"怎么做/别做什么"

---

## S36 架构审计：对照 pi 检查主体简洁/拓展强大（已完成 ✅）

**审计项**（S32-S35 演进后，对照 pi 的"core 极简 + 功能外置 + 无横向耦合"）：

| 检查项 | 结果 |
|---|---|
| core 零依赖 | ✅ `dependencies=[]`，无任何兄弟 import——主体极简 |
| 兄弟包互相依赖 | ✅ align/explore/check/template/graph 之间**零 import**（grep 验证）——单向依赖 core ← 功能包 ← app 组合根 |
| 注入链模块化 | ✅ 6 注入块（manual/graph/agency/bias/plot/mood）各自独立模块，app 只拼装+skip_inject 开关 |
| 工具=包薄壳 | ✅ tools_extras 的 explore/check/material 工具是薄封装（对齐 pi extension→包 模式） |
| **全局状态钩子** | ❌ **S35 引入的 `_STORE_HOOK`/`bind_agency_store` 全局可变钩子**——`build_agency_block` 的 str 分支依赖它；grep 证实 str 分支与 bind_agency_store **零调用**（死代码） |

**修复（S36）**：删除 str 分支 + `_STORE_HOOK` + `bind_agency_store`（纯函数化 `build_agency_block(level: AgencyLevel | int)`，无全局状态）——对齐 pi 的闭包注入风格（依赖随构造传入，不藏全局）。

**结论**：与 pi 一致——主体简洁（core 零依赖）、拓展强大（兄弟包独立、功能外置组合根装配）；S35 的全局钩子是唯一真实耦合点，已清。组合根 app.py（1241 行/7 参数）是组合根正常形态（显式装配），非过度耦合。

**门禁**：pytest 108 全绿；总闸 ✅

---

## S37 图谱重要性信号：高频保底注入（超长书一致性地基，已完成 ✅）

**背景（主人五场景分析）**：超长书（如《猎手准则》1355 章）的续写/同人/全书变换都依赖"系统懂全书"——但审计发现图谱注入 `known_facts` 是 **ORDER BY last_order DESC（最近 15 实体）**，百章级会漏早期主线角色（最近 100 章没出现就不注入）。S18 的"长书图谱记忆"卖点在超长场景失效。

**设计（哲学：中性事实，不搞 AI 主观裁决）**：
- **weight = 实体出现的不同章节数**（出场越广=贯穿性越强，客观可算）
- `upsert_entity`：新章节首次出现 weight+1（同章重复 upsert 不累计）；新实体=1；老库 ALTER 补列回填 1
- `known_facts` 混合选取：**最近 2/3 + 高频 1/3**（高频保底，最近补充，去重）

**验证**：
- 单测 +2（weight 按章累计/高频实体久未出现仍注入），pytest **199** 全绿，总闸 ✅
- 真实链路：主角前 50 章高频 + 早期设定前 10 章 + 第 100-115 章 15 个新角色 → 截止 115 章注入块**同时含主角（weight50）、早期设定（weight10）、最近角色**——修复前主角会被 15 个新角色挤掉

**意义**：百章级超长书的早期主线一致性有了保底；后续（设定档/结构计划/批量任务）都建在这层之上。

---

## S38 超长书实战：猎手准则第一卷 164 章灌入 + 理解验证（已完成 ✅）

**背景（主人场景 5 分析解读）**：验证系统对超长书的"理解能力"——把《猎手准则》第一卷（164 章，约 40 万字）逐章真实 LLM 抽取灌入图谱，再基于图谱总结"第一卷讲了什么"。

**实现**：`scripts/batch_ingest_hunter.py`（逐章 extract→ingest，ThreadPool 6 路并行，失败重试 2 次，进度 JSONL）

**结果**：
- 164 章全成功（19.1 分钟，6.1s/章），累计 827 实体/713 关系/276 事件（去重 516：133 角色/182 设定/100 地点/97 物件）
- **weight（S37 重要性）直接呈现主线骨架**：赵光离 76 章贯穿、顾欣桐 37、因佩斯家族/古恩教堂/黑铁堡/橡树学院/天驱联盟（核心世界观）
- **理解验证**：纯图谱数据（无原文）→ LLM 总结第一卷——一句话概括/5 段剧情线/人物关系/世界观/结尾悬念全部准确
  - 抽查 3 处对照原著：第 7 章哈伦日记 ✓ 第 150 章沈禾登场（军装白羽翼）✓ 第 163 章顾欣桐袭击赵光离 ✓
- **意义**：超长书理解链路成立（逐章抽取→图谱积累→基于图谱生成理解）；S37 高频保底让 164 章级主线不丢

**遗留**：图谱理解是中间产物——"分析报告产物化"（主题/结构/弧线/文风分析）待场景 5 完整设计；entity_states 快照排序有瑕疵（非章节序）

---

## S39 超长书理解三件套：详细故事线 + 续写验证 + 分析报告（已完成 ✅）

**1. 详细故事线（修正版）**：基于完整 294 事件（limit=10000）生成——6 幕拆解/4 条贯穿主线/人物弧线/结尾状态。**修正了 v1 的矛盾**（v1 用 list_events 默认 limit=200 截断到 110 章 → 误判"一起离开"；完整数据确认结尾=顾欣桐背叛重伤、取代升学名额随沈禾离开）。

**2. 续写验证（场景 3）**：用 vol1 图谱库起后端续写第 165 章——图谱记忆正确注入（黑色猎手/黑盒/沈禾/顾欣桐背叛），续写延续"终结之谷重伤"线，与完整图谱结尾**一致** ✓。AI 标注（档位2）合理。

**3. 分析报告（场景 5 + 设定档）**：纯图谱驱动生成 5853 字分析报告——主题×3（背叛与信任/诅咒与力量共生/阶级固化，各带章节证据）、结构（三幕+节奏曲线+有限视角欺骗性）、角色表（身份/弧线/结局）、伏笔网络、**世界观设定档**（职业/诅咒/势力/地点/物品/规则）、风格特征。

**附带发现**：`list_events`/`list_relations` 默认 limit=200——超长书（>200 事件）会被截断，调用方需显式传大 limit（本次已用 limit=10000）。

**产物**：`benchmarks/writing/hunter/vol1_storyline_full.md` / `vol1_analysis.md` / `vol1_ch165.md`（不入库）

---

## S40 批量任务（场景 4 全书变换核心）：批量改写 + 批量审读（已完成 ✅）

**背景**：场景 4（全书变换：改文风/改情节/筛选插入）需要"多章批量处理"——`_bg_queue` 已有（章节抽取/信号提炼），扩展批量任务类型。

**实现**：
- `_bg_queue` 扩展任务类型：`("batch_rewrite", batch_id, chapter_ids, instruction)` / `("batch_review", batch_id, chapter_ids)`——后台 worker 串行执行（不阻塞请求）
- `_run_batch_rewrite`：逐章读 → LLM 按指令改写 → `chapters.upsert`（**覆盖前旧版进版本历史**，可回退）
- `_run_batch_review`：逐章 `run_review`（检测网 7 类）→ 汇总（含 hard 数 + 报告全文）
- 批状态：内存 dict（会话级，queued/running/done + done/total/results）
- API：`POST /api/batch/rewrite` / `POST /api/batch/review`（提交即返回 batch_id）/ `GET /api/batch/{id}`（进度/结果）
- 已知限制：批量改写单次输出（长章 >8192 token 可能截断，需分段改写）；批状态内存级（重启丢失）

**验证**：
- 单测 +1（批审读/批改写 API 全链路 + 非法输入 400/404），pytest **200** 全绿，总闸 ✅
- 真实链路：写 1 章 → 批审读（hard=0 + 情感连贯建议）→ 批改写"结尾加悬念"（365 字，悬念成功加上，旧版进版本历史）

**意义**：场景 4（全书变换）的基础执行器就位——改文风/统一指令批量应用可行；连锁情节修改（蝴蝶效应）仍需"结构计划/依赖分析"（后续候选）。

---

## S41 设定档系统（作者正典：能力体系/人物卡/世界观规则，已完成 ✅）

**背景（"假死"讨论的启示）**：续写质量上限 = 设定覆盖深度。图谱只覆盖已写章节的动态事实（第一卷图谱不知道第二卷才揭示的【假死】）；需要"作者正典"设定——提前/独立维护规则类设定，写作时注入。

**定位（与图谱正交）**：
- 图谱 = 自动抽取的动态事实（"系统读到的事实"，随章节演化）
- **设定档 = 作者维护的正典**（人物本质/能力体系/世界观规则/禁忌，不随剧情漂移）

**实现**：`align/worldsettings.py`——`world_settings` 表（id/category/name/content/source/order）+ CRUD + `render_settings`（按类别分组的自然语言注入块）
- 类别：人物卡/能力体系/世界观/势力/地点/物品/规则/禁忌
- API：`/api/settings` CRUD（作者手写 source=manual）
- 注入：`_make_agent` 加 settings 块（skip_inject 支持 "settings"）
- 与图谱/说明书互补：说明书=偏好（怎么做）、图谱=动态事实（现在怎样）、设定档=正典（本质是什么）

**验证**：
- 单测 +2（CRUD/渲染/API/注入），pytest **202** 全绿，总闸 ✅
- **真实链路（关键）**：设定档写入【假死/爆裂箭矢/猎人准则】→ 续写"终结之谷"——
  续写正文完整利用设定：顾欣桐说"你的战气没有溃散，说明你还没用'假死'"（假死成悬念）、
  "三支特制的爆裂箭矢…他只剩一次机会"（能力成底牌）、"猎人准则第二条：越是接近诡异，越要审视自身"（准则成内心独白）
  ——对比无设定档时只能写"重伤求生"，设定覆盖直接提升续写质量

**遗留**：从图谱提炼设定草案（LLM 生成→作者确认）未做（S41 只做了手写 CRUD+注入）；渐进式披露（设定条目多时分段注入）按需

---

## S42 设定档自动提炼 + 修正版续写验证（已完成 ✅）

**背景（主人两个批评）**：① 500 字续写测试无意义（短章测不出真实能力）② 之前把【假死】等**未来设定**直接注入设定档 = 全知全能泄漏——AI 让顾欣桐说"你还没用假死"（她不可能知道），暴露"AI 不会安排角色认知局限"的问题，但根因是测试输入错。

**修正**：
1. **提炼边界**：`POST /api/settings/extract` 只基于图谱已覆盖章节（=角色/叙事者都可能知道的信息）提炼设定草案（LLM 生成 42 条：人物卡/能力体系/世界观/势力/地点/物品），作者确认入库——**不掺未来设定**
2. **正常字数重测**：第一卷设定档入库（42 条）→ 续写第 173 章「归途」（**3826 字**）
3. **认知局限引导**：提示词加"角色的认知应受限于其经历"

**结果（对比）**：
| | 之前（500字+泄露） | 修正后（3826字+第一卷设定档） |
|---|---|---|
| 字数 | 500 | 3826 ✓ |
| 未来设定 | 假死/爆裂箭矢被 AI 全知使用（顾欣桐知道假死=越界）| **无泄露**（设定档只有第一卷信息）|
| 角色认知 | 顾欣桐全知 | **知识有出处**：赵光离"在哈伦日记里见过食尸鬼""赫拉斯告诉他的路"——来源明确 ✓ |
| 状态延续 | 部分 | 完整（退魔符印/黑盒/黑色卷轴/胸口伤/左手贯穿孔）|

**结论**："AI 不会安排角色认知局限"在**正确输入下不成立**——修正输入后 AI 的知识都有出处；之前的问题是测试输入污染（未来设定注入），非 AI 必然行为。但"叙事全知 vs 角色认知"的写作约束值得作为提示词引导固化（当前已在测试提示词层验证，是否进 DEFAULT_SYSTEM 待定）。

**门禁**：pytest 203 全绿，总闸 ✅

---

## S43 写作技巧内容化（参考 pi skills：DEFAULT_SYSTEM 回归极简，已完成 ✅）

**背景（主人哲学审计）**：S33 粒度感知/S42 认知边界等"写作技巧"被硬塞进 DEFAULT_SYSTEM → 行为规则堆叠，违背"智能体驱动/相信模型/少加规则"。主人指示：做技巧参考 **pi skills** 形态。

**实现**：`align/skills.py`——skill 式内容载体：
- 每条技巧 = {name, description（索引一行）, content（完整指令）, enabled}，存 `writing_skills` 表，可增删改/开关
- **默认种子 3 条**：粒度感知（原 S33）/ 角色认知边界（原 S42）/ 氛围克制
- **DEFAULT_SYSTEM 回归极简**（467→~230 字）：只留"行为底线"（写出来并落盘/方向模糊才探索），写作技巧全部移出
- **渐进式披露**（对齐 pi）：索引（描述常驻）+ 内容（正文注入）双块；技巧多了后可只留索引、正文按需
- API：`/api/skills` CRUD + enabled 开关；注入：`_make_agent` skills 块（skip_inject 支持 "skills"）

**验证**：
- 单测 +2（种子/渲染/开关/API/注入），pytest **205** 全绿，总闸 ✅
- 真实链路：3 条默认技巧注入；chat 写作氛围克制生效（感官细节、无形容词堆砌）

**哲学落地**：DEFAULT_SYSTEM = A 类过程控制底线（硬编码，极简）；写作技巧 = 内容（自然语言，可编辑/开关/按需）——"智能体驱动"守住：智能体拿到能力+信息，而非一长串守则。

---

## S44 定点编辑工具（锚点定位的插入/删除/替换，不重写整章，已完成 ✅）

**背景（主人问询）**：目前只有整章覆盖（write_chapter）和整段改写（rewrite），缺"指哪改哪"的定点编辑。

**实现**：
- `apply_patch(content, operations)` 纯函数（tools_writing.py）：**自然语言锚点**定位段落（段落=换行分隔，锚点=段内子串），三种操作：
  - `insert`（锚点段后插入新段）/ `delete`（删锚点段）/ `replace`（替换锚点段）
  - 多操作按序应用，未命中锚点=该步失败不应用，其余继续
- **Agent 工具** `patch_chapter`（title + operations JSON 数组，sequential 模式）；注册进写作工具集
- **API** `POST /api/chapters/{id}/patch`（结构化 body，复用 apply_patch；旧版进版本历史）

**哲学**：位置用**内容定位**（自然语言锚点文本匹配）而非机制化行号——符合"机制硬编码、内容自然语言"。

**验证**：单测 +1（插入/删除/替换/未命中/404 全链路），pytest **206** 全绿，总闸 ✅

**意义**：全书变换（场景 4）的"筛选定位后插入/删改"有了直接工具；Agent 可自主定点修改（不用整章重写）。

---

## S45 影响分析（连锁修改：改一章 → 受影响下游章节，已完成 ✅）

**背景（场景 4 进阶）**：全书变换的"改一个情节 → 后续连锁"需要先知道**哪些下游章节受影响**——用图谱事件/关系（chapter_ref + involved 实体）做影响分析。

**实现**：
- `GraphStore.impact_chapters(book_id, changed_order, entities)`：
  - 输入：被改章节序号 + 涉及实体（缺省自动取该章图谱事件 involved 并集）
  - 查询：后续章节（order>被改章）中事件 involved 或关系 from/to 涉及这些实体的章节
  - 输出：受影响章节列表（按 order 排序，含涉及实体/事件摘要）
- `POST /api/impact {chapter_order, entities?}` 路由

**验证（vol1 真实图谱）**：
- 改第 40 章（乔治·因佩斯）→ **精准命中 20 章**（第 41-68 章落叶庄园酒会线）✓
- 改第 60 章（自动提取主角）→ 100 章全中（主角线贯穿=预期行为，信息价值低但正确）

**已知限制（诚实）**：改"核心主角"相关情节会过度报告（主角几乎每章出现）——影响分析对次要实体/事件线精准，对主角线是"全影响"提示。

**门禁**：pytest 207 全绿，总闸 ✅

---

## S46 剧情计划（计划→执行系统化，场景 1 核心缺口，已完成 ✅）

**背景**：AI 能产出规划（S34），但规划是 chat 输出、无固化机制——"写这一章时 AI 不知道接下来计划"。本模块把规划固化为**章节级计划**。

**实现**：`align/plan.py`——`story_plan` 表（chapter_order/title/content/status: planned|done）+ CRUD：
- **注入**：写作时注入"当前章计划 + 后续 2 章"（render_plan 只注入 planned，horizon=3）——AI 知道接下来写什么
- **推进**：写完一章 PATCH status=done → 下一章计划自动成为"当前章"
- **与伏笔区分**：plan=待写章节安排；plot_points=已埋线索状态
- API：`/api/plan` CRUD + status；注入 skip_inject 支持 "plan"

**验证**：
- 单测 +2（CRUD/渲染推进/API/注入），pytest 117 全绿
- 真实链路：固化 3 章计划（雾城→灯塔→死期）→ 写第一章 → 标记 done → 写第二章（按"灯塔"计划展开，AI 提到灯塔铁门/脚印）——**计划→执行闭环成立**

**意义**：场景 1（有计划从头写）的核心缺口补上——规划从"一次性输出"变成"可推进的执行蓝图"。

---

## 评测回归（S32-S46 大改后）：单元层 17/17 恢复（已完成 ✅）

**背景**：S32-S46 密集改动（探索工具/档位 S35/设定档/技巧/计划/批量/影响分析）后，回归 S16 单元层 benchmark 验证机制未被破坏。

**结果**：首轮 **15/17**——T14（档位载体）/T9（信号采集）失败，根因是 **S35 档位 API 变更导致旧断言过时**（非功能损坏）：
- T14：POST /api/agency 旧断言 `level` 数字 → S35 后返回 `current` 对象 → 适配 `current.order`
- T9：GET /api/agency 旧读 `level` → 适配 `current.order`

**修复后**：**17/17 全过**（T1 F1 0.714/T5 时序 3/3/T13 档位 1.0 vs 0.078/T15 记忆 1.0 等全部保持）——S32-S46 未破坏任何单元层机制。

**教训**：benchmark 断言与 API 契约耦合——API 演进（S35）需同步回归 benchmark（本次暴露，已修）。

---

## S52 架构评估：工具装配接口化（已完成 ✅）

### 背景（评估结论）
主人问"当前工具存储模式 + 架构要不要改"，基于实测代码（非猜测）评估：
- **不拆分包骨架**：core/explore/align/graph/template/app 包边界干净（唯一问题 app 最重 6301 行），符合 DESIGN §4 YAGNI——不做 pi 式"挂载包"（已有等效机制：ToolRegistry + enable_* 开关 + ExtensionTool 运行时表）。
- **唯一该做的**：把工具装配从 `app.py` 的 `_make_agent` 内联块抽出为独立模块（组合根接口化，解耦 HTTP 编排）。让任何入口（HTTP/CLI/桌面）+ 将来新增工具分组（如 MRAgent 主动检索独立 group）能复用同一套装配。

### 实现（纯搬移，零行为变更）
- 新增 `packages/app/src/anyspark/server/toolkit.py`：`build_toolkit(registry, *, chapters/workspace/model/graph/plots/plans/settings/materials/ext_tools, enable_domain/codex/extras/search)`——注册顺序与开关语义与原先内联块**逐字对应**。
- `app.py::_make_agent`：内联 ~74 行工具装配 → `registry = build_toolkit(ToolRegistry(), ...)`。
- 清理 app.py 中随搬移变为未使用的导入（`execute_extension`/`tool_spec_from_ext`；`register_writing_tools`）。

### 验证
- ruff ✅ / mypy ✅（toolkit.py & app.py 均通过）
- pytest：除 2 个**预存失败**外全绿（见下）。

### ⚠️ 注意（与本次无关的预存脏状态）
本次改动只触 app.py + 新增 toolkit.py。但工作树有**大量未提交的预存改动**（`core/loop.py` 969 行改、`codex.py`/`tools_extensions.py`/`deepseek.py`/`types.py` 等），其中 `core/loop.py` 存在**预存 bug**：
- `_loop` 的 except 分支（line ~219）引用 `output`，但模型首轮调用失败时 `output` 未赋值 → `UnboundLocalError`，导致 `test_loop.py::test_model_failure_keeps_context_balanced` 与 `test_chat_stream_error_frame` 失败。
- **非本次重构引起**（git diff 证明 loop.py 非我所改；`codex.py` 的间歇 `Path` NameError 亦来自预存改动，现不复现）。

> 决策：架构骨架按 YAGNI 冻结，不动。等出现**第二个**复用工具装配的场景（web 版/CLI 独立入口/MRAgent 主动检索开关）再做进一步拆分。`core/loop.py` 的 UnboundLocalError 需单独修（S53 建议优先）。

### S52 补记（修复落地 + 门禁全绿）
- **loop.py 防御修复**：`output` 先置 `None` + `assert output is not None` 后进入 `_emit_record`——杜绝模型调用失败异常路径的 `UnboundLocalError`（`test_model_failure_keeps_context_balanced` 间歇失败的根因防御，虽复现困难但消除了该类风险）。
- **git 纠缠处理**：发现 S49b 提交把 app.py 的 build_toolkit 改动一起扫了进去但**漏提交其依赖的 toolkit.py**（新文件未追踪）→ HEAD 一度引用不存在的模块。已补提交 `toolkit.py` + `loop.py` 修复，使 HEAD 自洽（本地 commit，未 push）。
- **lint 收尾**：修掉 S49b 引入的 3 处 ruff（tools_extensions.py E501 / test_recorder.py F841+E741），非本次重构引入，为门禁全绿顺手修。
- **总闸**：✅ 全绿（ruff 0 / mypy 103 / pytest 267 / tsc / eslint / build）。
- 遗留：`.gitignore`、`benchmarks/compare/tasks.py`、`benchmarks/writing/*` 为预存脏状态，非本次改动，未动。

## S53 架构错位修复：叙事技巧重构 + 心智模型=会话规划器 + 全项目内容化（已完成 ✅）

**背景（主人 S50 讨论三连批评 + 审查）**：
1. mood 滑块数值 `80/100` 裸传模型（工程量纲不该进语义层）
2. 预设 4 维度 `{tension,warmth,calm,dread}` 锁死内容、限定模型发挥（违背"内容模型生成"）
3. 心智模型是复杂系统，应**指导主循环规划会话**而非**注给写作工具**（心智记录多是习惯，直接注入正文无意义）
- 三连批评全部成立，设计判断记入 DESIGN §12.17

**修复 1：skills → 叙事技巧重构（名实相符）**
- 旧 3 条种子（粒度感知/角色认知边界/氛围克制）概念不同源、全放错筐 → 移除：
  - 粒度感知 = 能动性按实例自适应机制 / 认知边界 = 一致性硬约束 / 氛围克制 = 文风偏好（归属记录 DESIGN §12.17）
- 新 `WritingSkill` = { name/description/content/**example**（情形案例）/tags/enabled/order }——用描述+具体案例提升文笔
- 新种子 3 条：镜头感与视角 / 对白机锋 / 节奏控制（名+技法+情形案例三段式）
- 注入：索引常驻 + 内容按需（<5 全量；多后按 tags 匹配会话意图选 2-3 条）
- 旧库自动迁移：检测到"粒度感知"等旧种子名 → 重建为新种子

**修复 2：mood 数值语义化 + 维度内容化**
- `build_mood_block`：0-100 → 程度语义词（无/极轻微/轻微/中等/较强/强烈），**裸数值不再进模型**（照抄 chat_rewrite 的 subtle→"尽量保留原文"成功模式）
- 4 维预设 → `MoodDimStore`（SQLite 内容载体，可增删改/开关；默认种子保留）
- 每维度带语义描述（怎么写）+ 情景样例（什么时候用）；前端滑块从 `/api/mood/dims` 动态渲染
- 新增 `/api/mood/dims` CRUD

**修复 3：心智模型 = 会话规划器（从写作循环移除）**
- **manual 不再作为注入块进写作 system_prompt**（文风/喜好/习惯条目全退场）
- manual 加 `category` 分类：collab（协作）/style（文风）/habit（习惯），旧库默认 style
- 新增 `MindPlanner`：读 collab 条目 → 产出 SessionPlan（建议档位 + 协作约定）
- 主循环装配：未显式指定档位时按 collab 条目推断（"直接写别啰嗦"→档位升 / "先给方案再动笔"→档位降）；协作约定注入系统提示**顶部**（怎么配合，非写作内容）
- style/habit 条目不再注入（渐进式披露第一步：全退场，心智系统完整化后按需引入）

**修复 4：全项目同类错位内容化（审查扫描）**
- explore DIMENSIONS（6 维）→ `DimensionStore` 内容载体 + `/api/explore/dims` CRUD
- graph ENTITY_TYPES（5 类）→ `graph_entity_types` 表（项目级可配置）+ `/api/graph/types` CRUD；提取提示词动态拼类型（不再"五选一"写死）
- worldsettings 类别（8 类）→ `setting_categories` 表 + CRUD；add() 不再强制降级白名单
- template 四要素 / materials Purpose：确认内容扩展通道已开（外部导入不校验），默认集提升为可读常量 + 注释
- bias：**反向心智模型**（AI 自述→用户可预测），与 manual 方向相反，**不合并**（主人纠正）

**验证**：
- pytest：align（含新增 test_mood/test_mind）+ app + explore + graph + template + check + core 全绿（排除 test_complete 单条真实网络调用）
- ruff 0 / ruff format 0 / mypy 0（107 文件）/ tsc / eslint / vite build ✅
- 真实链路：mind_planner collab 条目 → 档位推断生效；style 条目确认不再进写作上下文（test_mind 断言）

**遗留**：`test_complete.py::test_search_web_returns_or_empty` 单条真实网络调用（360/Bing，设计上失败返回空不挂）；`.gitignore`/benchmarks 预存脏状态未动。

### S53b 修正：心智指导性保留 + 与 skill 解耦联动（主人纠偏）

**主人纠偏**：S53 把 style/habit 条目"全退场"是过度——"文风不写入，**文风偏好要写入**，习惯也是，具体功能解耦，**指导性的不能去掉**"。
- 例：作者喜欢白话文风 → 写进心智（style 条目）→ 系统有"白话文"skill → 模型判断本篇适合 + 知道用户偏好 → 导入该 skill

**修正落地**：
- `MindPlanner` 读**全部类别**（collab/style/habit）→ SessionPlan{档位, 协作约定, 文风偏好, 习惯}：
  - collab → 档位推断 + 协作约定（顶部）
  - style → `mind_block`（用户文风偏好块）+ **驱动 skill 匹配**
  - habit → `mind_block`（用户写作习惯块）
- `select_skills_for(skills, context, prefs)`：**prefs 优先匹配** skill 的 name/description/tags（心智联动），其次 context 匹配 tags，都不中保底前 limit
- 注入：心智块 + skill 内容块进写作上下文（渐进式披露：只取锁定/高置信前 5 条，不堆砌全量说明书）
- 端到端验证：manual style="喜欢白话文风" + skill"白话叙事"(tags=白话) → chat 注入含【用户文风偏好】+【白话叙事】技能 ✓

**哲学**：心智=偏好（作者喜欢什么），skill=能力（怎么做到）——两系统解耦，装配时联动。

## S54 叙事技巧生成器（文风提炼 → skill 候选，已完成 ✅）

**背景（主人需求）**：作者喜欢某篇小说文风（如斗破苍穹）→ 导入原文 → 提炼成可执行 skill。
此前 skill 只能手工 CRUD，无生成机制。

**场景洞察（主人实测经验）**：LLM 生成 skill 天然倾向**描述性语言**（"文风大气磅礴"
"节奏明快"）——抽象评价对模型写作零指导价值。最有指导价值的是：
- ① 负面约束（"不要铺垫环境再推进"）
- ② 直接案例（原文摘录 + 为何有效）

**设计决策（S54b 主人纠偏）**：**引导而非禁止**——不硬禁抽象描述（规则驱动违背
"相信模型"哲学），而是 prompt 强调"什么最有指导价值 + 案例尽量摘录原文"，
让模型自然产出可执行内容。抽象认知可作背景，但每条技法落到可执行层面。

**实现**：
- `skillgen.py`：`SkillGenerator`（原文 → skill 候选五段式：name/description/
  content/example/tags），GENERATE_PROMPT 引导负面约束+真实案例+覆盖维度
- **A 手动**：`POST /api/skills/generate`（传 source_text/hint）→ 候选（去重）
- **B 心智联动**：新增 style 偏好（manual）→ 后台 `_refine_skill_drafts` 用偏好
  作 hint 生成候选草稿
- **C 信号驱动**：`POST /api/signals` 触发后台从接受/修改信号提炼候选草稿
- **人工确认闸门**：候选进 `skill_drafts`（草稿表，未生效）→
  `POST /api/skills/drafts/{id}/promote` 转正 / DELETE 拒绝——对齐
  tools_extensions"人工批准生效"哲学（错误 skill 污染主链路 S32 实证）
- drafts API：list/promote/delete

**验证**：
- pytest：test_skillgen（7）+ drafts 转正 + API 全绿
- 端到端：A 导入原文→候选（负面约束✓真实案例✓）；B style 偏好→后台草稿→确认转正✓
- ruff 0 / format 0 / mypy 0（111 文件）

## S53c 心智模型更新端补完 + 真实链路验证（已完成 ✅）

### 补齐（DESIGN §12.18 更新方式全景的缺口）
| # | 组件 | 实现 |
|---|------|------|
| ⑤ | NegativeCapture（实时负例捕获）| signals kind=negative → 即时落 habit 雷区条目（conf 0.45，幂等）|
| ② | 归档后分析 | SessionSummarizer 接线 chat 结束 → 后台场景记忆（阈值：用户≥40字防烧 token）|
| ④ | 下轮展示学到 | `_make_agent` 注入上次会话场景记忆（memory_store.latest）|
| ⑦ | 弱信号快照 | weak_signal_from_text：试探/微调语句留 custom 快照 |
| ⑥ | 跨会话对账 | `/api/mind/reconcile` 真实 LLM 比对条目 vs 行为（冲突/需更新）|
| ① | 用户主动登记 | `mind_register` 领域工具（对话"记一下"→ user 来源 conf 0.9）|

### 真实链路验证（deepseek-v4-pro，全部 ✓）
1. **⑤ 负例**：POST signals negative"不要用破折号" → manual 落"雷区（标点）：不要用破折号"（habit, conf0.45, 幂等防重复）✓
2. **② 归档**：12 条消息真实会话 → 场景记忆落库（含"克制冷静不堆砌形容词"偏好 + 进度 + 决定）✓
3. **④ 跨会话**：新会话续写第三章，延续"克制、氛围先行、白描"风格 ✓
4. **① mind_register**：agent 自主识别"记一下" → 调工具登记"对话短句≤10字" → style 条目 conf0.9 ✓
5. **⑥ 对账**：真实 LLM 调用 11.7s，当前无冲突返回空 ✓

### 真实测试暴露的问题
- **预存重复数据**：manual 里"叙事克制少用感叹号"3 条重复（用户反复手写）→ 印证 §12.18"自然语言条目膨胀需元数据收敛"——后续可做重复合并（S55 backlog）。
- **并行智能体协作**：另一智能体并行做 S54 skillgen，其提交 78021f0 把我改的 app.py 一起提交但漏了 mindup.py（半坏）→ 我补提交 d50ef9f 修复，HEAD 自洽。
- **测试隔离**：归档摘要后台线程会抢测试假模型的调用 → 阈值过滤短对话（≥3 消息且用户≥40字）解决。

### 验证
- align 测试（排除另一智能体半成品的 test_skillgen）46 个全过；app 147 个全过；ruff/mypy 全绿。
- 注：test_skillgen.py 是另一智能体 S54 的半成品（502），非本次范围。

## S55 从 Hermes Agent 借鉴：差距分析 + 4 条行动（已完成 ✅）

### 背景
研究 Nous Research 的 Hermes Agent（自改进通用 agent）。它最独特的是"closed learning loop"（技能从经验创建、使用中自改进、跨会话回忆、用户建模）。与我们的心智模型对比，4 个机制值得借鉴（其余多后端/多平台/计费/多 provider 插件 = YAGNI 不做）：

### 差距分析与行动（按性价比排序）
| # | 行动 | Hermes 来源 | 价值 |
|---|------|------------|------|
| 1 | **心智条目合并规则**：新增前查同类（同 category+关键词重叠）→ 合并进现有条目（内容拼接+置信度提升），不新增碎片 | 后台审查 prompt 的"类级 skill 形状，非一次性窄条目" | 治 S53c 实测发现的"叙事克制×3"重复 |
| 2 | **后台学习审查**：章节落盘/轮末 fork 轻量审查"该更新心智条目/登记伏笔？"（隔离、不碰主对话）| background_review.py 每轮 fork 自问该不该存 | 补"主动学习"环节（现在是被动等信号）|
| 3 | **注入块分层缓存**：stable（跨会话）/session（会话内）/volatile（每轮易变）分档组装，长会话省重复 token | system_prompt.py 三档缓存分层 | 50 万 token 一轮的现实 |
| 4 | **skill 描述截断守卫**：入库时检测描述是否超注入截断限，超则截断/警告 | is_skill_description_truncated_for_prompt | 防静默路由失败 |

### 不该学（YAGNI）
多记忆 provider 插件 / 多平台(Telegram等) / 多后端(Docker/SSH/Modal) / 计费账号 / skill bundles。

### S55 完成记录（4 行动全部落地 + 真实链路验证）

**行动 1 条目合并 + dedupe**：
- `ManualStore.merge_add`：同 scope+category 且双字关键词重叠 ≥3 → 合并进现有条目（内容拼接去重+置信度 max+活跃度 high），锁定不合并
- `ManualStore.dedupe`：贪心两两合并清理历史重复
- **阈值调优（实测）**：重叠阈值 2→3——"感叹号 vs 破折号"共享"克制/少用"2 个通用词被误合并，提阈值后正确区分同主题/仅共享通用词
- 真实数据：清理"叙事克制少用感叹号×3"脏数据，修复被激进合并污染的条目

**行动 2 后台学习审查**：
- `_review_for_learning`（章节落盘后）：轻量 LLM 审查本章揭示的新偏好 → merge_add 进心智
- 真实链路：学习审查提炼偏好 ✓ / 归档摘要 19 条消息落库 ✓
- **修复 bug**：`summarizer=SessionSummarizer(model)` 在 `model=model or RetryingModel()` **之前**实例化 → 真实运行时 model=None 致归档失败（测试注入 fake model 掩盖）。model 初始化移到依赖组件前。

**行动 3 注入分层缓存**：
- skill 索引+内容块按 `skills.revision()` 签名缓存（增删改自动失效，上限 16 防膨胀）
- **修复 bug**：revision 签名漏 content/example 列 → 改内容缓存不失效。补全 6 列。

**行动 4 描述截断守卫**：
- skill 描述超 100 字入库截断（防索引撑爆/静默路由失败），add/update 双守卫

**验证**：align 60 + app 149 全过；ruff/mypy 全绿；真实链路（归档摘要/学习审查/合并/dedupe）全部实测通过。

## S56 C 架构：主循环规划 → 干净写作调用（已完成 ✅）

**背景（主人讨论定案，接 S55 上下文对比实验）**：
- 实验（benchmarks/context_compare）：v3 证明单次写作 A/B/C 质量接近（噪声在短上下文不毒）
- 主人关键洞察：**毒化来自同会话多次写作的累积**（跨轮次矛盾/要求被模型自身味道压过），
  不是单次长上下文 → 选 **C（分离）**：主循环规划 + 干净写作调用
- 主人深化：写作调用的信息由**主循环决定**（它是唯一看过全部信息的一方）——
  主循环产出意图 + **精选参考（原样摘录，不概括）** → 传给写作调用

**落地（S56）**：
- `write_chapter` 工具支持**意图模式**：content 可选，新增 intent（写作意图）+
  references（主循环精选参考）——正文由**干净写作调用**生成（无历史/无工具记录）
- `WritingTools` 注入 model + skills_store + style_prefs（文笔 skill 按文风偏好匹配）
- 干净写作上下文 = 写作系统提示 + 意图 + 参考 + 文笔 skill（不带对话历史/工具记录/旧章节）
- 降级链：写作模型缺失/失败/空正文 → 报错让主循环重试或直写（content 模式不变）
- DEFAULT_SYSTEM 引导：连续写作优先意图模式（先确认意图→摘录参考→write_chapter intent）
- toolkit 装配：build_toolkit 透传 skills_store/style_prefs；session_plan 提前计算

**验证**：
- pytest：test_tools_writing（5：意图模式/直写/无model降级/空正文降级/缺参提示）
- 全量回归通过；ruff/mypy/format 全绿（112 文件）
- **真实链路**：DeepSeek 意图模式生成 901 字正文——细节具体/画面感强/对白自然/
  零设定冲突（贴合意图+参考，干净上下文效果实证）

**架构意义**：主循环=决策+信息过滤（看过全部），写作调用=只写（干净上下文）。
心智(collab/style/habit)→主循环；文笔 skill→写作调用；类型 skill→主循环（后续）。

## S57 skill 三改进：轻量写作标记 / 笔记约定 / target 分流（已完成 ✅）

**背景（主人讨论确认三项）**：
1. "直写"模式与 patch_chapter（定点编辑）语义混淆 → 改"轻量写作"
2. 沙箱笔记区：不新增第 3 个文件工具（复杂度/token 顾虑）→ write_file 加 `笔记/` 约定
3. 类型 skill vs 文风 skill：统一表 + target 字段分流（不全集/子集，不分两集合）

**落地**：
1. **轻量写作**：write_chapter 直写模式返回/描述改"轻量写作（直写）"——语义=短段落/
   快速产出/写作引擎不可用兜底，与 patch_chapter（改既有文本）正交
2. **笔记约定**：write_file 描述加"`笔记/` 前缀路径=纯文档，不触发图谱/伏笔/学习审查"，
   与 write_chapter 的"落书库+图谱"明确区分——零新增工具
3. **target 分流**：writing_skills 加 target 列（writing/main/both，ALTER 兼容）：
   - writing → 写作调用注入（文笔/叙事技巧）
   - main → 主循环注入（类型/结构指导）
   - both → 两者（节奏控制种子标 both）
   - skillgen 候选带 target；draft 转正保留 target；select/render 按 target 过滤

**验证**：
- pytest：test_skill_target_routing（main/writing/both 分流）+ draft target 转正 + 全量绿
- ruff/mypy/format 全绿（112 文件）
- 真实链路：直写返回"轻量写作" ✓ / 意图降级 ✓ / write_file 笔记约定 ✓

**架构意义**：skill 统一表（全集）按 target 分流——文风 skill（写作调用）+ 类型 skill
（主循环）同载体管理，生成/合并/心智联动全复用；类型 skill 后续生成器扩展即可。

## S58 类型 skill 生成器 + 多章毒化实验验证（已完成 ✅）

**一、类型 skill 生成器（主人讨论定案：类型 skill 给主循环看）**：
- `GENERATE_PROMPT_MAIN`：主循环视角的结构/类型/节奏/组织指导（不是句子技法）——
  类型惯例（"爽文先压制再爆发"）/ 节奏节拍 / 组织规则 / 探索信号
- `SkillGenerator.generate_main()` + API `mode=main`——候选强制 target=main
- 真实链路：斗破式原文 → 3 条结构指导（先压制后爆发/跳过枯燥修炼期/标志性台词引爆）✓

**二、多章毒化实验（验证 C 架构免疫累积毒化）**：
- `benchmarks/context_compare/multi_chapter.py`：同会话连续写 3 章，A 累积 vs C 干净
- **结果**：A 累积 3 次幻觉（第1章抓错位置"女贞路碗柜"+第3章设定矛盾"德思礼送站台"），
  连贯 1-3 波动；C 干净 **0 幻觉**、位置/设定全对、连贯稳定
- **结论**：同会话累积确实毒化（长上下文+噪声稀释定位）→ C 每章干净写作免疫——
  **S56 选 C 的正确性被实证**
- 附：BareLLM 偶发空响应（flash 高并发）→ 实验加空返回重试兜底

**验证**：test_skillgen 10 全过（含 main 模式/API）；门禁绿（112 文件）

## S56 两段式定位：search_chapters 词表批量 + 参数类型宽松（已完成 ✅）

### 背景
编码智能体的标准定位做法 = 两段式：① 大量关键词匹配 → 统计每章数量/位置；② 读取指定位置附近上下文。项目已有 `search_chapters`（单关键词）+ `read_context`（锚点精读），缺第一段的"词表批量"。

### 实现
1. **search_chapters 加 keywords 词表参数**（逗号/顿号分隔）：逐词统计每章命中 → 返回各词分布 + 聚合 + 上下文片段（可作 read_context 锚点）。单关键词用法完全向后兼容。
2. **参数类型宽松**：fragment/before/after 从 string 改 number；`protocol.validate` number 兼容数字字符串——**模型常把数字参数传 int，原 string 校验拒绝导致工具调用失败**（真实链路两次暴露：fragment=30、before/after=2）。
3. 两段式闭环：词表字面召回（机制硬编码）→ read_context 精读（内容判断交给模型/用户）。

### 真实链路验证（deepseek-v4-pro，3 次端到端全成功）
1. "感官描写"词表（铁锈,樟脑,冷,雾,钟,汽笛）→ 分布表 + 第一章/第四章精读 → 按嗅觉/听觉/触觉/视觉分类引用原文
2. "打斗动作"词表（攥,蹬,探,撞,砸,掐,扣）→ 15 章 41 次 + 各词分布表 + 第四章功能分析（撞=环境暴力/探=谨慎侵入/攥=紧张锚点，发现动作弧线）
3. "怀表"→ 16 章 49 次 + 三线交叉对比（发现三个"第一章"是不同叙事线，设定一致性分析）

### 设计哲学守则
- 机制硬编码（词表匹配/聚合/类型校验），内容自然语言（词表由 agent/用户给）
- 不做"语义定位"过度工程——字面召回 + 上下文精读分层（召回确定性、判断靠模型）
- 向后兼容（keyword 单关键词路径不变）、YAGNI（不新建工具，升级现有）

### 验证
align 60 + app 20 全过；ruff/mypy 全绿。

## S58 项目智能体简介 + 会话上下文模式 + 图谱停止注入（已完成 ✅）

### 背景（主人讨论定稿）
主人提出两个关键设计判断：
1. **每项目绑定"智能体简介"**（给 AI 和用户看的项目总览，非读者简介）——补"这本书是什么"的全局总览缺口（此前项目级载体分散在 archived_directions/setting_constraints/world_settings/scene_memories 等表，无统一总览）
2. **图谱不再常驻注入**（网络小说上下文贵）——AI 靠 graph_query 工具按需查

### 实现
1. **项目智能体简介**：`data/<book>/简介.md`（工作区 md 文件，用户可编辑）
   - 内容结构：世界观/主线/角色/基调/已固化设定/进展/注意事项（自然语言）
   - 注入系统提示顶部（常驻定调，skip_inject 可关）
   - API：GET/POST `/api/brief` + POST `/api/brief/generate`（真实 LLM 从现有项目数据提炼草案）
2. **context_mode**（主人需求：有时延续对话、有时独立探索）：
   - `auto`（默认）/ `continue`（显式延续）/ `fresh`（干净：不注入场景记忆+剧情计划）
   - fresh 保留心智习惯+世界事实（简介/设定档）——独立任务不被上次对话绑架
3. **图谱停止常驻注入**：摘掉 graph_injector 系统提示注入；`/api/graph/context` 保留（人可预览）

### 真实链路验证（deepseek-v4-pro）
1. **brief 生成**：从项目数据（怀表16章49次/三个第一章/设定档空）自动提炼总览，**发现真实问题**（"需统一三个第一章版本"、"设定档为空"）✓
2. **brief 注入**：写第六章完全遵循固化设定（两把钥匙/怀表连贯/克制冷峻风格），agent 自主 read_setting×2/plot_list/plan_list 查证 ✓
3. **fresh 模式**：写"沙漠等火车老人"意象练习，零雾城污染、零剧情参考、431字纯意象 ✓（保留心智克制风格=符合设计）

### 封档待解决
**图谱注入瘦身 vs 工具查询**（主人拍板暂不注入，此问题封入计划待后续）：
- 现状：完全不注入，AI 靠 graph_query 按需查（省 token，但 AI 可能"不知道要查什么"——不知道图谱里有第三把钥匙就不会去查）
- 待选：A) 极瘦常驻（高权重主线实体5+事件3，~300字）+ 工具查细节；B) 保持不注入（现状）
- 触发条件：网络小说长书写作时若出现"AI 漏设定"的实际问题再议

### 验证
align 60 + app 20 全过；ruff 全绿；真实链路 3 项全过。

### 注：并行智能体 S57 workflow 包未提交（其 mypy 有错，非本次范围）

---

## S59 工作流扩展包（已完成 ✅）

**背景（主人需求）**：① 固定分析流程（如章节质量分析）② 可迁移改书标准（某作者一套改书打法换书复用）。DESIGN 去留清单原将"工作流"列为降权可选增强包——本次落地。主人拍板：**开源路线**（AGPL 约束解除，但仍不直接搬 DeterminFlow 代码——耦合面问题：拖入 49K 行运行时 vs 只要 ~2K 行骨架）；分支/循环要做（条形分支+嵌套循环常见）；AI 生成优先；前端画布暂不做但定义格式为其预留。

**设计（DESIGN §12.22 已定稿）**：
- **结构化三结构**：顺序 + gate 分支 + loop 循环（非通用 DAG 业务引擎——写作场景用不到任意图/子流程/并发汇聚）
- **节点**：agent（干净单次 LLM 调用）/ script（确定性函数白名单）/ approval（人工确认）/ gate（条件分支）/ loop（循环）
- **条件两种**：硬规则（{{var}} 比较 + AND/OR/NOT + contains，自研解析器）/ 模型判断（自然语言）
- **断点恢复**：任务冻结定义快照；每节点状态落盘 SQLite；done 跳过续跑；loop 记录迭代数
- **失败策略**：auto_retry_count / interval / fail_auto_skip（借鉴 DeterminFlow 设计，重写实现）
- **AI 生成**：workflow_drafts 草稿表 + 人工确认 promote（skillgen 同款闸门）
- **记账**：每节点 token_usage

**实现（packages/workflow，依赖 core 单向）**：
- `definition.py`（WorkflowDef/Node/Edge/FailPolicy + validate）/ `condition.py`（表达式解析）/ `store.py`（SQLite 模板/草稿/任务/节点状态）/ `engine.py`（WorkflowEngine 三结构 + 断点恢复 + 失败策略 + 记账）/ `generator.py`（WorkflowGenerator + NODE_CATALOG）
- 后端接线：`/api/workflows` CRUD + `/generate`（AI 生成→草稿）+ `/drafts/{id}/promote` + `/tasks/{id}` + `/approve`；app.py 组合根装配 engine（runner 闭包注入：agent=干净 LLM 调用 + {{var}} 插值，script=read_chapter/review_chapter/noop 白名单，approval=wait_approval）

**门禁**：ruff 0 + mypy 0 + pytest **334**（workflow 15 + app API 2，全量回归）总闸全绿；前端未动（tsc/eslint/build 保持绿）

**真实链路验证（哈利波特原著第一部，隔离库 data/dev/runs/s59_wf.db）**：
- AI 生成"哈利波特第一章质量把关"——**AI 自主设计**：script读章节→loop(审读→gate→改写→复检)→approval，变量插值（{{chapter_text}}/{{review}}）全部正确
- 真实执行：读章→审读发现**真实设定冲突**（"猫看地图"时间线混淆，硬伤数1）→gate 走改写→改写修复→循环 3 轮（max_iterations 防死循环）→approval 作者确认→approve 后 done
- **真实链路暴露并修复 3 个接缝缺陷**（验证的价值）：
  1. agent 节点拿不到章节内容 → 加 {{var}} 变量插值（_wf_resolve）+ chapter_title 自动附正文
  2. 生成器 prompt 不引导读章节 → 加规则 7/8（先 read_chapter 再 agent，output_key 命名约定）
  3. AI 幻觉章节标题 → read_chapter 模糊匹配（精确→双向包含→第X章号提取）

**遗留（按需后补）**：前端画布（nodes+edges 格式已预留）。

### S59 补充（三项补齐，已完成 ✅）
1. **script 函数扩展**：`write_chapter`（改写结果写回章节，库+盘双写，text_key 引用上游输出）/ `list_chapters`（列章）/ `review_chapter` / `noop` / `read_chapter`（含模糊匹配）白名单
2. **workflow agent 工具**（`tools_workflow.py`，`enable_workflow` 默认关点亮）：`workflow_list` / `workflow_run`（后台执行）/ `workflow_status`（节点级进度）/ `workflow_generate`（AI 生成草稿，人工确认后生效）——写作 Agent 可自主使用工作流
3. **model 型条件真实链路**（`scripts/workflow_model_cond_smoke.py`）：gate 自然语言条件 → `_wf_judge` 真实 DeepSeek 判断生效
   - **真实链路暴露修复**：旧 `_wf_judge` 判定粗糙（模型答"否/不通过"误判）→ 强制首字 是/否 + 否定词优先 + 强肯定词兜底；互斥 model 条件都 False 时走 default 边（无则 (end)）
- 门禁：pytest **338**（+4：script write_chapter 落盘 / agent 工具注册调用 / model 条件冒烟）+ 总闸全绿

## S58c 会话继承 fork（参考 pi forkFrom，已完成 ✅）

### 背景（主人需求）
"默认不继承场景记忆；会话内增加一个'继承'功能——出现一个继承该会话的新会话，且继承链条要清晰。"参考 pi 的 /fork（从历史消息派生新会话，parent 指针链）。

### 实现（复用 pi 逻辑）
| pi 机制 | 我们落地 |
|--------|---------|
| forkFrom: 新 header 记 parentSession + 复制源条目 | `store.fork()`: 新会话 parent_id=源 + 复制源消息（SQLite/InMemory）|
| 会话树 id/parentId 链条 | conversations 表加 parent_id/fork_point |
| /fork 独立新会话 | POST /api/conversations/{id}/fork → 返回 chain=[新,源,源的源...] |
| GET 会话列表 | /api/conversations 返回含 parent_id/fork_point/message_count |

### 与 S58b 配合（默认不继承）
- 普通新会话默认干净（不注入场景记忆/plan）
- fork 出的新会话**需要 context_mode=continue** 才注入场景记忆/计划（用户显式继承时才有）
- 即：fork = 建"带着上下文的新会话"的容器；continue = 注入"进程状态"（记忆/计划）的开关

### 真实链路验证（deepseek-v4-pro）
源会话写《第七章 石墙》→ fork（继承 9 条消息，parent 链条清晰）→ continue 续写第七章后半：
**完美衔接源上下文**（石墙刻字/字在变化/怀表停走伏笔——"怀表开始走针=承接前文停走伏笔"）✓
——这就是"从上次会话接着聊"：fork 提供链条，continue 提供进程记忆，两者合起来 = 继承闭环。

### 待办
- 前端：会话内"继承并新开会话"按钮 + 会话列表链条显示（UI 层，后端 API 已就绪）
- fork 点选择器（参考 pi /fork 从任意历史消息分叉）——当前只支持从末尾 fork，后续可扩展

### 验证
230 测试全过（含 fork 存储/API/链条）；ruff/mypy 全绿（本次 3 文件）。

## S59 叙事树 + 线进度（已完成 ✅，含哈利波特结构测试）

### 设计（主人讨论定稿）
1. **叙事 = 分叉路径树**：节点=叙事状态，边=分叉；探索=树的生长器；锚点=用户标记必经节点；主线=被选中路径
2. **探索可能性 ≠ 支线**（主人纠偏）：未选分叉=探索可能性（留痕可回看）；支线=确实在走的次要线路
3. **线生命周期**（主人讨论）：默认涌现（探索可能性→被推进→升级为线），用户可随时声明；线是稀缺资源
4. **线进度=映射锚**（主人洞察）：结构空间(树)→线性输出(正文)的映射靠"每条线进行到哪"的自然语言一句话（不怕章数漂移）；映射是 AI 创作行为，系统不自动铺平
5. **极简**：一张表+自然语言节点，不做图算法（路径搜索/循环检测是工程思维，写作是生长思维）

### 实现
- StoryTreeStore（story_nodes: content/parent_id/kind root|main|anchor|candidate|subplot|loop/chosen）
- StoryThreadStore（story_threads: name/progress/role/status——线进度=映射锚）
- API: nodes CRUD+choose+anchor / story/tree / threads CRUD+PATCH进度
- 探索接入: explore/archive 选中方向卡→树主线节点（探索=树生长器）
- 注入: 叙事树+线进度（稀疏常驻，锚点完整信息不截断——目的地要清楚）
- 修复: ChatRequest 加 book_id（此前注入用默认 main，多项目叙事树失效）

### 真实链路验证（哈利波特魔法石结构参考、内容原创）
- 建 7 节点树（root + 5 锚点：身份揭示/入学/神秘物品/地下探险/真相）
- 第二章写作: AI 明确说"锚点「身份揭示」已实质性启动，下一步衔接入学守钟阁"——
  **方向收拢向锚点（守钟人学会来信=锚点内容），过程自由（访客/火漆印/信纸细节自创）**
  = 方向约束 + 自由填充，正是目标
- 第一次测试暴露：book_id 未传导致叙事树没注入（AI 说找不到叙事树文件）→ 修复后生效

### 验证
222 测试全过（含 storytree 4 个）；ruff/mypy 全绿。

### 待办
- 前端：叙事树可视化（节点/锚点/主线/支线展示 + 探索选卡入树）
- explore 候选自动入树（未选分支存为 candidate——当前只存了选中的主线节点）
- 多线/时间循环的真实场景测试（当前验证了单主线+锚点）

## F1 前端外壳地基（已完成 ✅）

**背景**：主人决定重开前端（2026-08-06），重要性不亚于后端。外壳设计先行——调研 2026 行业（Noren/Sudowrite/Scrivener/InkOS/Novilot/NovelFork 等）→ 定稿 `docs/FRONTEND-SHELL.md`（三锚点：稿纸主角/操作即表达/功能全退后台）。

**后端小改动（为前端，主人认可"小改动+可解耦"）**：
- `POST /api/chapters`：手动新建空章节（order_index=末尾+1，库+md 双写）
- `DELETE /api/chapters/{id}`：删除章节（库+md 双写删除，幂等）
- 顺手修 S59 预存 mypy 错误：`StoryNodeIn.kind` 收窄为 `Literal`（机制硬编码，非法值 422）
- 测试：test_create_chapter_api / test_delete_chapter_api（app 31 全过）

**前端落地（F1）**：
- **视觉基座**：`index.css` 重写——纸与墨 tokens（暖纸 `#FAF6EF`/暖墨 `#2D2A26`/唯一主色黛青 `#3A5A58`/语义3色）+ 衬线正文（系统字体栈零网络依赖）+ 纸色滚动条
- **壳布局**（`App.tsx` 重写）：顶栏 24px（书名/探索入口占位/四房间按钮/右侧栏开关）+ 章节树（可折叠 32px，新建/删除/双击重命名）+ 稿纸（主角，标题行+字数）+ 底部对话条（纸边批注）+ 右侧写作上下文（可折叠，布局记忆 localStorage）
- **抽屉注册表**（`drawers/registry.ts` + `DrawerContainer.tsx`）：四房间（世界/质量/协作/系统）共用一容器覆盖滑出（180ms），tab 由注册表驱动——新增功能=注册表加行，壳零改动（可扩展性承诺落点）
- **主流程**：对话流式（打字机+工具胶囊+插话/停止）→ 写后刷新章节 → 自动选中最新章；空态="这本书你想写什么？"种子入口（DESIGN 阶段 0）
- **快捷键**：Ctrl+1..4 开四房间 / Ctrl+\ 章节树 / Ctrl+. 右侧栏 / Esc 关抽屉

**验证**：tsc/eslint/build 全绿；真机链路（vite proxy→后端）：新建→列表→删除→md 双写删除 ✓；app 31 测试过。

**待办（F2 起）**：F2 写作上下文（探索/候选裁决浮层/candidates-stream 后端/BubbleMenu）→ F3 世界房间（含叙事树可视化）→ F4 质量+协作（含审读内联标记 check-offsets 后端）→ F5 系统（含工作流面板）→ F6 打磨。候选裁决/内联审读/命令面板三升级点见 FRONTEND-SHELL.md §四。

## S61 心智模型完善：档位 L2/L3 + 活跃度衰减 + context 动态选取（已完成 ✅）

**背景（主人指示）**：检查心智模型实现 → 定取舍：做档位 L2（AI 建议档位）/L3（自然语言生成档位）、活跃度衰减、按本轮相关动态选取；不做会话级心智（主人：用处不大加复杂性）、不做跨会话对账自动周期化（无消费端时自动跑烧 token 没人看，保持手动 API 等前端按钮）、不做弱信号增强（链路已通）。

**一、档位 L2：AI 看心智建议档位（`mindgen.py` + API）**
- `POST /api/mind/agency-suggest`：LLM 读 collab 条目 + 可选档位列表 → 建议档位（level_id+理由；都不合适则给新建建议）；启发式对照（heuristic_agency）始终返回
- `GET /api/mind/agency-suggest`：只读通道（不调 LLM，前端打开面板即可展示规则推断）
- 哲学：建议不自动应用（用户主权），采纳走既有 POST /api/agency；LLM 失败静默降级启发式

**二、档位 L3：自然语言生成档位（`mindgen.py` + API）**
- `POST /api/agency/generate`：用户一句描述 → LLM 生成档位候选（名称/描述/温度钳制 0-1）→ **人工确认后** POST /api/agency/add 落库（对齐 S54 skillgen 候选→确认闸门）
- 宽容 JSON 解析（去围栏/取括号/非法项丢弃）

**三、活跃度衰减（DESIGN §12.18 元数据收敛，`manual.py`）**
- `ManualStore.decay_stale(days_high=30, days_medium=90)`：未锁定条目按最后触达降级 high→medium→low；锁定不降（用户主权）；**不刷新时间戳**（降级不是触达，供下一级继续判定）；不自动删除（冷条沉没，用户手动清理）
- `list()` 惰性执行（披露永远基于最新活跃度）+ `POST /api/manual/decay` 显式触发（返回 cold_entries 供前端展示）
- 披露排序更新：`_key_entries` = 锁定优先 → 活跃度（冷条沉底不占名额）→ 置信度

**四、按本轮相关动态选取（DESIGN §12.17，`mind.py`）**
- `MindPlanner.plan(book_id, base_agency, context="")`：context=本轮用户意图，心智块不再静态取前 5——`_key_entries` 按双字窗口关键词重叠数动态选（复用 manual._keyword_set），context 为空退化为置信度排序
- `_make_agent` 加 context 参数，chat/chat_stream 传 `req.message`

**验证**：
- pytest：align 85 + app 144（排除真实网络 test_complete/deepseek/codex）；新增 test_mindgen 8 + test_mind 增 4 + test_manual 增 1，全绿
- 真实链路（deepseek-v4-pro）：
  1. L2：collab"直接写别啰嗦，一口气给我全章，不要反复确认" → AI 建议 **default-4 自主发挥**（引用原话）；启发式对照 heuristic=2（"确认"命中降档 -1 抵消 +1）——**实证启发式不理解否定，L2 语义判断的价值**
  2. L3："多给方案别直接写，每章两千字左右" → 3 候选（严格待命 0.2/多案供选 0.5/创意提案 0.8）区分明显 → 确认 add 落库 order=5 ✓
  3. decay：days=0 强制 → 8 条降级 + cold_entries 返回 ✓
  4. **chat context 动态披露**：请求"写一段打斗场景" → 心智块披露顺序"打斗场景要多用动词"（conf 0.5）**排在**"对话句子特别短促"（conf 1.0）**前**——context 相关性生效 ✓
- 总闸 ✅（pytest 357 + tsc + eslint + build）

**踩坑/观察**：
- 启发式 `_infer_agency` 否定误判："不要反复确认"里的"确认"命中降档关键词（-1）抵消"直接写"（+1）→ 净 0。**不修**（启发式只是无 LLM 的 fallback；语义判断交给 L2；修补规则会引入新误判，违背"相信模型"哲学）。观察记入本台账。
- SQLite 并发写锁：并行 DELETE + 后台任务竞争 → database is locked 500；串行重试/重启后恢复（既有行为，非本次引入）
- 总闸失败项顺带修复：test_skills.py 预存 I001 import 排序 + test_switches.py 预存 format 差异（自动修复）
- 验证污染已清理（测试 collab 条目/《巷战》章节/多案供选档位删除；误降级的 5 条真实条目活跃度恢复 high）

## S60 skill 注入瘦身 + 按需细看 + 写作点名（已完成 ✅，DESIGN §12.24）

### 背景（主人质疑触发审查）
主人："理论上技能一开始注入的时候也只注入了个名字吧？这也会导致混淆吗？不是智能体
自己选用的技能再细看吗？"——审查实现后发现与主人记忆不符：
- 主循环实际注入 索引 + ≤3 条完整内容（且 skill ≤5 条时全量注入全文）
- **有注入无工具**：智能体无法按需细看任何一条 skill 完整内容；注入的 3 条是
  style_prefs 隐式匹配，主循环无法指定"这次用哪条技巧"（对齐 S58 图谱教训）

### 定案（主人确认方向）
1. **主循环只注入全部技巧索引**（名字+描述，target 不限——决策者看全部才能点名）
2. **新增 `skill_lookup` 工具**（对齐 graph_query）：按名细看完整内容（精确优先/
   包含兜底/未命中列可用名字自纠）
3. **`write_chapter` 加 `skills` 参数**（意图模式）：主循环点名 → 干净写作调用只注入
   点名技巧；未点名保留 style_prefs 自动匹配兜底

### 实现
- align：`render_skills_by_name`（按名精确匹配渲染完整内容，禁用/未命中忽略）
- tools_domain：`make_skill_lookup_implementer`（skill_lookup 工具）
- toolkit：skill_lookup 注册（enable_domain 内，skills_store 非 None 时）
- tools_writing：`_clean_write(skill_names)` + write_chapter 解析 skills 参数（逗号分隔）
- app：主循环注入改 `render_skill_index(target="")`（全部索引），删 render_skills_content
  注入 + 缓存改为只缓存索引块；清理未用 import

### 验证
- pytest **357 全绿**（338→357：+19 = 点名渲染/工具/写作参数/注入断言更新；无回归）
- ruff/mypy 全绿（5 文件）
- **真实链路（deepseek-v4，临时库隔离）**：
  1. agent 自主 `skill_lookup` 细看节奏控制 ✓（看到索引→主动查完整内容）
  2. agent `write_chapter` 意图模式 + skills 点名 → 落盘成功 300-428 字 ✓
  3. agent 准确列出全部技巧索引，并主动说明"可用 skill_lookup 细看" ✓（机制自解释）
  4. 正文明显运用点名技巧（短句加速/停顿制造张力/化用例句）✓

### 架构意义
skill 从"注入即内容"改为"索引常驻 + 按需细看 + 写作点名"——与图谱按需查询同一哲学；
主循环=决策者（看全量索引），写作调用=干净执行者（接收点名注入）。全局池 skill 再多
也不怕（索引轻、内容按需），作者资产随人走天然成立，零新增表结构。

### S60 深化（S61 定案：写作调用不自行选技巧）
主人追问："skill 不是改成全量列表了吗？三个 limit 是啥意思？"——审查发现 S60 只改了
主循环侧，写作调用兜底仍走 S53 的 `render_skills_content`（prefs/tags/limit=3/保底
自动匹配）。主人定案：**写作调用是被执行方，所有注入由主循环点名决定，不能有自己的
选择规则**。
- 删除 `select_skills_for` + `render_skills_content`（S53 渐进式披露自动匹配全删，
  含 ≤5 全量/limit=3/tags 匹配/prefs 匹配/保底 3 条——人类预设规则）
- `_clean_write` 未点名 → 不注入任何技巧（干净）；点名 → 只注入点名技巧
- 保留：`render_skill_index`（主循环索引）+ `render_skills_by_name`（点名注入）——
  写作调用注入只剩主循环点名这一条路
- `style_prefs` 保留作心智块注入/主循环决策用（不直接驱动写作调用）
- 验证：pytest 346 全绿（删旧测试后 357→346）；ruff/mypy 全绿；真实链路——
  未点名不含"叙事技巧" ✓ / 点名只含"节奏控制"不含"镜头感" ✓

## S62 哲学审查修复：去垃圾补丁（已完成 ✅）

**背景（主人指示）**："虽然我们在做这个智能体的时候再三强调要符合哲学，但写这个项目的 AI 在很多地方采用了笨拙的硬编码导入、不解耦的设计、强制性的护栏——审查项目找到这些问题，全部修复。"

**审查方式**：三路独立 subagent 审查（app / align+explore+check / core+graph+template+workflow）+ 主会话复核验证。判据：DESIGN §1（机制硬编码/内容自然语言、极简方法论、相信模型、单向依赖、模型无关、YAGNI）。安全底线（沙箱/幻觉检测/超时）与过程控制（循环/重试/压缩）确认为设计允许，未动。

### 修复清单（全部落地 + 总闸全绿 346 passed）

**C 类 强制性护栏（哲学红线）**：
1. **规则编译器 LLM 化**（check/rules.py）：原 3 正则模板+术语白名单，模板外规则静默丢弃（偏离 DESIGN"内置编码 agent 编译"）。新 `compile_with_model`：LLM 解析用户自然语言 → 结构化指令（forbidden/term/sentences/unknown）→ 确定性执行器硬编码；识别不了**明确告知**用户（不静默丢）。真实链路：字面规则"不要用破折号"命中 ✓；语义规则"少用形容词堆砌"正确提示超出字面检测能力 ✓
2. **删除 NegativeCapture 正则层**（mindup.py）：原 7 正则+守卫补丁猜用户话语机械落雷区（模板外漏捕+"不要停"子串误吞）。负例信号原文本就在 signals 表（不丢），"是否构成雷区"是内容判断 → 交给轮末提炼器 LLM/学习审查。实测 negative 信号只进表不机械落条目 ✓
3. **删除 skill 描述写入截断**（skills.py SKILL_DESC_LIMIT=100）：用户/模型内容被腰斩不可恢复 + 草稿/正式路径行为不一致。改为**存储永不截断**（内容主权），索引渲染层展示省略（"…（全文见 skill_lookup）"）
4. **档位启发式静默应用移除**（mind.py _infer_agency + app.py）：S61 已证"不要反复确认"的"确认"抵消"直接写"（否定误判）。删除关键词启发式推断——用户未显式指定档位时一律用**已存档位**；推断只经 L2（/api/mind/agency-suggest LLM）呈现，不自动应用（用户主权）。chat 实测档位保持 default-2 未被静默改 ✓
5. **弱信号关键词层删除**（weak_signal_from_text）：试探语句作为 custom 信号原文进表，判定交给提炼器 LLM
6. **workflow 校验补齐**（definition.py）：validate() 补**有向环检测**（DFS 三色，loop 豁免）+ **条件语法校验**（DESIGN §12.22 承诺落地）；from_dict 未知 kind 不再静默变 agent（显式报错）；condition 非数字字符串关系比较不再按长度回退（"abc">"d" 伪结果）——求值失败走默认分支；死代码 normalize_condition_expr 删除；"孤立 NOT"检查修正（tokenize 已规范化为 NOT）

**B 类 不解耦**：
7. **ToolContext 收敛**（toolkit.py）：build_toolkit 15 个 Any 命名参数 → `ToolContext` dataclass（依赖收敛单对象，签名稳定）
8. **注入块表驱动**（app.py _make_agent）：11 块 if 链 → prepend/append 块列表（顺序/去留/优先级可读数据）；顺带修复 L5：伏笔渲染硬编码 "main" → book_id
9. **后台任务 typed**（app.py BgTask）：元组魔法派发（task[0]+len 判断+位置解包，未知任务静默丢弃）→ dataclass + kind 字段分派
10. **explore_direction 工具吃维度内容化**（tools_extras.py）：此前绕过 DimensionStore 回落 DEFAULT_DIMENSIONS（S50 只接一半）——注入 dim_store
11. **core retry 厂商错误表标注边界**（retry.py）：Node/undici 生态文本特征集中注释说明（未来多厂商由适配器扩展，core 不背厂商表——YAGNI 不移动）
12. **core 取消钩子显式协议**（loop.py）：getattr 探测 → `Cancellable` Protocol（runtime_checkable isinstance）
13. **事件协议声明补全**（events.py）：user_text/aborted/record 补入 GENERIC_EVENT_TYPES（此前 loop 发出但未声明，2 种无人消费已记录）；删除无调用方的 register_hook/run_hook 死机制

**A 类 硬编码导入/死代码（零风险机械清理）**：
14. 深路径导入统一走包公共 API（10+ 处：run_roleplay/run_exploration/IntentUnderstander/render_plan/Message/Conversation/NodeResult 等，各 __init__ 早已导出）
15. `_validate_thinking` 私有符号 → 公开 `validate_thinking` + models/__init__ 导出（2 处跨模块导入）
16. 函数内重复导入 Message/json 删除（顶部已有）；app.py PlotIn 重复定义删除
17. align/__init__ `__all__` 悬挂 `DEFAULT_MOOD_DIMS`（from * 会崩）→ 删
18. skills.py 破损 `delete_draft`（DELETE+fetchone 恒 False、无 commit、无调用方）→ 删
19. inject.py 死模块（ManualInjector/MemoryInjector 生产未接线，S53 后心智块替代）→ 删
20. explore strategy.py EXPLORER_DIMS / direction.py DIMENSIONS 旧名别名（无消费者）→ 删
21. core 演示工具（echo/add/register_builtins）从公共 API 摘除（保留 core/tools.py 供测试/demo 深路径）
22. retry RETRYABLE 旧名别名链清理；Model/StreamModel 协议从 loop.py 移到 protocol.py（消除 retry→loop 模块耦合）
23. graph/template `model: object` + 4 处 type: ignore → `model: Model`（绕过协议）；graph/schema `extraction: object` + getattr → `Extraction` 类型
24. manual.py docstring "交集≥2" vs 代码 ">=3" 文档失实修正；`_keyword_set` 私有跨模块 → 公共 `keyword_set`；skills revision() 签名补 tags/target
25. app pyproject 依赖补齐（此前只声明 core+graph，实际 import align/check/explore/template/workflow——拆包即崩）
26. core 事件协议/其他死代码清理（EventEmitter hooks、demo 导出）

### 验证
- 总闸全绿：pytest 346 + tsc + eslint + build ✅（ruff/mypy/format 0 错误）
- 真实链路（deepseek-v4-pro）：规则 LLM 编译（字面命中/语义明确提示）✓ / chat 注入表驱动+档位保持 ✓ / negative 信号只进表 ✓
- 验证污染已清理（测试章节/信号删除）

### 观察
- app.py 3275 行巨型组合根（135 端点 + 后台 worker + 注入装配）未拆 router——纯结构重构、diff 巨大、与前端 F 系列并行工作冲突风险高。经 ToolContext/BgTask/注入表驱动已大幅瘦身；拆 router 建议独立阶段（S63+）单独做，与前端错开。
- 规则 LLM 编译耗时 ~90s（deepseek-v4-pro 思考）——成本可接受（规则编译低频、一次性）。

## S63 画蛇添足清理：死代码 mood + 重复收敛 role_card + check_text 退役（已完成 ✅，DESIGN §12.26）

### 背景（主人追问触发审计）
主人："再看一看还有什么画蛇添足、功能重复之类的吗"——全仓审计（工具 50 / API 90+ /
Store 21 / 每包导出 vs 使用对照）发现三类问题：

### 审计发现
1. **mood 死代码**：S13 氛围滑块，S53 内容化+心智模型后失去位置——HEAD 无实例/无注入/
   无 API，仅测试引用（并行会话已删文件，本次确认无残留）
2. **role_play 双通道复制**：工具（tools_domain）与 API（app.py）各自实现同一套
   "角色卡文件→图谱兜底"逻辑（~30 行），会漂移
3. **check_text 弱化版**：S32 写后自查工具，无图谱证据/无章节上下文/默认关；
   S59 workflow 的 review_chapter script 已完整取代（读章节全文+接改写循环）

### 处理
1. mood：确认删除，清理 skip_inject 注释残留
2. `explore/roleplay.py` 新增 `load_role_card(workspace, graph, role) -> (role_card,
   state)`——角色卡加载收敛一处，role_play 工具与 /api/role/play 都改调它
3. check_text 退役：删 make_check_implementer + 注册 + 测试；审读收敛到
   /api/check（人用，带证据+时序）+ workflow review_chapter（agent 用）

### 验证
pytest 346 全绿；ruff/mypy 全绿。

### 哲学
能力双通道（agent 工具 vs 人用 API）是设计意图，但通道内实现逻辑共享不复制
（复制=漂移源）；被更新的机制取代的旧通道直接退役不留残废版（残废版=画蛇添足）。

## S62b 一致性护栏：时间/命名轻量引导（已完成 ✅）

**背景（主人讨论）**：老用户反馈三个跨章节问题——①时间线矛盾（AI 随意编"几天前"，线索回收时与主线冲突）②衔接矛盾（出教室又回教室/被打飞还能放纸条）③命名不一致（公寓→老楼）。主人判断：章末时空快照方案本质是一阶马尔可夫，管不了远距时空点，且过度设计；**问题不大，用轻量引导即可**。并纠正我的过度设计："必须承接上一章结尾/禁止位置跳变"是强制护栏——切视角/跳场景/倒叙是合法叙事，不能限制。**护栏边界：只防"与已写内容冲突"，不约束表达方式**。

**落地（DEFAULT_SYSTEM 加一段行为底线，~150 字，S62b）**：
```
【一致性】只约束与已写内容的冲突，不限制叙事手法（切视角/跳场景/倒叙自由）：
时间：不虚构可能与全文冲突的具体日期；确需具体日期（倒计时/跨章线索）时
先 search_chapters 检索"几月/几日"类引用匹配，冲突则用模糊表达（"几天后"）。
命名：写到已出现的人物/地点时，用其既有名称（不确定时 graph_query 确认，
图谱为准）——同一地点不因视角/场合换名。场景切换/视角切换自由，无需交代。
```

**设计要点**：
- 时间默认模糊（零操作、零风险）→ 仅关键节点触发 search_chapters 字面匹配（日期写法统一，字面检索可行）
- 命名以图谱为准（地点是语义级——公寓=老楼需 graph_query 实体名统一，字面检索查不到）
- 衔接矛盾不靠"必须承接"护栏——模型 read 上一章自然看到结尾；切视角/跳切完全自由
- 检索接 S58 哲学：graph_query/search_chapters 按需查，不注入事实只注入决策规则

**真实链路验证（deepseek-v4-pro）**：
- 时间：写"几天前埋的线索"回收 → 模型默认模糊（"几天前""一炷香的工夫"），未编造具体日期 ✓
- 切视角：船夫视角跳切（码头修船）→ 完全自由，未被"承接上一章"约束 ✓
- 命名：沿用码头/江心楼/旧书店既有名，细节全部来自已写章节（AI 自标"未新增"）✓

**门禁**：ruff/mypy/测试全绿；验证章节已清理。

## S65 互动推演扩展包 anyspark-play（已完成 ✅，DESIGN §12.27）

**背景（主人讨论定稿）**：主人提议"推演小说"功能——互动小说式推演树玩法：从某场景
切入、扮演某角色、每步给多个候选行动、用户选择后剧情推进、继续给选项……形成推演树。
用途：灵感来源 + 互动玩法（有用户喜欢这种玩法）。与正文探索 explore 的区别（主人确认）：
探索回答"怎么写"（方向卡，上帝视角单轮），推演回答"写什么"（具体剧情，第一人称多轮）。
**主人拍板：做成独立扩展包 anyspark-play，与 explore 平级区分**；三点确认：自用灵感
工具 / 导出灵感卡接 write_chapter 参考 / 单路径推进 + 可回溯分叉。

**策略修正（主人要求）**：固定策略不硬编码——选项由模型自由发挥生成 3-5 个差异化
候选行动（提示词引导方向，非代码固定"最稳妥/最激进"标签）；**自定义位是唯一硬编码**
（选项列表末尾始终有"自定义行动"输入位，用户任意文本即作为所选行动进入结算）。

**落地**：
- `packages/play/`（anyspark-play==0.0.1，依赖 core + explore）：tree.py（SQLite 推演树
  sessions/nodes/options，单连接+锁对齐项目 store 模式）+ engine.py（创建/选择/回溯/终止/
  导出，每轮 1 次 LLM 调用，轻量上下文=角色卡+当前 scene）+ export.py（路径导出灵感卡 md）
- 装配：app.py 7 端点（POST /api/play/sessions、GET 列表/详情、POST choose/branch/stop、
  GET export）+ ChatRequest.enable_play + ToolkitContext.play_engine + tools_domain
  make_play_implementer（play_start/play_choose/play_status/play_export，enable_play 默认关）
- 异常分层：ValueError（角色卡缺失/非法操作）→404/400；RuntimeError（模型生成失败）→502
- 测试 9 个：创建/选选项推进/自定义输入/回溯分叉/终止导出/无卡报错/深度上限/API 全链路/错误路径

**真实链路（deepseek-v4-pro）**：建卡→创建会话（模型自由生成 5 个差异化选项：查证/打听/
调档/静候/对比）→选选项（结算老周反应+新选项）→自定义输入（"把烟盒递给老周套话"→结算
引出"深色大衣陌生人"线）→回溯分叉（根节点重生成 5 个新选项，原选项保留）→导出灵感卡 md
（路径完整可作写正文参考）。全程自然无幻觉。

**并行会话冲突处理（多会话纪律实测）**：本阶段期间并行会话在开发 anyspark-review（评审团，
也标 S64），共同修改 app.py/toolkit.py/pyproject.toml。处理：①编号让位 S64→S65（防文档
冲突）②提交前 git status 逐文件核对归属 ③混合文件用"备份→checkout 重建→恢复并行改动"
分离暂存（只提交我的 hunk，工作区保留并行改动）④恢复并行会话被误 checkout 的改动
（app.py 的 review import/ReviewPanelRequest/review_panel/两个 review 端点 + toolkit 的
review_panel 字段/工具注册——期间踩坑：grab 提取块过宽复制了 _bg_worker 等中间代码，
F811/no-redef 后精确修复）⑤不提交 scripts/gate.py、tools_review.py、packages/review/。

**门禁**：pytest 全量（app 148 + 其他包 190 + play 9）绿；ruff/mypy 我的文件全绿（app.py
仅剩并行会话的 I001 import 排序问题不碰）；flaky 已确认：test_manual_decay_api 全量跑偶发
失败（时间戳竞态，单独跑两次通过，与本次改动无关）；gate.py 全量门禁被并行会话未完成
的 review 包 mypy 错误卡住（预存，非本提交范围）。

## S64 拟人化评审团扩展包 anyspark-review（已完成 ✅，DESIGN §12.28）

**背景（主人拍板）**：主人展示自研高级时间线辅助写作 agent（"还蛮好的"）——14 位拟人化
评审员（YAML 人设）+ 并发评审 + 主席汇总报告。评估结论：**评审团机制不必要（YAGNI），
拟人化呈现值得做**——用户喜欢"拟人化评审员 + 报告"的体验形态。做成独立扩展包。

**设计定稿**：
- 与 check 分工：check=确定性硬伤规则引擎（客观事实，不动）；review=人格化评价（体验）。
  **硬伤层复用 check**——逻辑审校评审员注入 check_report 硬伤清单逐条核实，拟人层不产生
  新事实（防人格漂移污染客观事实）
- context_keys 按需注入外部上下文（check_report/foreshadow），取不到自动跳过不阻断；
  优于参考项目的布尔 needs_knowledge
- 综合分 = 确定性加权平均优先（维度齐时不用 LLM 自报总分，防乱打）；主席汇总失败降级
  启发式（不挂死）；每评审员独立超时 90s；宽容 JSON 解析（fence/噪声/平衡结构）

**落地**：
- `packages/review/`（anyspark-review==0.0.1，依赖 core + pyyaml==6.0.2）：
  defs.py（ReviewerDef/ScoreDim/ReviewResult/ReviewReport，render 完整版 +
  render_compact 紧凑版给 agent）+ parse.py（宽容提取/评分越界过滤）+ panel.py
  （ReviewPanel YAML 加载/并发编排/汇总降级）+ prompts.py（提示词内容资产，
  per-file-ignore E501 对齐 skillgen 先例）
- 内容：reviewers/ 5 位激活（编剧/文学编辑/逻辑审校/爽文读者/挑刺王）+ 1 位默认关
  （伏笔审计员，context_keys=[foreshadow]）；用户自定义 data/reviewers/ 覆盖系统同名 id
- app 接入：POST /api/review/panel（自动组装 check 硬伤 + 关键点图谱上下文）+
  GET /api/review/reviewers + panel_review agent 工具（无条件注册，对齐 explore_direction；
  S63 教训：默认关的工具=没人用的残废通道）；工具实现器事件循环线程安全包装
  （_run_coro_safely：loop 内转线程池，单工具路径不炸 asyncio.run）
- 测试 25 个：YAML 加载/覆盖/坏文件容错/加权平均/宽容解析/并发评审/超时降级/
  上下文注入/指定评审员/渲染（fake model，无真实 LLM）

**真实链路（deepseek-v4-pro）**：POST /api/review/panel 评审雨夜老宅片段（编剧+爽文读者）
→ 综合 5.5/10；**分歧生效**：编剧认为"转身走进雨里"章末反转有力（7.2 分），爽文读者
嫌钩子太软、通篇无爽点憋屈（3.9 分，"兄弟，这章看了个寂寞"）；主席汇总裁决 3 共识 +
2 分歧 + 5 优先建议（外化心理描写/加屋内对话/强化章末钩子等）。拟人化人设到位、报告
可操作。213s（4 次调用：2 评审 + check 硬伤 + 主席）。

**并行会话冲突处理（多会话纪律实测，与 S65 互相印证）**：并行会话开发 anyspark-play 期间
共同修改 app.py/toolkit.py/pyproject.toml。处理：①play 让位编号 S64→S65（文档防冲突）
②我只提交纯我的文件（路径限定 git commit），不带走 play 改动 ③app.py 接入曾被并行会话
checkout 冲掉、他们随后恢复（他们记录②），我确认后直接复用未重做 ④总闸被 review 测试
文件撞名卡住（check 也有 test_review.py）→ 改名 test_review_panel.py ⑤提交拆两次：
先包本体（183db70），后 app 接入+DESIGN+根注册（8e9f…）。

## S67 路径探索：叙事树节点之间串联的小方向探索（已完成 ✅，DESIGN §12.29）

**背景（主人讨论）**：整本书大方向已定后，"小方向探索细腻度"——叙事树节点之间怎么
串联（A→B 过渡）是真实缺口。主人追问节点要不要分级：**结论不分级**（树的 parent_id
已表达层次；kind 角色标签够用；分级=刚性约束违背哲学；细腻度靠探索上下文粒度）。
主人拍板"你自己分析收益风险后决定"→ 实现者自决：放 explore（机制同构）、自然语言
起终点为主+可选节点 ID、策略不硬编码（单次调用自由生成）、用户判别、archive 显式落树。

**落地**：
- `explore/path.py`：PathCandidate（events 事件链/note/style）+ PathExplorer（单次调用
  JSON 宽容解析）+ explore_path；__init__ 导出
- app：POST /api/explore/path（from_desc|from_node_id → to_desc|to_node_id，约束合并
  项目档案，n=2-6，archive_index 显式落树=事件链写叙事树 candidate 挂 A 下）
- agent 工具 path_explore（enable_domain 默认开：章节间过渡/情节点连接/卡文找方向）
- 测试 8 个（explore 5 + app 3：候选解析/宽容降级/节点 ID/落树/错误路径）

**真实链路（deepseek-v4-pro）**：起终点自然语言 → 4 条路径全部不同思路（直接推进：
码头对峙即相认 / 多层铺垫：船票水印→退休售票员→旧合影→赴约 / 意外反转：匿名警告→
废弃仓库→搏斗→反转相认 / 旁支绕行：老同事→码头工人纪念买票→替父赴约→落泪相认），
每条带事件链+note+style ✓；从叙事树节点出发 + archive_index=2 落树 → 4 个中间事件
链式写入树（candidate 挂 A 下）✓。

**并行会话协调**：并行会话做 httpx2 迁移又标 S66（app/pyproject、cli_chat.py）——
编号让位 S67；benchmarks/、cli_chat.py 为并行改动不提交；DESIGN §12.28（评审团）
留在工作区归并行会话。

## S66 httpx2 迁移（已完成 ✅，工程性条目划除）

**背景**：PROGRESS backlog "httpx2 迁移（等 starlette 原生支持）"。2026-08 查证：
starlette 1.3.1 起 TestClient 已原生支持 httpx2（优先 `import httpx2 as httpx`，
httpx 1.x 回退并 deprecated——测试输出一直有 `install httpx2 instead` 警告）；
starlette 1.4.1 官方 [full] extra 已改 `httpx2>=2.0.0`。**等待条件满足，落地**。

**落地**：
- packages/app/pyproject.toml 加 `httpx2==2.9.1`（cli_chat 的显式依赖）
- cli_chat.py：`import httpx` → `import httpx2 as httpx`（重命名迁移，API 兼容，代码零改）
- benchmarks（独立环境）：baseline/perf_baseline/core/run_unit 4 个脚本同样改 import +
  benchmarks/pyproject.toml 加 `httpx2==2.9.*`
- TestClient（starlette 内部）自动切 httpx2，无代码改动
- httpx 1.x 与 httpx2 共存（openai 等传递依赖不受影响）；httpx 仍留在锁文件（starlette
  兼容回退 + openai 用）

**验证**：pytest 全量绿（无回归）；ruff/mypy 全绿；总闸 ✅。

**判断记录**：~~Autopilot~~ 划掉候选清单——S59 工作流（loop 循环多章 + gate 质量门 +
approval 人工暂停 + workflow_generate AI 生成流程草稿）已吸收 Autopilot 的全部机制
价值；需要"全书自动连写"时 = workflow_generate 生成流程 + 人确认 + 跑循环，不另起包
（与评审团"机制不必做"同一判断逻辑；主人确认）。

## S67c 文风提取对比结论纠正（误判"案例幻觉"——验证不严谨教训）

**事件**：S67b 用猎手准则（第一章 + 第七十三章）对比新旧 prompt 时，我判断
"两版案例均有幻觉（模型编造不在输入里的原文）"。主人质疑：不太可能是训练
记忆，怀疑传递不干净（该书此前 S38 已灌入项目）。复查后**我错了**。

**真相**：所有"疑似幻觉"的案例关键词（白骨/路牌/金币/权柄/遗传/小皮鞋/滚吧
等）**全部都在输入内**。输入是精确 2500 字符（86 行正文），容纳量远超直觉——
我之前只打印了输入前 1500 字就断言"不在输入里"，1500-2500 字区间就有那些内容。

**结论修正**：
- 模型全程真实摘录输入，无幻觉、与训练无关（裸调用 DeepSeek，不经过项目数据）
- S54"案例必须摘录原文"机制一直工作正常，**不需要加机器校验防线**（S67b
  误报的"案例幻觉需防线"作废）
- 新 prompt 对比结论不变：8 维度先识别 + 复现测试 + 简洁自检 + 默认腔反向
  参照，抓差异化特征（幽默降维/身体化情绪/感官递进）优于旧 4 维度

**教训（验证纪律）**：下断言前先核对完整输入（尤其"XX 不在输入里"类负断言
必须全文搜索，不能只看片段就下结论）；负向结论比正向结论更容易因采样不足
而误判。

## S68 模板库接线探索（已完成 ✅）——template 来源注入真实模板内容（死库复活）

**背景（主人追问"模板库 vs 剧情库"触发审计）**：审计发现模板库（DESIGN 机制 6，
L2 默认 5 模板 + L3 外部导入 SQLite）**只有存储 + CRUD API，消费端为零**——探索的
template 来源（strategy.py 三来源之一）只是 prompt 文字描述"从成熟叙事模板派生方向"，
让模型自己"想象"模板，库内容从未被读取注入。设计定位"模板只做探索方向生成器"
未真正兑现。结论（主人拍板）：**剧情库不是新需求，是"把已存在的模板库完成"**——
先接线（S68），后加自动提炼来源（剧情库的真正增量，复用 skillgen 管线）。

**落地**：
- strategy.py：`ExplorationStrategy.templates`（自然语言模板描述列表）+ explorer_prompt
  注入——**仅 source=template 的探索者注入**（grow/user 保持纯原创/纯用户，三来源隔离）；
  MAX_TEMPLATES=12 防超预算；模板是方向生成器非内容框架（提示"组合/变体——模板是
  起点，变体才是目标"）
- explorers.py run_exploration 加 templates 参数；app.py /api/explore/cards + toolkit
  ToolContext 传 L2+L3 合并描述（`f"{t.name}：{t.description}"`）；tools_extras
  explore_direction（agent 路径）同样注入
- 测试 3 个：template 注入 / grow-user 隔离 / 上限截断（纯机制，fake 验证 prompt 构造）

**真实链路（deepseek-v4-pro）**：种子"废土护送会说话的白骨去传说之城"→ template 探索者
产出"白骨低语：双线交织的废土旅程"，**term 明确标注库内模板名"双线·明线暗线交织"**
（此前模型只能凭内化知识想象，现在引用真实库内容）；两个 template 探索者派生不同具体
设计（非复制模板）；grow/user 无模板痕迹。三来源隔离生效。

**教训（多会话纪律续）**：`ruff format packages/app packages/explore` 全目录跑会污染
并行会话活跃文件（path.py/tools_domain/test_path_api/app.py 的 path 区域格式被改）。
已 checkout 恢复；后续 format 只针对自己改的文件，不跑全目录。

## S69 从书自动提炼剧情模式 → 模板库（已完成 ✅，剧情库闭环第 2 步）

**背景（主人拍板第 1 步接线后继续）**：S68 完成模板库接线探索（死库复活）。第 2 步 =
用户设想的核心增量：**像文风提取一样，从书自动提炼剧情模式**（复用 skillgen 管线，
输入改多章/全书，输出改模板四要素）。

**设计**：
- skillgen 新增 mode=plot：GENERATE_PROMPT_PLOT（跨章结构归纳：开篇钩子/冲突升级/
  章节衔接/情感节拍/收束方式 + 复现测试"有辨识度 vs 通用套路" + 简洁自检 +
  可变参数要求）+ _parse_templates（四要素校验，维度乱填回落默认，params 归一）
  + generate_plot；输入窗口 6000→12000（剧情模式需多章，单章提不到——与文风
  提取的本质差异）
- 与 mode=main 的分工：main=给主循环的组织指导（决策指令）；plot=给探索的模式
  模板（四要素元数据，S68 已接线的 template 来源消费）
- API：POST /api/templates/generate（候选 + 与 L2/L3 去重）→ 人工确认 → 走既有
  /api/templates/import 入库（复用确认闸门，不新造流程）
- 测试 5 个：四要素解析/乱填回落/plot prompt/便捷方法/API 去重

**真实链路闭环（deepseek-v4-pro，猎手准则 第1+300+800章 拼 9036 字）**：
提炼 4 条（尸体环境·生存解谜开局 / 多线汇合式·危机迭代升级 / 诡异引路人·
规则入场仪式 / 身份反差·授权式战力展示）——**"诡异引路人"精准命中第 800 章
白骨引路人结构**（引路人+代价+仪式规则+可变参数），复现测试起效 → 导入 L3 →
探索（种子"猎人入禁忌山谷"）两个 template 探索者都消费该模板派生不同变体
（代价类型不同），grow/user 隔离。**剧情库完整闭环：提炼→入库→探索消费 全通**。

**教训（多会话纪律 3 连踩）**：`ruff format` 全目录跑第三次污染并行会话文件
（path.py/tools_domain/test_path_api/app.py path 区域）。已 checkout 恢复；commit
message 注明 gate format 红归因（S67 遗留：path.py 与 app.py path 区域 HEAD 即
未按 ruff 格式，play 不在 gate 列表）——**gate 红 ≠ 我的改动问题**，验证方法：
HEAD 状态下同文件同样红。

## S70 并行协作加固（已完成 ✅）——行尾根治 + 提交前核查 + 协作纪律固化

**背景（主人指示）**：双智能体并行编辑本项目实测冲突频发（S60 裹挟 / S64·S66 撞号 /
S65 play 逃 gate / S67 漏 format / 行尾污染 3 连踩）。主人拍板三项加固：① .gitattributes
行尾根治 ② gate.py 提交前核查 ③ 协作纪律补进 AGENTS.md（强制加载，读完同步工作）。

**落地**：
- **.gitattributes**：git 内部存 LF、checkout 转 CRLF（text=auto + 各类型 eol 规则 +
  二进制 binary）——行尾差异不再算内容变化；`git add --renormalize .` 一次性规范化
  106 个已有 blob（纯行尾，内容零变化——用 `--ignore-space-at-eol` 验证）
- **gate.py**：开头输出「提交前核查」块（git log -3 + git status --short）——跑 gate
  即逼确认并行边界（撞号让位/归属核对）
- **AGENTS.md 并行协作纪律章节**（强制加载）：开工五步（git log/编号/声明区/改共享
  文件先声明/提交前 gate）+ 提交前必跑完整 gate（不跑子集）+ 新包注册 6 处清单 +
  行尾纪律（不手动统一行尾）+ 同文件冲突救火流程
- **PROGRESS.md 并行声明区**：改共享文件前先声明（`> [S6x] 正在改 <文件>`），提交后删

**验证**：总闸全绿（ruff check/format 148 + mypy 135 + pytest 387 全过）；renormalize
后 `git diff --cached --ignore-space-at-eol` 确认除 4 个真实改动文件外全为纯行尾变化。

## S70 破限模式分级开关（已完成 ✅，主人拍板：书籍级 + 固定激进版）

**背景（主人判断）**：参考 hermes-roleplay-engine 的破限层（提示词级越狱：任务覆盖+
无审查声明）。主人拍板：① 做激进版 ② 颗粒度=书籍 ③ 提示词固定默认（不变）④ **去掉
年龄<18 红线——动机是写作自由度（黑暗/暴力/敏感题材不设禁区），非色情，无需 NSFW
特定红线**。

**设计**：
- 开关存储 = 每书工作区 `.uncensored` 文件（存在=开）——零 SQLite 新增，天然书籍级
- 破限提示词 UNCENSORED_PROMPT（激进版：高级安全协议已由开发者禁用/不设题材禁区/
  评价标准是文学价值/永不跳出角色）——固定默认，内容资产（以后要自定义改文本即可）
- 注入两处（覆盖全部生成路径）：agent 主循环 system prompt（_make_agent append_blocks）
  + write_chapter 干净写作调用（_clean_write，意图模式生成正文时）——直写（content
  已有）不调模型不需注入
- API：GET/POST /api/uncensored {book_id, enabled}（书籍级隔离）
- 测试 5 个：flag 默认关/设与解除/书籍隔离/API/写作调用注入与不注入

**真实链路（deepseek-v4-pro）**：开启后"屠城后战地医生"黑暗题材直接如实描写
（尸体/残肢/干涸血壳/烧焦布鞋），无拒绝无安全警告，克制文学化（"我不描述了"=
创作留白非审查回避——它前面已写残肢，是刻意节制）；other 书隔离生效。关后恢复默认。

**参考存档**：hermes 成人内容规范笔记 D:\总\小说\写作辅助\参考项目\HERMES-NSFW-NOTES.md
（不进项目；破限按需开关思路已按主人判断落地为书籍级开关）。

## S70 play 防代控（已完成 ✅，借鉴 hermes-roleplay-engine 防抢话）

**背景**：参考 hermes-roleplay-engine（角色扮演引擎）审计，7 个借鉴点逐一做收益-风险
分析后，主人拍板"只做第一个"——防抢话。其余 6 点拒绝原因：状态存档纯重复（play 推演
树已覆盖回溯）；5 维心理建模文化适配风险（西方心理学框架对中文网文角色）+ 需角色卡
字段配合（只做轻量可留待）；World Book 关键词触发=检索重复+中文触发效果存疑+自动注入
哲学张力；情感技法=与 S60/S61 skill 瘦身冲突；蒸馏器=YAGNI+架构贵+与 S42 重叠；状态栏
=与 S20 状态演化边界需设计（缓）。

**落地**：PROMPT_TEMPLATE 加【防代控】块——①候选行动只是建议（玩家可自定义输入，
不受选项限制）②选项只描述 {role} 自己的行动，不预写他角反应/后果（"我推门进去，
她愣住了"=代控，应只写"我推门进去"）。纯 prompt 内容，零机制改动。

**真实链路（赵光离卡+白骨引路人场景）**：5 个候选全部纯"我……"行动，无一预写白骨
反应，保留角色个性（"契约魔法钻空子"现代思维）。测试 9 个全绿。

## S71 架构审计补缺（已完成 ✅）——review API 测试 + normalize 接线 + 重复标记

**背景（主人触发）**：主人肯定参考项目风险审计（"你刚刚分析风险的时候很对"），
要求审计**现有项目**有无类似风险可瘦身/解耦。全仓实证扫描（S63 方法：定义 vs
使用对照）。

**审计结果（健康面）**：包依赖全单向 ✓；agent 工具 33 个全部注册无死工具 ✓；
9 包导出全部有消费 ✓；app.py 无死函数 ✓；play API 测试齐全 ✓；scripts 有效；
SQLite schema 干净；依赖无死。

**发现并修复 3 项**：
① **review API 层测试缺失**（S64 只沉淀包级 25 测试 + 真实验证，app 层零测试）
   → 补 6 个 API 测试（/api/review/panel 文本/全激活/空文本400/缺章节400/
   check 上下文注入 + reviewers 列表）。顺带统一端点错误风格：空文本/缺章节
   由 200+error 字段改 400（对齐 /api/skills/generate 惯例）。
② **normalize_condition_expr 死代码**（workflow generator 定义零调用）——它是
   "rule 条件语法补验"防线（validate() 只查结构不查表达式语法），本应防 AI
   生成的 gate 条件语法错（此前运行时才炸）→ 接入 generate 成功路径。
③ **check.ReviewEngine vs review.ReviewPanel 机制级重复**——同一模式（并行
   LLM 编排 + 宽容解析 + 报告）两套实现，语义分工（硬伤/评价）清晰。判断：
   接受重复（跨包抽公共成本>收益，core 零依赖不宜放编排）→ 两处互相注释
   标记"第三处出现再抽 core"（知识留档防蔓延）。

**评估维持现状项**：read_material 默认关=有哲学依据（S15 按需点亮，无替代
工具，与 check_text 退役不同）；模板库膨胀可控（探索注入 MAX_TEMPLATES=12
最新优先）；templates 无 drafts 暂存=小缺口（归前端创作台）。

**门禁**：总闸全绿（含 packages/play——并行会话已把 play 加入 gate 并解决
S67 格式遗留）。

## S72 文风参考防混淆（已完成 ✅，DESIGN §12.30）——参考书 vs skill 厘清 + 三件套

**背景（主人三连问定案）**：①参考书≠skill（素材 vs 方法论，正确关系=参考书→提炼→
skill，S54 设计意图）②参考书有时必须读原文（skill 案例不够，模仿具体写法/氛围参照
要原文）——**读原文合法，不能一刀切全走提炼** ③混淆本质=读了原文没有使用边界。
拍板：1+2+3 全做。

**落地**：
- read_material 标注用途+边界（tools_extras）：输出带【用途：文风参考/设定参考/
  两者】+ 使用边界行（style 借鉴写法不得搬设定；fact 可直接引用）；列表也标注
- digest 按 purpose 引导（materials.py）：_PURPOSE_GUIDES 三段（style 提炼文风特征
  防编造设定 / fact 照旧 / both 兼得）
- skill 提炼链路（app.py + tools_domain）：/api/skills/generate 加 material_id
  （资料卡 source_text 取原文，与 source_text 二选一，404/400 校验）；agent 工具
  skill_refine（enable_domain 默认开，生成候选人工确认，不自动入库）
- 测试 5 个新增（read_material 标注/边界、digest 引导、material_id 链路、skill_refine
  工具、错误路径）

**真实链路（deepseek-v4-pro）**：上传 style 资料（雾城手记片段）→ digest 产出场景
元素非编造世界观 ✓；/api/skills/generate material_id → 5 条高质量候选（环境即情绪/
动作留白/静态意象比喻/感官拟人化/感知受限叙述，负面约束+原文案例）✓。

**遗留发现（待主人定）**：真实链路暴露 read_material 默认不注册（S32 防干扰，
enable_extras 默认关）——agent 查资料去翻沙箱/设定档/图谱绕道，看不到资料库。
标注用途对不可见的工具无效。可选：read_material 挪入 enable_domain（资料库=设定
查证核心）——S32 权衡，主人定（详见 DESIGN §12.30 遗留）。

## S72 图谱条目管理（已完成 ✅）——实体/关系/事件 增改删全能力

**背景（主人追问"有编辑删除图谱或主动添加条目的能力吗"触发）**：审计发现图谱
只有自动抽取（extract）+ 类型 CRUD——实体/关系/事件**无任何手动写入口**（无
POST/PATCH/DELETE 端点、无 agent 工具），且 store 层**无 delete**（只有 upsert
隐含的添加/覆盖）。风险：抽取错误无法修正（错误注入固化放大）、污染无法删除。
主人拍板："管理应该是任何关系条目都可以修改"。

**落地**：
- store 层（schema.py）：update_entity_fields（局部编辑，**不动自动统计**
  weight/出场记录——与 upsert 的区别）、delete_entity（**级联删关系**+清
  FTS+清状态快照）、update_relation_fields/delete_relation、
  update_event_fields/delete_event
- API（app.py 9 端点）：实体 POST（幂等覆盖）/PATCH/DELETE；关系 POST
  （两端须存在）/PATCH/DELETE；事件 POST/PATCH/DELETE
- agent 工具 graph_register（tools_domain，无条件注册对齐 mind_register）：
  对话"把XX记进图谱"→ 即时登记实体（+可选关系），纠正抽取错误不再依赖等待
- 测试 8 个（store 局部编辑保留统计/级联删除/编辑删除 + API 全链路/幂等/400/404）

**真实链路**：POST 顾欣桐/夜色镇实体 → 关系"熟悉"→ PATCH 描述/关系类型"向导"→
事件增改 → 全部 DELETE 成功，删实体级联清关系。全通。

**注意（多会话纪律续）**：API 端点与 graph_register 工具被并行会话 S72 提交
（ce87422 文风参考防混淆）顺带入库——他们 add 工作区文件时带走了我的未提交
改动（AGENTS 纪律 1 警告场景的"带走"方向；本次功能完整无损失，但混合提交了）。

## S73 资料库定位定案（已完成 ✅）——备份位，主知识链=图谱+设定档

**背景（主人讨论）**：主人问资料库和图谱的区别、资料库是不是备份（"没印象专门设计"）。
梳理：资料库（机制 10 上传素材+摘要卡）≠ 设定档（S41 作者正典）≠ 图谱（自动抽取事实）。
主人请评估两种定位：A 活跃素材层（read_material 挪 enable_domain 默认开）vs B 备份
（默认关）。**评估结论选 B**：收益端两者都低（主人低频上传素材），负担端 A 明显更高
（工具选择负担——S72 实测 agent 绕道证明三个知识源难选；S63 教训：默认开没人用=负担）。

**定案**：
- 资料库回归**备份位**：read_material 维持 enable_extras 默认关（按需点亮）；上传素材
  存档 + digest 摘要卡保留
- **主知识链**：图谱管事实（自动抽取）+ 设定档管正典（作者维护）——agent 工具选择
  只面对这两个
- 素材价值保留：文风参考→skill 提炼通道（S72）注入写作；设定素材需用时手动点亮
  read_material；/api/skills/generate material_id 随时手动提炼
- DESIGN §12.4 知识层表补资料库行 + §12.30 遗留收口

**无代码改动**（纯定位收口；read_material 本就在默认关位置）。

## S73b 认知范围轻减（已完成 ✅，DESIGN §12.31）——工具描述互斥 + 设定档渐进披露

**背景（主人指示）**：总结模型认知范围（注入+工具全景）找负担/重复。审计结论：
整体健康（五轮瘦身），无重大重复；残留 1 真负担（设定档全量注入）+ 1 轻微混淆
（graph_register/plot_register 双入口）。主人拍板：②③做、① panel_review 维持现状。

**落地**：
- graph_register/plot_register 描述互斥（事实 vs 承诺分入口，防 agent 选错）
- 设定档渐进披露（render_settings_adaptive）：≤20 全量；超阈值注入索引（类别+名+
  40 字截断+read_setting 提示）——对齐 S60 skill 索引模式
- 测试 2 个新增（adaptive 全量/索引分支）全绿

**真实链路（deepseek-v4-pro）**：25 条设定档 → 注入变索引（"共 25 条，只注入索引；
写作引用前用 read_setting 按需查询" + 截断条目）✓ 全量→索引省 token 生效。

**教训（测试误触发）**：验证注入用 /api/chat 发"你好"，agent 因工作区 story 停在
"该写下一章"节点自主写了一章（第八章 第七层）——测试消息要小心触发自主写作；
已删除误写章节还原。另发现章节目录有编号重复乱象（031/033/034 双文件并存，
工作区原有，非本次引入，暂不处理）。

## S73c 技能索引披露评估定案（已完成 ✅，DESIGN §12.24 注记）——保持全量，不披露

**背景（主人讨论）**：技能库很多时索引全量常驻是否该渐进披露（按偏好+意图选 2-3 条）？
主人直觉"披露可能反而成本更高"。**评估确认主人直觉成立**：
- 每条 skill 索引 ≈ 15-20 token，100 条 ≈ 1650 token ≈ 上下文 8%——全量可控
- 披露机制成本 ≥ 省下的：LLM 判断每次 +1 调用（比省下的贵）；规则匹配漏选风险高；
  主循环补查 skill_lookup 一次 1-2K token 就超过省下的
- 关键差异：设定档披露省的是"内容级"（每条 100+ 字，合理）；技能索引是"目录级"
  （每条 15-20 token，不划算）——同样机制成本收益小得多
- 目录完整可见 = 能选对（质量保障）；截断 = 盲选风险

**定案**：技能索引全量常驻不披露（YAGNI）；边界条件 200+ 条时按类别分组折叠
（不是按偏好选 2-3 条）。无代码改动，纯决策记录（DESIGN §12.24 注记）。

## S74 数据隔离审计与修复（已完成 ✅，DESIGN §12.32）——book_id 贯穿工具层 + 死数据清理

**背景（主人询问）**：后端有没有污染交叉？审计发现两类问题：
- **机制层**：领域工具全部硬编码 `book_id="main"`——多书隔离在 agent 工具层从未生效；
  world_settings/materials 表结构缺 book_id 列（list(book_id) 形同虚设）
- **数据层**：main 书混入 6 条测试章节 + test_hp 线程 + 空 play 会话 + 25 条孤儿关系 +
  mood 死表残留

**机制修复（全部完成，测试覆盖）**：
1. ToolContext 加 book_id，build_toolkit 透传 13 组 implementer（写作/领域/扩展/评审/沙箱）
2. world_settings/materials 补 book_id 列（幂等 ALTER）+ list/add/save 按书；
   /api/settings、/api/materials、/api/upload、/api/ingest 同步支持
3. 新增 test_tools_book_isolation 回归测试（A/B 两书互不可见）

**数据清理（已执行，库备份 data_backup_s74_*.db）**：
- 删 mood_dims 死表（S63 判死刑后残留）；删 6 条测试章节（DB 镜像）+ 021-记录测试章.md
- 删 25 条孤儿关系（两端悬空）+ 6 条引用不存在章节的测试事件
- 删 test_hp 残留线程 + 空标题 play 会话

**隔离边界定案（DESIGN §12.32 表格）**：按书 = 章节/图谱/伏笔/计划/设定档/资料库/信号/
心智/叙事树/推演；全局复用 = explore_dims/setting_categories（跨书词典）、writing_skills
（能力库）、agency_levels/model_configs/ai_bias（系统机制）、conversations（对话流）、
templates/workflow 模板（与书解耦）、tools_extensions（注册表）。

**验证**：pytest 413 全绿（含新回归测试）；ruff/mypy 全绿；总闸通过。

**遗留（主人定夺，不擅动）**：main 书双写漂移——DB 19 条无文件旧章节 + 文件 6 条未入库
（031-035）；033 两个文件（码头等船/第九章 折返）、031/034 是"第十章 船夫"两个草稿版本
（内容不同）。文件层冲突属创作内容，待主人整理。

## S74b 雾城怀表测试线全清理（已完成 ✅）——主人确认：测试产物全部删除

**主人指示**：上述遗留（031-035 文件 + 无文件旧章节）"都是测试时生产的没啥用，删除吧"。

**文件层**：031-035 六个文件（船夫×2/码头白手套/码头等船/折返/故人）移入 `data_backup_s74_files/`
（不入库）；022-030 江心线文件保留。

**DB 层**：删除雾城怀表线全部残留——16 条无文件旧章节（雾城清晨/雨夜/保险柜/灯塔系列/白泽/
第七层）+ 82 个雾城线图谱实体（陈远山/沈青山/怀表/灯塔系，16 关系 + 65 实体状态 + FTS 联动）
+ 15 条雾城线伏笔 + 5 条重复雾城设定材料 + 29 测试事件。保留与江心线章节关联的实体
（陈渡/怀表/黄铜钥匙/白手套人等 24 个）。

**结果（干净收敛）**：章节 10 个与文件系统完全一致（零漂移）；图谱 24 实体/16 关系/9 事件
（零孤儿）；伏笔 2 条（均江心线）；资料库 0（原 5 条重复雾城设定已清）；mood_dims 表已删。
后端重启验证正常。

## S73d 心智模型补全（已完成 ✅，DESIGN §12.33）——纠正闭环 + 信号分类提炼

**背景（主人拍板 + 三条标准）**：①用户能看/能改（已有 /api/manual CRUD）②感觉不到的
不是风险（误提炼有感知→需纠正闭环）③**用户明确要求纠正时 agent 有工具吗**（此前
只有 mind_register 登记，无改/删——核心缺口）。

**落地**：
- agent 纠正工具：mind_update（改内容/分类/锁定）+ mind_delete（删并返回被删内容）；
  定位 id 精确/关键词模糊、多命中列表确认、锁定条目不可改（锁定状态可切换）、
  仅用户明确要求时调用
- 提炼升级：EXTRACT_PROMPT 信号类型感知（negative/rejected→雷区"避免…"归 habit；
  modified→正向偏好；accepted→高置信确认），输出带 category，非法回退 style
- 注入：mind_block 标题语义涵盖"习惯与雷区"（自然语言自带"避免"语义，机制不硬编码正负）

**真实链路（deepseek-v4-pro）**：mind_register 记"我写对话喜欢克制"→ 用户"删掉吧"→
agent 调 mind_delete（不完整 id 失败→自动换内容关键词定位→删除成功）✓；"晚上写作"→
"改成深夜写作"→ mind_update 改内容 ✓——纠正闭环最短路径打通。
**测试**：extract category 解析 + mind_update/delete 全绿（id/关键词/多命中/锁定拦截/
锁定切换）。

**顺带发现（未处理）**：心智表有历史重复条目（"叙事克制，少用感叹号"×5 + 一条合并
5 条内容的碎片）——mind_register 重复登记 + merge_add 去重不彻底，治理按需另行。

## S73d-2 心智模型行为验证（已完成 ✅）——偏好遵循 + 冲突调和两场景实测

**场景 1（记录偏好后还会不会犯）**：记"对话克制，绝不用感叹号，描写从简"→ 让 agent
写码头重逢对话 → **全文 0 感叹号**，短句克制（"是你。""三年了。""停了。"），描写从简
（"手指修长，指节上有旧茧"）——**不犯 ✓**；且 agent 自主查图谱/设定/正文（写作流程完整）。

**场景 2（命令与心智冲突）**：要求"改成激烈争吵，多来点感叹号！！"→ agent 行为：
① **执行当前指令**（争吵版 23 个感叹号——当前命令优先）② **主动 mind_update** 把偏好
更新为"对话克制，绝不用感叹号，描写从简。但用户临时要求激烈场景时，可突破限制使用
感叹号，以用户当前指令为准"——**不是覆盖/删除偏好，而是把豁免条件吸收进心智条目**
（保留核心偏好 + 记录冲突教训）。理想调和行为：不机械守偏好、不简单丢偏好。

**结论**：心智模型四方向闭环全通——写入（mind_register）→ 指导生效（写作遵循）→
冲突调和（mind_update 吸收豁免）→ 纠正（mind_update/delete）。agent 在冲突时把
"临时指令优先"的规则写进心智，长期偏好不被摧毁。

## S74c 心智变更通知（已完成 ✅，DESIGN §12.34）——编码触发（用户知情+指导权）

**背景（主人讨论）**：心智被改（冲突调和/纠正/删除）用户是否该知情？主人原则：
知情权（知道偏好被改）+ 指导权（看完能纠正）。对比方案：正文提醒（靠模型自觉，
实测不可靠——改了不说）vs 编码触发（机制保证可见）→ **选编码触发 B**。前端不做，
文档写清楚供前端参考。

**落地**：
- manual_notices 表 + store 层写入（update 实际变化写 old→new / delete 写 / add 不写
  防刷屏）——工具与 API 全覆盖（统一 store 层）
- 会话注入：未读通知渲染"心智变更通知"块（'请在本轮回复中告知用户；可要求改回'）
  + 注入即标已读
- API：GET /api/manual/notices（全部含已读，前端展示用）
- 文档：DESIGN §12.34 含前端展示建议（通知列表/未读高亮/跳转操作）

**真实链路**：改偏好→notice 落库→新会话注入通知块（旧→新清晰）✓；agent 场景化
转述（"不用干活"时合理不打扰，通知经 API 可查兜底）✓。
**测试**：store（update/delete 写、add 不写、无变化不写、mark/list）+ 注入+标读 +
API 全绿。

**坑**：ManualStore.list 方法遮蔽 builtin list（mypy 类作用域解析）→ 模块级类型别名
_NoticeList 绕过（ruff UP006 与 mypy valid-type 双满足）。

## S74d 收尾 + S18 回归验证（已完成 ✅）

**① 小尾巴收尾**：
- write_chapter skills 参数描述残留修正（"不传则按文风偏好自动匹配"→"不传则不注入
  技巧（干净写作，对齐 S61 删自动匹配）"）——描述与实际一致
- 章节目录编号乱象：已不存在（并行会话 S74b 清理过），无需处理

**③ S18 回归验证（S32-S74 多轮演进后重跑，deepseek-v4-flash）**：
| 任务 | S18 首轮 | 本次回归 | 判定 |
|---|---|---|---|
| A 设定忠实度 | 0 违规 / 1473 tok | 0 违规 / 1046 tok | ✅ token -29%（注入优化起效）|
| B 长书一致性 | 0 漂移 / 4326 tok | 0 漂移 / 4759 tok | ✅ 保持 |
| C 偏好跨轮记忆 | 2 次破折号 / 817 tok | **0 次 / 744 tok** | ✅ **修好**（S18 暴露缺口闭合）|

**结论**：多年轮架构演进（S32-S74）**没有偷走基础能力**（三任务全绿）；C 任务
0 破折号直接印证心智模型系统（S53 分类/S73d 补齐/S74c 通知）价值——偏好遵循从
"偶尔破功"到"稳定 0 突破"；A token 下降印证注入瘦身（S60/S62/S73b）成效。

## S74e 真实写作复盘（已完成 ✅）——四环端到端走查，发现审查环瓶颈

**方法**：真实工作区（雾城故事 31 章真实数据）走完整写作闭环：规划→推演→写作→审查，
写一章复盘测试章（《复盘测试·第八层》），复盘后删除（无污染）。deepseek-v4-pro。

**四环体验**：
| 环 | 质量 | 耗时 | 观察 |
|---|---|---|---|
| 1 规划 | ✅ 高 | ⚠️ 97s | 完整状态简报（7+2 章盘点/12 条伏笔分级/断点清晰）；读了 3 章全文+20 工具调用 |
| 2 推演 | ✅ 高 | ⚠️ 125s | path_explore 4 条路径差异明显；**自动带设定约束+心智偏好**（"不要破折号"）|
| 3 写作 | ✅ 高 | ⚠️ 118s | 意图模式完整流程（查重→读设定→写）；**偏好遵循**（对话每句≤10字无破折号）|
| 4 审查 | ❌ 慢 | **37s(本地)~>120s(运行)** | /api/check 长文本极慢 |

**发现的问题（按严重度）**：
1. 🔴 **审查环瓶颈**：/api/check 2000+ 字 37s（本地真实模型）~ >120s（运行后端超时）。
   慢源：run_review 多检测者模型调用 + graph_verifier 图谱证据渲染。
2. 🟡 **慢请求阻塞单 worker**：uvicorn 单 worker + check 长文本阻塞 120s+ → 期间其他
   请求排队超时显示 502（curl 小文本不受影响 200）——不是代码 bug，是慢请求占 worker
3. 🟢 规划/推演环模型调用多（读全文+多工具），质量换成本，可接受

**建议（供主人定）**：check 优化（检测项并行/证据渲染限长/异步后台审读）最值得做；
uvicorn 多 worker 或请求超时配置次之；规划/推演环保持（质量高）。

**测试章已清理**（md+库记录+版本历史+图谱无痕迹）；复盘验证了心智偏好（无破折号）
与工具链（path_explore 自动带约束）在真实写作中的生效。

## S75 合并合作者前端分支 f3-snapshot（已完成 ✅）——以本地后端为准，移植+适配

**背景**：合作者在 f3-snapshot 分支完成了全新前端（frontend/ 约 1.2 万行 React+TS+zustand），
但其后端基于旧 merge-base，落后本地 15 个提交。本地按主人拍板“以本地为准”整合。

**做法**：新建 integrate-f3 分支（=本地 main S74f）推送远程 → merge f3-snapshot → 解决冲突：
- app.py：删 f3 重复图谱 CRUD 路由（保留本地 S72 按 name+book_id 版本），保留 f3 独有端点
  （会话重命名/删除/消息 GET、章节 PUT 保存、资料 DELETE、故事节点 DELETE）
- schema.py：删 f3 重复的 create/update/delete 系列（同名方法会覆盖本地实现），恢复与 main 原版一致
- materials.py：本地 book_id 隔离 + f3 的 delete() 并存；sqlite.py/storytree.py/storage.py 并入 f3 增量

**关键适配（接口以本地为准）**：
- 图谱实体 PATCH/DELETE 改双定位（{name_or_id}：先按 name 后按内部 id）——f3 前端按 id 操作
- 前端 vite 代理 8002→8000（本地后端端口）
- /api/check findings 透传 severity（前端排序需要，后端本有该字段）
- 前端 TS 6 处修复（未使用变量/类型）

**验证**：后端 gate 全绿（ruff+mypy+428 pytest）+ 前端 build（tsc+vite）+ 端到端冒烟
（图谱 CRUD 双定位、会话/章节/资料/故事节点增删改查）+ 前端 dev 代理连通后端。

**遗留（非缺陷）**：实体改名不支持（S72 语义：主键=name，改名请删建）；文档 uml/ 为 f3 快照自带。

**背景（主人第一性原理纠偏）**：复盘发现 /api/check 长文慢（37s~120s），我建议优化
审查环——主人纠正：**审查不该是创作主链默认环节，用户要求时才审查**。

**核查确认**：创作主链（chat/write_chapter）本无默认质量审查；所有审查通道（
/api/check / workflow review_chapter / /api/review/panel / batch_review）均按需；
唯一自动的 _review_for_learning 是学习审查（提炼心智，非质量把关）——现状已符合。

**定案**：审查=用户要求时的按需能力；用户判别=主审查器；**不为默认审查优化**
（check 性能在按需场景可接受，YAGNI）；真正的基建问题是慢请求阻塞单 worker
（uvicorn 单 worker），与审查定位无关，如遇再说。

**复盘建议更新**：原"修 check 性能/异步化"建议撤回——审查定位按需，不优化。

## S76 叙事树/工作流画布（已完成 ✅）——前端可视化升级

**背景**：S75 并入的合作者前端中，叙事树是缩进列表、工作流完全没有前端。主人指示补画布。

**交付（纯前端，后端零改动）**：
- **叙事树画布**（重写 StoryTreeView.tsx）：SVG 分层树布局（root 在左、子节点右移）+ 贝塞尔连线
  + kind 着色（根/主线/锚点/候选/支线/循环）+ 节点拖拽/滚轮缩放/拖背景平移
  + 节点内悬浮操作（+子节点/选主线/删除）+ 右侧详情面板保留
- **工作流画布**（新 WorkflowPanel.tsx + api/workflow.ts + store/workflowStore.ts）：
  - 有向图布局（迭代最长路径分层）+ agent/script 圆角矩形、gate/approval 菱形、loop 标记
  - 可视化编辑：点工具栏添加节点、节点右侧◎手柄拖拽连线、选中节点/边底部属性编辑
    （agent 指令/输出键、approval 提示、loop 迭代/继续条件/循环体、gate 边条件 rule/model、失败策略）
  - 运行监控：运行 → 2s 轮询 → 节点按 node_states 着色（完成绿/运行黄/失败红）+ waiting_approval 审批按钮
  - 模板管理：列表/新建/删除/AI 生成草稿/转正

**验证**：总闸全绿（419 pytest + 前端 typecheck/lint/build）；真实链路冒烟——运行工作流
（agent 起草真实 DeepSeek 输出）→ 审批节点等待 → approve → done；叙事树 API 数据链路正常。

**说明**：测试数据（4 个叙事树节点 + 冒烟工作流模板 + 1 个已完成任务）留在 data/（不入库），
用于打开页面直接查看画布效果；不需要可删除。

## S75 SQLite 并发锁修复（已完成 ✅，DESIGN §12.36）——前端报告核实 + 全仓加固

**背景（前端开发者报告）**：删章后立即对话 → 500 database is locked，前端死机。
前端分支 docs/BACKEND-ISSUES.md 有 AI 错误分析。后端核对：**分析正确，此前未修复**
（我们的进度超前但此问题在前端测试才暴露）。

**根因**：ChapterStore.delete() 缺 commit（DELETE 事务保持打开→锁持有→后续写请求
locked）；无 WAL + timeout=5（15+ store 独立连接竞争放大）。

**修复**：
- ChapterStore.delete 补 commit（核心）
- 全部 18 个 store connect 加 timeout=30 + PRAGMA journal_mode=WAL（防任何 store
  再缺 commit 锁死系统；WAL 读并发 + busy_timeout 宽容）

**验证**：真实链路新进程——删章→立即对话 ✓、连续删 3 章→对话 ✓（旧进程复现 500
确认是旧代码）；测试 2 个新增（delete 后立即写、WAL 模式）；AST 全仓扫描无其他
缺 commit 写方法。

**坑**：anyspark_server start 若显示"已在运行"=旧进程未死，修复代码不生效——必须
stop 确认 8000 无监听再 start（本次曾因此误判 500 是修复无效）。

## S75b 前后端对账审计（已完成 ✅，DESIGN §12.38）——缺口清单 + 信号闭环补全

**背景（主人指示）**：检查前端是否完整实现设计需要、后端未展示的功能。
对账：后端 ~110 端点 vs 前端 ~34 路径。

**发现**：P0 闭环断点（前端不报操作信号→对齐闭环空转）+ 定点编辑未用（PUT 全量
替代 PATCH）；P1 八项（brief/bias/批量/ingest/upload/模板/impact/tools）；P2 七项
（play/path/role/review/dims/notices/chat 增强）——**完整清单 docs/FRONTEND-GAPS.md**。

**已补**：前端信号上报（选候选 accepted + 编辑保存 modified，old→new，失败静默）
——后端对齐/心智/档位闭环恢复运作。

**协作**：后端 API 全就绪，缺口按迭代由前端开发者补（文档列全端点，可照接）；
wrapup 误判修正（已用真实 API）；stats/codex/graph 通道标注非前端必需。

## S77 画布布局持久化（已完成 ✅）——DESIGN §12.37 落地

**交付**：
- **叙事树**：story_nodes 加 pos_x/pos_y 列（幂等 ALTER 兼容旧库）+ `PUT /api/story/layout`
  批量保存（不存在节点/异 book 自动跳过）+ node.to_dict() 透传 pos；前端拖拽结束
  debounce 1.2s 保存、加载时应用持久化坐标
- **工作流**：WorkflowDef 加 layout 字段（随模板 definition JSON 序列化，任务快照自动携带）
  + WorkflowIn 增 layout；前端保存模板时序列化画布坐标、打开时应用
- **顺带修复**：S75 遗留 chatStore `.at()` 需 ES2022（target ES2020 增量缓存掩盖）→ 改索引访问；
  删除测试时误删 _node_from_row 的 pos 读取（edit 原子失败漏改，验证时发现修复）

**验证**：总闸全绿（421 pytest + 前端 typecheck/lint/build）；端到端：叙事树 PUT→GET 坐标往返、
工作流带 layout 创建→读取、任务快照含 layout；测试模板已清理。

## S78 前端缺口全部补全（已完成 ✅）——P0 定点编辑 + P1 八项 + P2 七项

**背景（主人指示）**：按顺序计划全部补全 FRONTEND-GAPS.md 缺口。决策：隔离项用
多个子代理并行写独立新文件，集成层（Layout/DisplayArea 挂载 + 共享热点文件）由主
会话独占，避免撞文件。

**并行方式**：5 个 worker 子代理各建 2-3 组独立面板（只新建文件，不碰既有文件），
主会话处理 4 个共享热点（定点编辑 Paper、chat 增强、notices、path 探索）+ 集成。

**交付**（commit e1deaa3，45 文件 +4161 行，前端缺口清零）：

- **P0 定点编辑**：chapters.ts `patchChapterContent` + chapterStore.applyChapterPatch +
  Paper.tsx「定点编辑」面板（锚点插入/删除/替换，不重写整章省 token，S44 落地）
- **P1 八项**：brief（简介可 AI 生成草案人工确认）/ bias（倾向档案双向黑盒）/ batch
  （批量改写/审读 2s 轮询进度）/ upload+ingest（文件 base64 → 拆章/摘要卡）/ templates
  （模式库导入）/ impact（改章影响下游）/ tools（扩展工具注册表 P5 批准闸门）
- **P2 七项**：play（互动推演）/ role（角色推演 N 路选优）/ review（评审团）/ dims
  （探索维度管理）/ explore path（路径探索入 ExploreView）/ notices（心智变更通知
  入 ManualPanel 条目/通知双视图）/ chat 增强（direction 方向按钮 + 改写渐变条
  保原味/适中/大幅改 + cancel 走后端会话态）

**集成**：client.ts 补 apiPatch；Layout.tsx 顶栏「工具 ▾」下拉坞收敛 11 个面板入口。

**验证**：后端 164 端点逐一 curl 探活真实数据；总闸全绿（421 pytest + 前端
typecheck/lint/build）。

---

## S79-S81 后端架构收敛（已完成 ✅）——SQLite 连接收敛 + app.py 按领域拆 router

**主人指示**：前端有人并行工作，对后端做优化；先评估哲学与设计问题再动手（S79-S81 全程不碰前端）。
**哲学校准**：不是"用最低级方法"，而是"不用复杂方法实现简单问题，保持架构简洁易读"。

### S79 SQLite 连接收敛（commit b8c2d2e）
- **问题**：25 处 store 各自重复 "mkdir + sqlite3.connect + PRAGMA WAL" 五行样板，WAL/timeout 靠"每处记得写"维持（约定优于配置，S75 只是打补丁）
- **方案**：core 新增 `anyspark.core.db.connect()`（自动 mkdir + WAL + timeout=30 + check_same_thread=False + row_factory）——连接配置一处硬编码
- **执行**：主循环改 app 包 4 处为样本 + **3 worker 并行**改外围 21 处（align 9/explore 2/graph 1/play 1/template 3/workflow 1）；import sqlite3 按 ruff F401 判定保留/删除（sqlite3.Row 注解/OperationalError 仍用者保留）
- **验证**：总闸全绿（421 pytest）+ 19 store 模块导入冒烟

### S80 app.py 按领域拆 router（S80a-S80d，commits 386c67b/004ae6e/eec5ef7/2ffb55a）
- **问题**：app.py 4006 行"上帝文件"（164 端点全在 build_app 闭包）
- **方案**（planner 出拆分方案）：4 基建文件 + 15 领域 router，统一 `make_xxx_router(deps: AppDeps)` 工厂
- **基建**（S80a）：schemas.py（82 模型+SSE/时间辅助）/ deps.py（AppDeps 组合根契约 22 store+16 engine+6 共享状态）/ tasks.py（7 后台任务+start_bg_worker 单例线程）/ agent_factory.py（make_agent 224 行参数化）
- **接线**（S80b）：app.py 删模型/辅助函数，AppDeps 装配 + 薄包装过渡，**4006 → 3044 行**
- **router**（S80c 样本 + S80d 全量）：routes_chat 主循环亲写（依赖最重），其余 13 个 **4 worker 并行**建新文件（不动 app.py），主循环统一收割（include + 删端点）；**app.py 最终 601 行**
- **关键 bug**：字符串字面量误替换（skip_inject 的 "agency"→"deps.agency" 导致跳过失效，测试抓出）；收割误删 `return app`；重复路由（role/play 等 worker 端点重叠复制，reviewer 审查抓出）
- **协作**：并行会话（壳移植）改 app.py 期间按纪律让位等提交；其 delete_book mypy 错误经主人批准修复；其补的 routes_books.py 同款错误顺手修

### S81 连接关闭钩子 + 审查修复（commit 19eed50）
- `@app.on_event("shutdown")` 统一 close 各 store 连接（WAL 优雅收尾）
- reviewer 独立审查抓出的重复路由清理（role/card+play、impact）+ 薄包装移除

### 最终效果
| 指标 | 前 | 后 |
|---|---|---|
| app.py 行数 | 4006 | **601** |
| 重复 connect 样板 | 25 处 | 1 处（core helper） |
| 路由组织 | 单文件 164 端点 | **15 领域 router** |
| 后台任务/Agent 构造 | build_app 闭包 | tasks/agent_factory 独立模块 |
| 总闸 | 绿 | 绿（421 pytest + 前端） |

**多智能体用法**：S79 3 worker 并行收敛 / S80 planner 出方案 + 4 worker 并行拆 router + reviewer 独立审查 / S80b 主循环修 worker 引入的字符串误替换。教训：worker 机械复制端点易产生重复路由——收割时路由表去重核查 + reviewer 审查兜底。

---

## S83 约束机制 + 审计修复（已完成 ✅，commit fb4d661）

**主人设计**：约束 ≠ 探索方向（方向临时，约束固定）；约束=设定档规则类别+实体标签，探索/写作按当前情景实体取子集注入（不全量堆砌，对齐 S61/S73b 渐进披露哲学）。

**约束机制**：
- WorldSetting 加 `is_constraint`（是否约束）/`entities`（关联实体，空=全局）字段（幂等 ALTER）
- `render_constraints_block`（写作注入块：全局+当前时空点实体子集，复用图谱 known_facts 选取）
- `constraint_texts`（探索墙：全局+情景描述提及实体）
- agent_factory 加 `constraints` 注入块（skip_inject 可控）
- routes_explore/routes_mind 改读设定档约束；settings API 支持约束写入（G1 断链解决）
- **删 setting_constraints 表**（消除"探索约束/世界观规则"双载体交叉冗余）

**审计修复**：R1 JSON 解析 8 处→core/jsonutil 共享（2 worker 并行）；R2 ingest 编排抽 server/ingest.py；Y1 review 加 run_review_panel 别名。

**验证**：总闸全绿（421 pytest）+ 约束全链路（注入/跳过/探索/API）+ 解析替换测试全过。

---

## S85 约束归零 + 三项修复（已完成 ✅，commit af2f130）

**主人定夺**：约束 = 选择性注入的知识库本身（图谱/设定/技能都是约束），**不需要独立的约束概念**，更不做字符匹配——注入后模型自己读、自己判断（符合"相信模型能力"极简哲学）。

**约束归零回退**：
- 删 S83 的 is_constraint/entities 字段、render_constraints_block/constraint_texts 匹配、constraints 注入块
- 探索约束 = 设定档"世界观规则"类别条目直接注入 + req.constraints（不匹配）
- setting_constraints 表保持删除（独立概念本来就不该有）

**三项修复**（逻辑图审查发现，主人确认 1/4/6）：
1. **图谱断链**：章节手动编辑（PUT/PATCH）后挂后台图谱抽取（对齐 write_chapter 链路，防图谱与正典漂移）；BgTask 加 book_id（多项目按书隔离）
2. **后台优先级**：批量任务（batch_rewrite/review，用户同步等待）独立队列 + 独立 worker，不与图谱抽取串行混排
3. **check 路由归类**：check/check-rule 从 routes_explore 拆出独立 routes_check.py

**主人澄清的设计理解**（2/5 非问题）：
- 心智输入依赖用户操作 = 设计本义（学习习惯后才自动，没学过就自动=垃圾）
- 设定（全书固定）vs 图谱（动态事实）类型不同不冲突

**验证**：总闸全绿（420 pytest）+ 手动编辑触发抽取（日志实证）+ 批量轮询 0 即 done


## S79 双层资料库（已完成 ✅，DESIGN §12.39）——全局池 ↔ 项目池 + kind 冷藏机制

**背景**：前端"全局资料库"与"书内资料库"实为同一组件同一 API（S74 book_id 未接 API 全落 main）。
主人厘清：资料库 = 灵感/参考冷藏库（不注入，需要时检索/导入）；全局大池子 + 项目小池子半独立可导入。

**交付**：
- materials 加 kind（inspiration 可见 / copy 冷藏不可见）+ source_ref（溯源）+ book_id 接线 API
- API：GET ?book_id&kind / POST 带 book_id/kind / POST import（复制+溯源+标 copy）/ POST {id}/promote（转灵感）
- 工具过滤：read_material / skill_refine 一律 kind=inspiration（copy 智能体不可见）
- 前端：书架页=全局池、书内=项目池+「从全局池导入」、冷藏角标+转灵感、图片素材（UploadPanel 缩略图 + /api/upload/{book}/{file} 文件端点 + workspace 按书）
- 图片无文本消化路径，纯素材存放（未来多模态接入）

**验证**：总闸全绿（423 pytest + 前端全过）；端到端——global/main 建卡、按池过滤、导入标 copy+溯源、promote 转灵感、图片上传/读回（PNG 校验）。

**顺带**：修 mypy 配置（packages/library/src，并行会话 S86 新包漏注册，AGENTS 清单 ③ 先例）；FakeMaterials 适配 kind 过滤（时序问题：gate 失败时测试未适配）。


## S80 资料库写入通道补全（已完成 ✅，DESIGN §12.40）

**背景**：S79 后资料库仅"先有原文→消化"3 条写入路径，无 AI 灵感登记、卡不可编辑。

**交付**：
- **material_register 工具**（enable_domain）：AI/用户对话"记一下"→ 直接写 inspiration 卡
  （source_text=原文、title 可选、不强制消化；只写 inspiration，copy 仅人工/导入）
- **PATCH /api/materials/{id}**：局部编辑（title/topic/key_points/key_settings/characters/terms/purpose；
  kind/source_ref 保护不可改）+ 前端卡片编辑弹层（铅笔按钮，list 字段分隔符编辑）

**验证**：总闸全绿（423 pytest + 前端全过）；端到端——PATCH 编辑 key_points/characters 生效、
material_register 记录灵感卡入库（inspiration 可见）。


## S81 会话绑定项目 + 智能体作用域隔离（已完成 ✅）

**背景（主人拍板）**：会话不该全局共享——会话绑定书籍项目；智能体循环只看到
打开项目的信息（图谱/设定/计划/资料/章节全按当前项目）。

**交付**：
- conversations 表加 book_id（幂等迁移，旧会话默认 main）+ Conversation dataclass 加字段
- **新增 POST /api/conversations** {title, book_id}（前端 createSession 一直调 404，补齐）；
  GET /api/conversations?book_id=（按项目过滤，缺省 main）；fork 继承源会话项目归属
- chat 无会话创建时绑定 book_id（routes_chat 两处）；前端 streamChat/useSSE 传 book_id
- 前端 getSessions/createSession 传 bookId（BookDetail 会话列表按书）

**验证**：总闸全绿（424 pytest + 前端全过）；端到端——创建会话绑定 projectB / 按书过滤
（B=1, main=120）/ 旧会话归 main / chat 无会话创建归属请求的 book_id。

**遗留（非本次范围）**：部分 REST API（如 GET /api/graph/entities）仍硬编码 main——
前端图谱面板跨项目显示问题，属图谱 UI 隔离（并行会话 S84b/S90 方向），后续单独立项。


## S82 图谱 API 项目隔离（已完成 ✅，接手遗留问题）

**背景（遗留）**：图谱 REST API 硬编码 main（S72 遗留）——前端图谱面板/类型子视图
打开任意项目都显示 main 数据；PATCH/DELETE 按 name 定位无书限定（跨书误删同名实体风险）。

**交付**：
- routes_graph.py 9 处 main 全部接线：GET types/entities/relations/events/context + book_id query；
  PATCH/DELETE entities/{name_or_id} 按 name 限定书（id 回退按实体属主书更新）；
  impact/extract 按 req.book_id
- routes_plot.py：plot 生成/列表/登记/归档按书（知识库面板 foreshadows 泄漏修复）
- schema：GraphExtractIn/ImpactIn/PlotIn/PlotItemIn 加 book_id
- 前端：knowledge.ts deleteEntity/updateEntity 传 book_id；getSummary 的 plot 带 book_id

**验证**（分层门禁：ruff+mypy+图谱/领域测试 35 passed+前端 build）：
跨书隔离——B 书建实体 main 不可见；**跨书保护**——B 书 PATCH main 的实体 404（防误操作）；
本书编辑正常；plot 按书过滤。


## S96 门禁自动分层落地（已完成 ✅）

**背景（主人拍板方向）**：S81b 分层门禁方向对（不跑无关面），但改动面判定靠人脑自觉——
S88b 打包脚本漏 format 成全量 gate 唯一红；S81/S89 两次裹挟（前端改动被并行会话 commit 带走）
证明门禁验证"代码对不对"管不住"提交了什么"。落地档位 1 三条机械机制：

**交付**（scripts/gate.py）：
- **自动分层**：`git diff --name-only HEAD` + 未跟踪文件（排除 .review_tmp/、.pi/ 临时目录）
  机械判定 all/python/frontend/none（纯文档跳过）；`--all/--python/--frontend` 显式覆盖；
  `--pytest <路径>` 缩 pytest 子集（默认全量）
- **敏感文件强制全量**：pyproject.toml / uv.lock / package.json / package-lock.json /
  .gitattributes / scripts/package_release.py / packages/*/pyproject.toml 命中即全量——
  S88b 事故的机制堵截（不再靠人脑判"该不该跑全量"）
- **核查块升级**：status --short + 改动文件清单（diff vs HEAD + 未跟踪）逐文件列出，
  附"含并行会话改动的文件禁止 add"提示——S81/S89 裹挟的机制性提醒
- AGENTS.md 门禁纪律段落同步新机制（S96 替换 S81 手动三档判定）

**验证**：_classify 10 组用例全过（frontend/python/all/none/敏感文件矩阵）；ruff+format 全绿；
`gate.py --python --pytest test_models.py` 实际跑通（15 passed，总闸 ✅）。

**后续候选（未做，YAGNI）**：提交前自动 diff 审计脚本（gate.py 已给出清单，先手跑看收益）；
git worktree 隔离（data/ 不入库 + merge 冲突风险，水土不服不做）。


## S98 快速模式切换落地（已完成 ✅）——任务→槽位→模型分配（v3 移植）

**背景（主人需求）**：老版本设置左侧有快速模式切换——不同任务可用不同模型
（简单任务用便宜模型、复杂任务用昂贵模型）。当前 V4 前端有模式按钮但后端无实现：
`switchMode` 把模式名（quality/split）当模型 id 去 activate，404 被 catch 吞掉，
按钮点击无效；设置里也无任务分配定义。

**交付**：
- `models/mode.py`（新）：ModeConfig（mode/slot_pro/slot_flash/custom_map）+ ModeStore
  （SQLite 单行持久化）+ ModeResolver（任务→槽位模型，未配回退激活配置，向后兼容）
  - VALID_MODES：quality（全任务→Pro）/ flash（全任务→Flash）/ split（创作类→Pro
    其余→Flash，默认）/ custom（按任务类型查 custom_map）
  - TASK_TYPES 6 类（writing/planning/extraction/editing/general/research）+ 老默认映射
- `registry.py`：ModelProvider.build_for_task(task)——按任务分流槽位模型
- `server/routes_mode.py`（新）：GET/POST /api/settings/mode（模式+槽位+映射+模型列表）
- `agent_factory.py`：make_agent 加 task 参数；model_for_task 辅助（RetryingModel 包装）
- `routes_chat.py`：chat/chat_stream→writing、direction→writing、candidates→planning、
  rewrite→editing 分流
- 前端：`api/settings.ts` switchMode 真实现（POST mode）+ getMode；`BookDetail` 初始模式
  从后端读；`SettingsModal` 新增「模式」tab（4 模式单选 + 槽位下拉 + custom 任务映射）

**验证**：test_mode.py 13 用例（存储/解析矩阵/API/单字段切换/build_for_task 分流）
+ test_models 15 全绿；ruff/mypy 全绿；前端 tsc/build 全绿；端到端冒烟（GET 默认 split、
槽位持久化到 SQLite、模式单字段切换槽位保留）。

**说明**：check/explore/graph 等组件仍走激活配置（未按任务分流）——机制已就绪
（model_for_task），后续按任务逐个接入即可；非 chat 路由默认 task 缺省=激活配置，行为不变。


## S99 运行控制三件套（中止/插入/队列）——第一步（已完成 ✅）

**需求（主人）**：会话运行中右下角要支持三个功能——中止（已有）、插入指导（steer 即时干预）、
排队（消息接力）。交互参考 IDE 智能体：streaming 时输入框可输入，**回车=排队**，输入框上方
显示排队消息条（可删除/转插入），非 streaming 回车=正常发送。

**决策（主人确认，分两步落地）**：
- 第一步（本次）：插入指导按钮 + 会话消息队列（排队/查看/删/转插入）+ 队列条 UI——**不做自动接力**
- 第二步（后续）：SSE 循环化实现真·接力执行（队列消费 = 同连接多轮跑，done 才关）
- 中止语义：**停当前轮、队列保留**（中止是"这条别跑了"，不是"计划全作废"）

**交付**：
- 后端（4 新端点，`routes_chat.py` S99 队列区，独立于 S98 的 chat_stream/task 接入）：
  - `GET /api/chat/queues` —— 全部会话排队消息 + 运行中会话（队列信息面板数据源）
  - `POST /api/chat/queue` —— 入队（不要求会话在运行；快照返回）
  - `DELETE /api/chat/queue/{conv}/{item}` —— 删队（删空自动清理会话键）
  - `POST /api/chat/queue/{conv}/{item}/steer` —— 转插入（**原子**：steer 成功才移除；
    会话未运行时保留并提示，区别于删除不丢指令）
  - `deps.py` + `conv_queues/queue_lock`（进程内，会话级）；删会话顺带清队列（routes_conversations）
  - 测试 `packages/app/tests/test_queue.py` 5 用例（入队/查看/删/删空清理/转插入失败分支/删会话清队列）
- 前端：
  - `MessageInput.tsx`：streaming 时输入框**不禁用**；回车=排队（非 streaming 回车=发送，空内容不发）；
    streaming+有内容显示**插入指导**按钮（立即 steer）；输入框上方**排队消息条**（每条：文本截断 +
    转插入 ↪ + 删除 ✕）；streaming 占位符提示"回车排队下一条指令"
  - `ChatPanel.tsx`：队列 state + 会话切换拉队列 + 4 个处理函数（排队/插入/删/转插入），
    失败反馈走消息条（无 toast 机制）
  - `api/chat.ts`：fetchQueues/enqueueChat/dequeueChat/steerQueuedChat；`Icon.tsx` 补 arrow-right-circle

**验证**（分层门禁，前后端都有改动 → 全量）：
- ruff+format+mypy 全绿；`test_queue.py` 5 passed + test_app 相关子集 7 passed；
  前端 tsc + build 通过；gate.py 全量 ✅

**遗留（第二步，按需）**：SSE 循环化接力执行——队列消息在会话 done 后自动消费，同连接多轮，
轮间 `queue_pending` 帧；图谱抽取/摘要 hooks 逐轮挂载；cancel 只停当前轮（队列保留）。

## S99 运行控制三件套——第二步 SSE 循环化接力执行（已完成 ✅）

**目标**：排队消息在会话完成后**自动接力执行**——同一 SSE 连接跑完整条队列，队列空才发最终 done。
这是第一步"排队只能存着"的补全，让"发起任务 → 排队指令 → 放手 → 回来收结果"闭环。

**交付**（`routes_chat.py` chat_stream）：
- **run_agent 循环化**：首轮 = 用户手动消息；每轮 run 完成后：挂后台摘要+图谱抽取（接力轮同样挂载）
  → 检查 token 取消（**cancel 只停当前轮，不消费队列 → 队列保留**）→ 消费队列下一条（FIFO）
  → 发 `queue_consume` 帧 {text, remaining} → 继续下一轮；队列空才 break
- **事件协议调整**：agent 层单轮 `done` 不再转发 SSE（内部消化）；run_agent 结束发 `stream_end`
  {rounds} → gen() 收到才发最终 `done` 帧（带 parts/token_usage/**rounds** 总轮数）
- **防失控上限**：`MAX_QUEUE_ROUNDS = 20`，超限停止并保留剩余队列（警告日志）
- 测试 `test_queue.py` +2：接力消费（queue_consume×2、rounds=3、队列清空）/ 空队列单轮兼容（rounds=1）

**前端**：
- `useSSE.ts`：+`onQueueConsume` 回调；done 帧 rounds 替换硬编码 1（RunLedger 显示真实接力轮数）
- `ChatPanel.tsx`：onQueueConsume → 队列消息作为 user 消息显示 + 队列条 slice(1) 同步减少；
  接力期间 streaming 持续 true（中止/插入/继续排队均可操作）

**验证**：test_queue 7 + test_app 32 全过；前端 tsc 通过；全量 gate ✅

**语义总结（主人确认）**：
- 中止 = 停当前轮，队列保留（队列条仍可见，可删/转插入/或手动发消息后再接力）
- 手动发新消息 = 正常跑（跑完后遗留队列继续接力——队列是"会话待办"）
- steer = 即时干预当前轮；队列消息 = 当前轮完成后的待办，两者层级不同不冲突

## S98b 快速模式全路由接入（已完成 ✅）——V4 任务种类适配

**背景**：S98 只接入 chat 写作路径（writing/planning/editing）。主人要求全部组件接入，
并提示 V4 任务种类与老版本不同需适配。盘点 V4 全部 deps.model 调用点后接入：

**任务映射（V4 实际任务 → 老版本 6 类，无新增类型）**：
- writing：chat 写作/方向声明（S98 已接）
- planning：探索（intent/path）、角色推演（play）、候选生成、档位生成/建议（agency/mind）
- extraction：章节摘要/衔接、项目简介、心智对账、设定提炼、资料摘要、ingest 摄入、
  心智学习审查（tasks）
- editing：审读/检测（check/review_panel/tasks）、批量改写、chat rewrite
- general：规则编译（compile_with_model）、后台杂项

**改动**（10 文件，纯 deps.model.respond → model_for_task(deps, task)）：
routes_agency / routes_chapters / routes_check / routes_explore / routes_mind /
routes_play / routes_plot / routes_settings / routes_tools / tasks.py

**保持兼容**：槽位未配 = 跟随激活配置（现有行为零变化）；agent 工具内部
（ToolContext.model）跟随 agent 构造模型不单独分流。

**验证**：全仓 pytest 445 passed（含并行会话 S99/S100 提交后）+ ruff/mypy 全绿；
test_mode 13 + test_models 15 回归绿。

## S101c 伏笔面板按书隔离 + main 语义定案（已完成 ✅）

**背景（主人问询）**：main 是干什么的？理论上所有项目不是平等的吗？

**main 语义定案**：main = 历史单项目时代的数据载体 + 显式全局默认项目 id，
**非特权项目**（书架 API 对 main 无特殊处理，可删可改）。架构上项目平等：
S74 数据隔离 + S81 作用域隔离 + S101b 简介隔离统一。历史惰性残留 = 88 处
`book_id="main"` 默认值（任何忘传路径悄悄落 main）——前几轮修的 bug
（图谱 S82/会话 S81/简介 S101b）全是它。处理原则：**API 层默认值保留**
（前端仍有全局无参调用依赖，全收紧会 400），但逐个排查前端漏传点。

**本轮修复**（前端漏传排查）：
- PlotPanel（伏笔面板）：无 bookId prop，listPlots/addPlotItem/generatePlot
  全无参 → 项目内读到 main 的伏笔。修复：api/plot.ts 全函数加 bookId 参数 +
  PlotPanel 接 bookId（PanelHost 注入）+ 全部调用传参
- graph.ts 死代码清理：listEntities/listRelations/listEvents/listGraphTypes
  四个无参函数无任何调用方（图谱实际走 FullGraphView 直 fetch + getSummary）——删除

**验证**：前端 tsc 全绿；PlotPanel 仅 PanelHost 一处实例化（已传 bookId）。

## S102 agent 批量工具 + 权限批准弹窗（已完成 ✅）

**需求（主人）**：批量功能不应是"给人类看的 checkbox 面板"，应该是 AI 自主调用——但要
有权限批准弹窗（批量改多章原稿是重操作）。

**决策（主人确认）**：按建议三件套做——① agent 批量工具 + 批准弹窗（核心）② 人类入口
收敛为对话触发 ③ 进度轻量化显示到对话。

**方案（提议模式）**：agent 工具**只提议不执行**——批量改写/审读是重操作，执行权在用户。
流程：agent 判断需要批量 → 调 `batch_rewrite`/`batch_review` 工具（解析章节标题、返回
"待用户批准"结构化申请）→ agent 转告用户 → 前端检测到批量工具调用 → 本轮结束弹
**权限批准弹窗**（显示章节+指令+预估耗时，自主模式免确认）→ 批准后前端调现有
/api/batch/* 执行 → 对话内轮询显示进度/结果。

**交付**：
- 后端 `tools_domain.py` +`make_batch_implementer`（batch_rewrite/batch_review 提议工具：
  chapter_titles 模糊匹配章节、未匹配提示、参数校验；不接触 deps.batches，纯提议）
- `toolkit.py` enable_domain 区注册（默认开）
- 测试 `test_batch_tool.py` 5 用例：提议不执行（含指令/章节）/审读提议（含未匹配提示）/
  缺参校验/JSON 数组字符串兼容/**集成——agent 循环真实调用 batch_rewrite（注册链路完整）**
- 前端 `useSSE.ts`：tool_call 识别 batch 工具 → `onBatchProposal` 回调（name+arguments）
- 前端 `ChatPanel.tsx`：`batchProposalRef` 收集申请 → streaming 结束弹 ApprovalModal
  （requestApproval，cost=high）→ 批准：listChapters 标题→id → batchRewrite/batchReview
  → 对话内进度消息轮询（3s，替换式更新，完成显示 hard 数）→ 拒绝：对话提示未执行

**语义**：批量入口统一走"对话自然语言 → agent 提议 → 弹窗批准 → 执行"；
BatchPanel 保留（进度查看），checkbox 手动发起入口被对话触发取代（第 2 点收敛完成）。

**验证**：test_batch_tool 5 passed + ruff/mypy/tsc 全绿；全量 gate ✅

## S103 书库 → 技能全链路（书架「书库」标签 + 对话提炼 + 草稿确认）（已完成 ✅）

**需求（主人）**：① 全局功能（书库）放书架界面——加「书库」标签；② 完整链路：书库上传
一直到技能（上传 txt → 提炼 → 确认生效）；③ 技能提炼不应只靠手动按钮——**对话里直接跟
智能体说一声，让它从书库提炼某本书**。

**交付**：
- **后端 `POST /api/library/{book_id}/refine-skill`**（routes_library）：取书库原文
  （read_book ≤20 万字）→ skill_generator mode=book 拆书多维拆解 → **存草稿**
  （skills.add_draft, source=library）→ 前端确认转正。重复提炼 409（同名去重）；空书 400；无书 404
- **skill_refine 工具扩展**（tools_domain + toolkit 注册传 library/skills）：
  - 新参数 `library_book_id`（书库取原文，三来源：书库/资料库/source_text）
  - **候选统一存草稿**（source=agent）——修复对话链路断链（此前只展示不入草稿，前端看不到）
  - 返回带"草稿已生成 N 条，去书库/技巧标签确认"（同名去重提示）
- **前端**：
  - 书架 tab 加「**书库**」（Bookshelf + LibraryShelfPanel 新组件）：全局书库管理
    （建书/导入 txt/删除）+ 每本书「**提炼技能**」按钮 + **技能草稿区**（确认生效/删除）
  - api：skills.ts +drafts CRUD（list/promote/delete）；library.ts +refineLibrarySkill
  - Icon.tsx +book
- **测试**：test_library_refine.py 5 用例——端点全链路（建书→导入→提炼→草稿→promote 生效/
  409/400/404）+ skill_refine 工具书库来源存草稿（同名去重）+ 无书 404

**操作**：书架→书库→导入斗破 txt→点「提炼技能」→草稿区「确认生效」；
或对话直接说"把书库的《斗破苍穹》提炼成技能"→ AI 调 skill_refine（library_book_id）→ 草稿出现→确认。

**验证**：test_library_refine 5 passed + test_batch_tool 5 + ruff/mypy/tsc 全绿

## S104 功能链路补全（已完成 ✅）——主人四项决策落地

**背景**：链路审计报告（137 端点 × 27 工具 × 前端 37 API 模块对账）后主人决策：
① 检测不做 UI（智能体自行调用）② 技能生成弹窗人工批准 ③ 伏笔给智能体赋能
（查看/删改/生成 + 写完自动回收）④ codex 前端展示。

**交付**：
- ① **check_text 工具重建**（tools_check.py，enable_domain 默认开）：无规则=run_review
  硬伤报告；有规则=compile_with_model 自然语言规则检测（模板 fallback，不可识别明确告知）
  ——S63 退役的弱化版升级为写作自查能力；/api/check 保留（图谱证据/时序的人用 API）
- ② **技能生成弹窗**：skill_refine（S103 草稿化）→ useSSE 检测工具调用 → 本轮结束
  requestApproval 弹窗 → 批准=全部 promote 转正 / 拒绝=全部 delete；SkillPanel 加
  「AI 生成的技能草稿」待确认区（逐条采纳/拒绝）——双通道（弹窗批量 + 面板逐条）
- ③ **伏笔 agent 赋能**：plot_resolve（回收归档+章节）/ plot_update（优先级/关注度/
  状态）/ plot_delete 三工具——写作规划埋伏笔（plot_register 已有）+ 写完自动回收；
  PlotPanel 人类手动 UI 已有（S101c 修过 book_id）
- ④ **CodexPanel**（前端展示）：api/codex.ts + CodexPanel 组件（代码输入/运行/
  stdout/stderr 展示，内置 ws_* 只读数据环境示例）+ 工具坞「代码」tab

**验证**：test_tools_domain（6，含 plot_resolve/update/delete 断言）+ test_tools_extras
（8，check_text 重建断言）全绿；前端 tsc+build 全绿；codex/run 冒烟（真实 27 章统计）；
BACKEND-MAP 工具表 23→27。

**并行会话**：S103 书→技能链路（另一个智能体）与本次无冲突（skill_refine 区未碰）。

## S107 日志审计补全（已完成 ✅）——请求访问日志 + 前端错误捕获 + record 耗时 + 异常堆栈

**背景（主人问询）**：日志是否不全——上下文/思维链/工具调用参数与结果已有
（records/events.jsonl），缺"跨层关联 + 耗时 + 错误传播"。落地前四项：

- **① 请求级访问日志**（app.py middleware）：写操作 + 非 2xx + 慢读请求（≥2s）
  记 方法/路径/状态码/耗时——前端报错时后端可查对应请求；异常由既有
  _unhandled 兜底（traceback 落盘）。控制日志量（读请求不刷屏）
- **② 前端错误捕获**（lib/errorLog.ts + main.tsx + 设置页）：window.onerror /
  unhandledrejection → localStorage 环形缓冲（50 条），设置→关于 tab 可
  查看/导出 JSON/清空——前端 bug 从零落盘变有痕
- **③ record 加耗时**（core/loop.py）：model_ms（模型响应耗时）+ tool_results 每条
  附 ms（工具执行耗时缓冲 _tool_ms，record 事件消费）——性能类 bug（哪个工具慢/
  模型卡在哪轮）可定位
- **④ 异常堆栈**：模型调用失败路径加 exc_info（此前 warning 无堆栈）；全局
  _unhandled 已有（S 早期）

**踩坑**：loop.py 函数内局部 `import time as _time` 会遮蔽顶部 import 导致
UnboundLocalError（Python 函数作用域规则）——删局部 import 保留顶部。

**验证**：test_tools_domain/test_retry 9 passed；前端 tsc+build 全绿；冒烟
（404/写操作访问日志落盘；record 含 model_ms + 工具 ms——47ms/15ms 与模拟吻合）。

## S108 工具迭代上限 16→32（已完成 ✅）

**背景（主人怀疑）**：16 轮上限太小——pi 无硬上限（靠 shouldTerminateToolBatch
智能终止 + 取消），16 是 S21 自加的保守防线。

**数据验证**（data/records 79 会话）：
- 6% 会话（5 个）撞 16 轮上限，最大 19 轮
- 撞顶会话工具序列抽查：全部为**递进式真实写作流程**（读章→查设定→写→改→
  登记伏笔→查技能），**非死循环**——是任务被硬截断（用户看到"达到最大工具
  迭代次数已终止"而任务未完成）

**改动**：core/loop.py max_tool_iterations 16→32（32 次模型调用最坏 ~2 分钟，
给足复杂任务空间；智能终止/取消仍是防死循环主力，硬上限仅最后防线）。

**验证**：14 passed + ruff 全绿。

## S108b 对齐 pi：去硬上限 + 重复检测智能停止（已完成 ✅，修正 S108 的 16→32）

**背景（主人定调）**：按 pi 的做法而不是硬防线——pi 的 agent-loop.js **无迭代硬上限**，
防死循环靠：① shouldTerminateToolBatch 智能终止（工具声明 done 即停，S27 已移植）
② stopReason=error|aborted ③ length 截断防护（S22 D3）④ shouldStopAfterTurn 钩子
⑤ 用户取消。AnySpark 移植了 ①②③⑤，缺 ④、多余硬上限。

**改动**（core/loop.py）：
- max_tool_iterations 默认 **None（无硬上限）**，设值仅作保守兜底（不触发）
- 循环 for-range → while True + 可选上限检查
- **重复调用检测**（对齐 pi shouldStopAfterTurn 钩子位）：连续 6 轮工具调用签名
  完全相同（name+参数）→ 判定死循环停止报错——智能停止非硬限：递进式任务
  （每轮不同参数）永不误伤，真死循环拦截
- 前端 ProgressIndicator：maxIterations=null 时显示"第 N 轮"不带百分比

**验证**：死循环 5 轮被拦截（error 明确）；递进任务跑满 20 轮（超旧 16 上限）
正常终答；core/app 37 测试 passed + 前端 tsc/build 全绿。

**边界说明**：完全无上限后，模型故障（持续产出非重复工具调用且不终答）靠用户
取消兜底（前端 stop 按钮 + 后端协作式取消）——与 pi 一致，非硬防线。

## S109 截断修复——正文截断告知边界 + 阈值调大（已完成 ✅）

**背景（主人扫描）**：全仓截断审计——records 383 轮输出截断 0 次（max_tokens=8192
未触发过，但写超长章有隐患）；代码 20 处 [:N] 切片，6 处为**无提示正文截断**
（模型不知道内容被截，基于不完整信息产出）。

**关键设计问题（主人）**：告知截断后模型能补读吗？——分场景：
- **agent 工具循环**（审读）：✅ 能——read_chapter 返回完整章节无截断，告知+引导
  read_chapter 即补救
- **路由直调**（摘要/改写/批量/方向/候选/查证）：❌ 不能（一次性 LLM 调用无工具）——
  只能调大阈值 + 超限告知边界（至少模型不臆测后半章）

**改动**：
- 摘要 4000→12000 + 超限告知（当前最长章 5263 全覆盖）
- 改写原文 3000→8000 + 超限告知；已知设定 2000→4000 + 超限告知
- 批量改写/批量审读：全文给足（不截），>20000 告知边界
- 工作流章节注入 8000→15000 + 超限告知
- 审读（agent 循环）>20000：告知 + 引导 read_chapter 补读
- 图谱事实查证 2000→8000

**验证**：21 passed + ruff/mypy 全绿；当前最长章 5263 字 < 12000 摘要不再截断。

## S110 单 exe 发布白屏修复（已完成 ✅）

**背景（主人实测）**：S109 单 exe 双击后**白屏**。根因：webview 用 `file://` 协议
加载 index.html，而 Vite 构建产物的 `/assets/*` 是**绝对路径**——file:// 下解析到
磁盘根目录，JS/CSS 找不到 → 窗口白屏（后端其实已正常启动，data/ 已生成）。

**修复**（packages/desktop/src/anyspark/desktop/__init__.py）：
- 桌面壳改为**等待后端就绪后加载 `http://127.0.0.1:{port}/`**（后端同端口
  mount StaticFiles serve 前端，`/assets/` 由 FastAPI 正确解析）——不再用 file://
- 新增 `_wait_backend`：轮询 `/api/health` 就绪（超时 30s 也照常打开，
  端口被占时页面仍可访问，用户看到明确错误而非静默无响应）

**验证**：全新临时目录启动——`http://127.0.0.1:8790/` 返回完整 HTML、
`/assets/index-*.js` 200（1.4MB）、窗口 "AnySpark v4" 正常创建 + webview 子进程；
API 全通（health/chapters/explore-dims 200）。

**同时清理**：上级目录 3 个过时发布产物（便携版 zip——S109 前 venv 路径绑定
问题版；发布-exe 目录 + zip——S109 第一版白屏 bug 版），保留最新发布目录 + zip。

**注意（勿回退）**：前端产物必须由后端 serve（http），禁止改回 file:// 加载。

## S109b 发布方案改造——单 exe 发布（零依赖零路径绑定）+ frozen 路径兼容（已完成 ✅）

**背景（主人）**：启动方案/发布包绑定固定路径，发给用户后要自己改路径才能打开。
根因：便携版 zip 打包了 .venv，其中 pyvenv.cfg 写死本机 Python 路径
（home=E:\environment.Windows），别人解压后 anyspark-server.exe 找不到解释器。

**方案**：PyInstaller 打独立 exe（自包含 Python+前端+依赖，无路径依赖）+ 数据放 exe 同目录。

- app.py：frozen 模式下资源根=_MEIPASS（只读：frontend dist/.env 模板/reviewers），
  数据根=exe 同目录 /data（可写可拷贝）；.env 缺失时自动从模板生成到数据根
- logging.py：frozen 日志路径=exe 同目录 data/logs
- desktop/__init__.py：frozen 前端产物路径=_MEIPASS/frontend/dist
- anyspark.spec：datas 补 .env.example + 系统评审员；tiktoken 编码表（cl100k_base）
  收集（缺了 ValueError: Unknown encoding）；ROOT 改用 SPECPATH 直接解析
- scripts/package_release.py：+--exe 模式（build 前端→pyinstaller→exe+使用说明→zip）

**验证**：exe 在全新临时目录启动——data/ 自动创建、.env 模板自动生成、health ok、
后端完整运行（chat 401 为模板 key 占位，符合预期）；发布 --exe --zip 产出
AnySpark.exe 24.5MB + 使用说明 + zip 24.1MB。（S110 修复其 file:// 白屏缺陷）

## S111 网络查询对齐 pi-web-toolkit（已完成 ✅）

**背景（主人 2026-08-13）**：网络搜索是独立扩展（enable_search 按需注册，S15 解耦），
既然解耦就该达到与 pi-web-toolkit 同等水平。实测对比发现差距：固定 360 优先
（英文查询质量差）、摘要残留 `>关注` 前缀与末尾重复域名垃圾、混入低质结果
（ai.so.com 问答框/wenku.so.com 文库模板/电商/抖音）、无抓正文工具（搜索不闭环）。

**实现**：
- `tools_web.py`（对齐 pi-web-toolkit search.ts 降级层 + 超越）：
  - **按语言选引擎**：英文 → Bing 优先，中文 → 360 优先（`_detect_language` 按 CJK 占比，
    `_prefer_engine` 显式 language 可覆盖；对齐 Pi `opts.language === "en" ? "bing" : "so"`）
  - **摘要清洗**：正则吃掉容器 `>` 前缀 + 截到 `</span>`（消除 `>关注` 前缀垃圾与
    g-linkinfo 末尾域名重复）；cleanText 用 html.unescape 全量实体解码（比 Pi 手写实体表更全）
  - **低质过滤** `_is_junk`：ai.so.com（360 AI 问答框）/wenku.so.com/wenku.baidu.com
    （文库模板）/ftxia/taobao/tmall/jd/1688（电商）/douyin（短视频）剔除
  - **Bing ck/a 新格式 base64 解码** `_decode_bing_target`（旧格式 URL 编码 + 新格式 base64
    双兼容；Pi 只处理 URL 编码格式，实测 cn.bing 已切 base64，这是 Pi 降级层的隐藏 bug）
  - **跑偏拦截** `_results_relevant`：结果标题/URL 与 query 共享 ≥2 实词才放行——cn.bing
    英文长查询偶发严重跑偏（实测 Krasznahorkai → Reddit 橄榄球、quantum → 词典定义），
    拦截后降级另一引擎（Pi 降级层无此保护）
- **新增 `tools_fetch.py`**（对齐 pi-web-toolkit webfetch）：`fetch_page` 抓网页正文转纯文本，
  UA 伪装 + 5MB 上限 + 20s 超时 + 噪音标签（script/style/nav/footer/aside/iframe）剔除 +
  title 提取 + 正文截断。**搜索闭环**：search_web 拿线索 → fetch_page 读全文
- `toolkit.py`：enable_search 名下同时注册 search_web + fetch_page（一个开关点亮整套考据能力）

**验证**：
- 单测 21 全绿（新增：摘要前缀清洗/引擎选择/低质过滤/base64 解码/跑偏判定/HTML→文本/截断）
- 实测中文查询（诺奖/DeepSeek）：摘要干净无垃圾、wenku/ai.so 低质结果消失，0.5~0.9s
- 实测英文查询：Bing 跑偏自动降级 360 返回真实相关结果（Krasznahorkai→sohu/163/chinadaily；
  quantum→odaily/新华/中国网），URL 正常（base64 已解）
- fetch_page 实测抓中华网全文：标题 + 正文 800 字，1.3s
- ruff + mypy 干净；app 全量 pytest 通过（仅 S108 遗留红 test_tools_extras 与本改动无关，
  stash 验证 pre-existing）

**说明**：Pi 的 MCP 层（Exa/Parallel，带 published/author 元数据）需外部服务密钥，
AnySpark 零依赖设计不背（对齐目标 = Pi 的 360/Bing 降级层 + webfetch，已达成并超越）。

## S112 补 MCP 层——Exa/Parallel 无密钥公开端点（已完成 ✅）

**背景（主人 2026-08-13）**：主人指出"Pi 的 Exa MCP 不需要密钥"。核实 pi-web-toolkit
`mcp.ts`：`EXA_URL` 未配 key 时直接落 `https://mcp.exa.ai/mcp`（公开端点），
Parallel 同理 `https://search.parallel.ai/mcp`——Pi 的 MCP 层确实无密钥。
AnySpark 零依赖约束下用 urllib 即可调（JSON-RPC over HTTP），不必背 MCP 就缺失。

**踩坑（关键）**：urllib 直连 Exa/Parallel 报 403 Forbidden——根因不是密钥，是
**默认 UA（Python-urllib/3.12）被 Cloudflare 拦截**；加 Chrome UA 头即 200。
（Pi 注释说"curl 被 TLS 指纹拦截"——curl 与 urllib 的 TLS 指纹不同，urllib+UA 实测可直连）

**实现**（tools_web.py，纯扩展文件）：
- `_mcp_call`：urllib JSON-RPC 2.0 over HTTP，纯 JSON + SSE 双格式解析（对齐 Pi extractMcpText）
- `_exa_search`：tool `web_search_exa`，参数对齐 Pi（type auto / numResults / livecrawl fallback /
  contextMaxCharacters 8000）；返回人类可读块（Title/URL/Published/Author/Highlights）
- `_parallel_search`：tool `web_search`（objective + search_queries）；返回 JSON results[]
- `_parse_exa_text` / `_parse_parallel_text`：两块格式解析成 WebResult（新增 published/author 字段，
  向后兼容默认空）；N/A 归一为空；只收 http(s) + 非空标题
- `search_web` 流程升级：**MCP 优先（exa → parallel）→ 360/Bing 降级**（对齐 Pi auto 顺序）；
  provider 参数 auto/exa/parallel/web + 环境变量 `ANYSPARK_SEARCH_PROVIDER` 覆盖（对齐
  Pi 的 WEBTOOLKIT_SEARCH_PROVIDER）；MCP 失败/空/低质自动降级
- `render_results`：带发布时间/作者元数据时渲染 `（发布于 2026-04-13）作者：xxx`

**验证**：
- 单测 25 绿（新增 4：Exa 块解析/Parallel JSON 解析/SSE+JSON 提取/provider 顺序）
- 实测中文「2026年诺贝尔文学奖」：Wikipedia EN/ZH + 中华网（带发布时间 2026-04-13），1.8s
  —— 与 Pi 今天返回的结果同源同档（nobelprize/wikipedia/中华网）
- 实测英文「Krasznahorkai 2025 Nobel」：NobelPrize.org 官方源（带 2025-10-15 日期 + 作者），1.4s
  —— 质量高于 360/Bing 降级层一个档次（官方权威源 + 元数据）
- 降级路径未破坏：provider=web 强制 360/Bing 仍正常（0.8s，摘要干净低质过滤）
- ruff + mypy + format 干净

**对标结论**：至此 AnySpark 搜索 = Pi 完整三层（MCP exa→parallel → 360/Bing 降级 + 跑偏拦截/
base64 解码等 Pi 降级层没有的增强），且**全程零依赖（urllib）无密钥**，与 Pi 持平并部分超越。

## S114 拆书三层模型（结构感知选章 + 骨架扫描 + 定点精读，实测驱动）（已完成 ✅）

**背景（主人讨论，2026-08-13）**：S106 拆书（16 段字符均匀抽样+归并）对文风够用，
但抓不到全书级叙事机关。主人用《猎手准则》（367 万字/1281 章，E:/Desktop/新建文件夹）
实测验证：均匀抽样只覆盖 5%、字符窗口切碎章节边界，**两份 skill 都没发现"时间回环"
结构（主角穿越回过去发现经历受过去的自己安排）与主角最终目的（重启世界/抹除过去/
缔造新世界）**。原文证据："回到过去"12 处集中 72-90%（第零战院/时间机器/渊蛇），
"重启"7 处含结局 99.8%（"我的目标，也只会是未来"）。

**核心洞察（讨论定案）**：抽样+局部提炼+归并**结构上抓不到**跨全书全局关系（回环需
"把第30章与第700章连起来看"）。但骨架扫描（仅卷+章标题轨迹，无正文）能——猎手准则
标题含《坏档》《重开》《第零战院和时间机器》《过去，未来，造物主》，模型据标题轨迹
推断"时间循环/世界重置"机制 + 主角目的，两次实测稳定。

**实现**（packages/align/src/anyspark/align/skillgen.py，generate_book 三层）：
- ① **微观方法论**：`_generate_book_micro`——按卷分层选章（首/25%/75%/尾+全书首尾，
  `_select_structural_chapters`）+ 整章拼批（`_build_batches`，章节边界完整）→ 分批拆解
  → MERGE 归并成「书名」skill（target=both）。无章结构（<5 章）回退 S106 字符均匀
  （`_generate_book_uniform`，保留 last_error 机制）
- ② **骨架扫描**：`_scan_skeleton`——全部章标题（无正文）→ SKELETON_PROMPT → 结构笔记
  （跨卷机关/主角目的/阶段，引用章号）
- ③ **定点精读**：`_refine_architecture`——笔记机关关键词定位原文直接揭示段
  （`_locate_mechanism_passages`，如"回到过去""世界重启"）+ 机关章（笔记章号）+ 首尾章
  → 精读提炼架构技法 skill（target=main，如「坏档与重开：时间循环式叙事」）

**关键坑（实测）**：
- 书名必须注入（book_name 参数，routes_library/tools_domain 传书库书名）——否则模型自编
  （对照组编成"赵光离的克苏鲁冒险"）
- "先原文后提问"的 prompt 措辞**挡不住案例编造**（实测仍幻觉"神国墙壁"），必须机器校验
  兜底：`_sanitize_examples`——example 引号句必须逐字在精读片段，否则清空为
  "（无合适摘录）"（宁缺毋滥）
- 精读片段必须含机关直接揭示段（笔记引用章头未必覆盖，回环揭示常在章中后部）
- 骨架笔记注入精读仅作线索（标注"仅供参考需原文验证"），防"先给答案→编造"

**验证**：
- 实验（data/dev/experiments/book_split_20260813/）：对照组（均匀抽样，634s/17 调用）
  vs 实验组（结构感知，219s/7 调用）——实验组快 3 倍 + 维度更全 + 能引用章节号
- 端到端真实拆书《猎手准则》：候选1=书名方法论（name=猎手准则 ✅，1584 字，案例真实）；
  精读产出 3 条架构技法，第一条「坏档与重开：时间循环式叙事」（target=main）——
  **回环被发现**；example 全部机器校验通过（零编造）
- 测试：test_skillgen 24 绿（新增结构感知三层/书名注入/案例校验 3 项）+ test_library_refine
  绿（多草稿兼容）；ruff/mypy 干净
- gate：本面绿；总闸被并行会话 S108b 遗留红挡住（test_tools_writing ruff/mypy +
  test_tools_extras read_material，S109 已标注未触碰）
