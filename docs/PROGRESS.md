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
| S7 知识图谱 | 图谱 schema（实体/关系/时间线 + FTS）；LLM 实体抽取入库；写作时"当前时空点已知事实"检索注入；资料摘要卡图谱关联（机制 10 补齐）；检测设定冲突图谱比对（确定性校验基础） | 章节落盘后实体自动入库；写作注入当前时空点已知事实；资料卡关联图谱实体 | ⬜ 未开始 |
| S8 token+流式 | token 预算（精确计算）；prune/summarize 两阶段压缩；SSE 流式传输（core 事件协议→后端 SSE→前端 EventSource） | 长对话历史自动压缩不超窗；chat 流式输出前端逐字显示 | ⬜ 未开始 |
| S9 能动性+倾向 | 能动性协议（0-4 级：声明/解析/温度映射/反馈自动调节）；AI 倾向档案（AI 主动暴露当前倾向）；前端能动性选择器 | 写作可调档位；档位影响生成；倾向档案可读 | ⬜ 未开始 |
| S10 交互层+T2 收尾 | 低摩擦组件（氛围滑块/候选卡堆/改写渐变条/建议卡拖入）；方向声明（阶段 5）；一章收尾（更新图谱/一致性摘要卡/下一章衔接提示） | 写作中候选卡可拖入稿纸；一章完成自动收尾提示 | ⬜ 未开始 |
| S11 基建+安全+工具 | 请求级超时/重试/指数退避；幻觉检测 fake_tool/fake_write + 越界保护；工具扩展（文件读写/文档解析 txt-docx-md/多格式导出/网络搜索） | 断流自动重试；伪造工具调用被拦截；新工具可用 | ⬜ 未开始 |
| S12 收尾 | 总闸全绿；CI 同步；AUDIT-V1 全文复核更新；桌面壳/PyInstaller 回归 | 总闸全绿；AUDIT-V1 无 ❌ 遗留（除设计明确降权/后补项） | ⬜ 未开始 |

