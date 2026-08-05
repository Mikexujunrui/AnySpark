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
| S15 拼接落地 | 增强按需装配/重试可拼接/氛围归位/前端懒加载 | 总闸全绿 | ✅ 完成 |
| S16 benchmark 单元层 | 黑盒 17 任务 + 修图谱抽取无重试缺陷 | 17/17 | ✅ 完成 |
| S17 伏笔闭环 | 注入写作/自动回收/关注度 | 真实链路回收成功 | ✅ 完成 |
| S18 benchmark 对比层 | 裸 LLM 基线三任务（诚实：短程相当） | 报告已生成 | ✅ 完成 |
| S19 人工层 | 盲测材料（匿名A/B+三档打分表） | 材料待主人打分 | ✅ 完成 |
| S20 状态演化 | 角色/地点 state 增量+历史表+注入 | 真实链路验证 | ✅ 完成 |
| S21 系统层 | 分支剧本测哲学过程指标（修改率↓/说明书累积/偏好遵从），复用 /api/stats；另修复信号→说明书提炼闭环缺口 | 真实链路 A/B 分支验证通过（A:1条说明书/B:0，破折号 4→2） | ✅ 完成 |
| **Backlog**（按需） | 仅剩 httpx2 迁移（工程性，等 starlette 原生支持再迁；多线叙事已随 S29、后台独立 worker 已随 S21c 完成划除） | | ⏳ |

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
