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

- **设计实现审计报告**：见 `docs/AUDIT-V1.md`（截至 commit `9742f06`：七阶段主干✅，知识图谱/token压缩/能动性/SSE 等缺口及优先级）
- **补缺路线**：见下方「补缺阶段规划（S7+）」——P0 知识图谱 → P1 token 压缩/能动性 → P2 SSE → 其余按需
- 对接手者：先读 AUDIT-V1 再动手，补缺前向主人确认

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

