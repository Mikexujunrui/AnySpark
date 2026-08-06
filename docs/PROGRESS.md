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

- **设计实现审计报告**：见 `docs/AUDIT-V1.md`（基准 `a08894d`：S32-S46 实测演进复核）
- **设计演进补记**：见 `docs/DESIGN.md` §12（S32-S46 变更集中追溯）
- **当前状态**：S0-S46 全部完成，pytest 207 全绿，单元层 benchmark 17/17（S32-S46 回归）
- **候选清单（下一步，按优先级）**：
  1. **心智模型系统**（设计内降权，核心候选）：包罗万象（文风/喜好/毒点/边界）+ **渐进式披露**（索引常驻/正文按需，对齐 pi skills）——manual 是雏形，需设计分类与注入时机；含档位 L2（AI 看心智后建议档位）/L3（自然语言生成档位）
  2. **对比层回归**：S18 三任务（设定忠实/长书一致/偏好记忆）在 S32-S46 后重跑（成本 ~20min）
  3. **前端 UI**（主人明确不优先）：伏笔面板/图谱可视化/设定档/技巧/计划/批量/定点编辑/影响分析均无 UI（API 全）
  4. **httpx2 迁移**（工程性）：等 starlette 原生支持
  5. **设定档渐进式披露**：条目多时分段/按需注入（当前全量）
  6. **影响分析主角线过度报告优化**：核心实体与事件线区分报告（当前主角线=全影响提示）
  7. **list_events 默认 limit**：200 对超长书截断，调用方需显式传大 limit（当前用法已知）
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
