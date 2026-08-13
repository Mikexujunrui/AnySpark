# AnySpark v4 进阶设计提案——从 DeepSeek Harness 借鉴的工程升级 + 内容生态基础设施

> **性质**：讨论稿（非主规格）。结论未定稿，不进入 DESIGN.md——讨论拍板后再
> 更新主规格 + 排期实现。
> **缘起**：2026-08-13 主人要求对比本地项目与 DeepSeek Harness（机器之心报道，
> DSH 今日随 V4 Pro 开源，github.com/deepseek-ai/deepseek-harness）。
> 对比结论：定位不同（AnySpark=小说创作专用引擎，DSH=通用智能体框架），
> 领域能力 AnySpark 完胜；但 DSH 有三项通用工程做得更系统，值得借鉴。
> 随后讨论延伸出**生态战略**与**内容生态基础设施**（提案 D）——后者是
> “内容生态放开”战略的落地第一刀。
> 本文档把这些写成待做设计，供讨论。

---

## 0. 背景：对比结论速览

| 维度 | AnySpark 现状 | DSH 做法 | 差距 |
|---|---|---|---|
| 会话日志 | S49 RunRecorder：每轮快照（prompt/output/tool_results）落 JSONL | **Session Log 事件溯源**：一切模型所见可从日志重建（含压缩/路由/权限/steering 事件） | 有快照无"过程事件"——模型看见什么有了，**为什么是这份**（压缩了什么/注入了什么/切了什么模型）没有 |
| 多 Agent | workflow agent 节点 = 干净单次调用（无工具循环）；评审团/推演是替代品 | **subagent 委派**：主 Agent 派任务给子 Agent，作用域隔离，并行；workflow=脚本驱动编排 | 无真正的子 Agent 执行——调研/收集/并行起草等“固定流程外包重活”做不了（不占主循环上下文） |
| 沙箱安全 | codex run_code：白名单 + 只读数据环境 ws_* | **失败关闭原则**：无法确认隔离生效 → 拒绝执行（不静默降级） | 白名单是"允许清单"思路，缺"隔离确认"底线 |

三项的共同点：都是**把“发生过什么”变成可审计、可复现的系统事实**——
AnySpark 已有一半（records 快照），缺的是另一半（过程事件 / 执行委派 / 隔离底线）。

### 0.1 生态战略结论（已讨论确认，2026-08-13）

与 DSH 对比后延伸出的战略判断：

1. **插件化 ≠ 我们的解耦化**：DSH 解耦的是能力边界（接口/实现/消费者三层，可拔插换），
   AnySpark 解耦的是机制 vs 内容（机制硬编码、内容自然语言）。插件化回答“同一引擎
   怎么变成不同产品”；我们要回答“一个产品怎么把小说写好”。插件化的抽象层代价
   （每次调用多跳层）写作长文本场景扛不住；用户是写作者不是开发者。
   **结论：不做插件化微内核（见 §5 不做清单）**
2. **能偷的边界**：DSH 是 TS/Node + Cordis——插件代码不能搬（语言+框架墙）；
   **能偷三样**：① 设计思想（事件溯源/工具流水线/失败关闭，即本提案 A/B/C）
   ② 能力清单（工具对照补缺）③ 数据形态内容（skill/模板/prompt 若同构可直接导入）。
   墙是保护：借鉴思想不背其运行时/依赖包袱。
3. **生态战略**：内容生态放开（skill/模板/设定/评审员 yaml——价值在内容不在代码），
   代码生态谨慎（保持 P5 人工批准模式，不做插件市场）。
4. **自定义前端**：已是 API 优先（187 端点 HTTP），第三方前端天然可接（S75 合作者
   前端即证据）——无需新开发；“用户自定义 UI 布局”技术上可行但 YAGNI（见 §5）。
5. **资料库双层缺口**（详见提案 D）：全局池→项目池有通道，反向没有；上传端口
   只有项目内（book_id），无全局；**skill 无文件导入通道**——内容生态的货币不通，
   生态是死的。

---

## 1. 提案 A：会话事件溯源升级——"模型所见可重建"

### 1.1 现状盘点（已核实）

S49 RunRecorder 已记录（`data/records/<conv>/events.jsonl`，每轮一行）：

```
{
  turn_index, model_ms,
  prompt: [{role, content}...],        # 模型请求的完整消息快照 ✅
  output: {text, reasoning, usage, tool_calls, truncated},
  tool_results: [{name, ok, content, ms}]
}
```

**已经很强**：prompt 完整快照 = 模型当时看到的输入。修 bug / 训练心智模型的素材齐了。

**缺口**（与 DSH Session Log 的差距）：
1. **无系统事件**——上下文压缩发生时（S8 两阶段压缩）、注入块被裁剪/降级时（S55 分层缓存）、模型路由切换时（S98 mode 分流）、steering 插话注入时（S25），records 里**没有对应事件**。回放时只能看到"最终 prompt"，看不到"中间发生了什么变换"。
2. **无权限/审批事件**——扩展工具批准/拒绝（S48-P5）、评审员加载失败等，不在记录里。
3. **无因果关联**——压缩前 40K 上下文被压成 8K，压缩事件与 prompt 快照之间没有 id 关联，无法回答"这条 prompt 是基于哪份被压缩的历史生成的"。

### 1.2 目标原则（对齐 DSH）

> **凡是模型看见的内容，都必须能够从日志中重建；凡是改变模型输入的操作，都必须留下事件。**

具体三条：
- P-A1：现有每轮 prompt 快照保留（已经是重建基础）
- P-A2：新增**系统事件流**（与轮快照同文件追加，`type` 区分）：`context_compressed`（压缩前后 token/块签名）、`inject_cut`（注入块被裁剪：块名+原因）、`model_switched`（旧/新配置+原因）、`steering_injected`（插话文本+注入轮次）、`tool_approved/denied`、`reviewer_load_failed` 等
- P-A3：事件与轮快照通过 `turn_index` 关联；压缩事件记录**被压缩的轮次区间**（如 [3,7]），回放时可还原"第 8 轮 prompt 是从第 3-7 轮压缩而来"

### 1.3 设计

**A. 事件类型注册表**（`core/events.py` 扩展，机制硬编码）：

```python
EventType = Literal[
    "record",              # 已有：轮快照
    "context_compressed",  # 新增：{from_turn, to_turn, before_tokens, after_tokens, kept_ids}
    "inject_cut",          # 新增：{block, reason, char_dropped}
    "model_switched",      # 新增：{task, old_id, new_id, reason}
    "steering_injected",   # 新增：{text, at_turn}
    "tool_approved",       # 新增：{tool, approved, by}
    "runtime_warning",     # 新增：{origin, message}（评审员加载失败等非致命告警）
]
```

**B. 发射点**（各组件 emit 事件，recorder 统一订阅落盘）：
- `loop.py`：压缩前后（现有压缩调用处）emit `context_compressed`
- `app.py` 注入装配：S55 分层缓存裁剪时 emit `inject_cut`
- `ModelProvider`：S98 mode 分流实际切换时 emit `model_switched`
- `chat` 路由：steer 注入时 emit `steering_injected`
- 扩展工具批准端点：emit `tool_approved`

**C. 落盘与查询**：
- 与轮快照同文件追加（`events.jsonl`），`type` 字段区分，不破坏现有格式（向后兼容）
- 新增只读端点 `GET /api/records/{conv_id}`（返回事件序列，前端会话回放面板可展示"压缩/切换/注入"标记）

**D. 影响面**：
- `core/events.py`（类型注册）+ `core/loop.py`（压缩事件）+ `app.py`/`routes_mode.py`/`routes_chat.py`/`routes_tools.py`（发射点）
- `recorder.py`（无需改：已是通用订阅）
- 前端：会话详情面板加"系统事件"tab（可选，二期）
- 无 DB schema 变更（JSONL 追加）

### 1.4 验证标准

- 单元：mock 一次完整会话（含压缩/裁剪/切换/steering），断言 events.jsonl 事件齐全且 turn_index 关联正确
- 集成：真实跑一次长会话触发压缩，records 中出现 `context_compressed` 且压缩区间可还原
- 回归：现有 424 测试全绿（record 事件格式不变）

### 1.5 讨论点（已定结论）

- Q1：系统事件存储——**JSONL 追加（保持现状，已确认）**：消费方只有修 bug/回放，
  无人做跨会话检索；真要统计 JSONL 可用脚本扫。SQLite 等有真实需求再升
- Q2：`inject_cut` 块名+原因——**仅记录，前端默认折叠（已确认）**
- Q3：压缩事件内容——**只留 token 数 + 轮次区间，不保留被压缩原文（已确认）**：
  历史轮快照本来就在 records 里，保留原文=重复存储；重建从源头重放即可

---

## 2. 提案 B：子 Agent 内核 + workflow 固定流程执行器

### 2.1 现状盘点（已核实）

- workflow 包（S59）：节点 `agent/script/approval/gate/loop`——**agent 节点 = 干净单次 LLM 调用**
  （无工具循环；runner 在 app.py 是 instruction → 一次 respond → 返回）；script = 确定性函数
  （read/review）
- 评审团（S65）：拟人化面板，非执行委派
- play 推演（S65）：角色多选推演，非执行委派
- **结论（S114 定案）**：AnySpark 没有真正的子 Agent 执行能力——既不能主循环委派，
  workflow 也干不了“搜索→读多页→提炼→整理”这类**多步工具活**（agent 节点无工具循环）

### 2.2 目标场景（S114 定案：workflow = 任何可固定流程的工作，不只是写作）

1. **调研/收集资料（主人提出，最高频）**：写小说前调研——子 Agent 用网络搜索
   （search_web/fetch_page）+ 读参考书（library/read_book）收集资料 → 整理成报告
   落项目资料池 → **不占主循环上下文**（fresh 隔离，产出物进 materials 按需检索）
2. **并行起草**：写 5 章时，5 个子 Agent 各起草一章（各自干净上下文，互不污染），主 Agent 汇总衔接
3. **分工调查**：子 Agent A 查图谱+设定，子 Agent B 检索正文+提炼 skill，主 Agent 综合
4. **多版本比稿**：3 个子 Agent 用不同技法 skill 写同一章，主 Agent/评审团选优
5. **批量审读**：子 Agent 各自审读一章（现有 batch_review 是“路由直调”，升级为委派后可带各自上下文）

### 2.3 设计（S114 定案：机制一份，两个入口——workflow 优先落地）

**核心统一（主人洞察）**：调研工作流（搜索/读书/收集 → 不占主循环）本质就是
`run_subagent` 的模板化形态——**同一套子 Agent 内核，两个入口**，不是两个功能。

**A. 子 Agent 内核（loop 层，机制一份，地基）**

```python
# core/loop.py（或新 core/subagent.py）
run_subagent(
    instruction: str,
    context: {mode: "fresh"|"fork", inject: [...]},   # 上下文策略
    scope: {tools: [...], books: [...]},               # 工具白名单/作用域
    budget: {max_turns: 10},                           # 护栏
) -> SubagentResult(output, output_key)
```

- 独立上下文（fresh 默认：不受父会话污染；fork：从父会话某边界派生，对齐 S58c）
- 工具白名单（默认最小只读为主，写操作需显式授权）
- 护栏：≤3 个/会话，每个 ≤10 轮（硬上限；S108b 智能停止保留）
- 注入由父 Agent/模板点名（对齐 S60 主循环点名注入哲学）

**B. workflow agent 节点升级（模板化子 Agent，第一个落地）**

- agent 节点从“干净单次调用”升级为“**跑完整工具循环**”（调用子 Agent 内核）
- 节点 params 增加 `delegate` 语义：`{instruction, context, scope, budget}`
- **调研工作流模板**（首个真实场景，可复用可参数化）：

```yaml
- id: n1
  kind: agent
  delegate: {context: {mode: fresh}, scope: {tools: [search_web, fetch_page]}}
  params: {instruction: "围绕主题搜索+抓取 3-5 页，输出来源清单+要点"}
- id: n2
  kind: agent
  delegate: {context: {mode: fresh}, scope: {tools: [library_book, read_book]}}
  params: {instruction: "从参考书库摘录相关章节，输出摘录"}
- id: n3
  kind: agent
  params: {instruction: "合并 n1+n2 产出 → 结构化调研报告"}
- id: n4
  kind: agent
  scope: {tools: [material_register]}
  params: {instruction: "报告写入项目资料池（materials, kind=inspiration）"}
- id: n5
  kind: approval   # 人工确认 → 报告入项目池
```

主循环调用：`run_workflow("调研", {主题})` → 后台跑 → 完成回传一句
“报告已入项目池（N 来源 + M 要点），未占用主循环上下文”。

**C. 主循环自由委派（对话即时用，二期）**

- `run_subagent` 注册为主循环工具：对话里随口“帮我查一下这个设定冲突”→ 主 Agent 直接委派
- 复用同一内核与护栏，仅入口不同

**D. 并行**：多个委派节点可 `parallel: true`（复用 S28 后台队列/线程池思路；
读并行 + 写串行队列，零新依赖）

### 2.4 验证标准

- 单元：子 Agent 内核——委派返回结构化结果；fresh 上下文隔离（父子 prompt 无交集）；
  工具白名单生效；预算护栏（超轮数停止）
- 集成：调研工作流真实跑通——搜索+读书+整理 → 报告入项目池 → 主循环上下文无污染
- 集成：3 子 Agent 并行起草 3 章 → 主 Agent 汇总（记录 token 成本）
- 回归：现有 workflow/play 测试全绿

### 2.5 讨论点（已定结论）

- Q4：委派入口——**机制一份（loop 层子 Agent 内核），两个入口（已确认）**：
  workflow agent 节点升级（模板化子 Agent）**优先落地**——固定流程外包重活（调研/收集/批量）
  是更高频真实需求，且白得 S59 断点恢复/失败策略/确认闸门；主循环 run_subagent 工具二期
  （对话即时委派，复用同一内核）
- Q5：子 Agent 心智档位——**不需要（已确认）**：子 Agent 自由度 ≤ 父命令边界
  （严格遵照委派指令，可显著低于父，上限天然由指令边界保证）；档位只在父会话层
  存在；子 Agent 要的是注入内容（设定档/技能），不是心智状态
- Q6：并行委派 SQLite 并发——**复用 S28 后台队列串行化写操作（已确认）**：
  子 Agent 读多写少，读并行（SQLite 读不冲突）+ 写串行队列，零新依赖

---

## 3. 提案 C：codex 沙箱"失败关闭"原则

### 3.1 现状盘点（已核实）

- `/api/codex/run`：`run_code(code, timeout, data_env=make_data_env(...))`
- 安全模型 = **白名单**：只读数据环境 ws_*（真实统计/自定义分析），不允许任意文件写
- 问题：白名单是"允许清单"思路——**如果隔离机制本身失效（如环境变量被注入、路径逃逸、意外获得写权限），当前实现没有兜底检查**，可能静默继续执行（带着本应被禁止的能力）

### 3.2 目标原则（对齐 DSH）

> **失败关闭（fail-closed）**：如果系统无法确认隔离真正生效，就拒绝执行——绝不静默退化为无保护运行。

### 3.3 设计

**A. 隔离确认清单**（`run_code` 执行前检查，全部通过才运行）：
1. `cwd` 在允许根内（数据区只读副本，非项目根）
2. 无写权限的路径前缀已注入 deny 规则（sandbox deny 写 `chapters/`、`data/workspace/*/chapters`）
3. 环境变量白名单：剥离 `DEEPSEEK_API_KEY` 等敏感项（子进程环境 = 最小集）
4. 超时已设（默认 30s，上限 120s）——无超时 = 拒绝
5. 字节码编译通过（语法错直接拒绝，不执行半截）

**B. 失败关闭行为**：任一检查不通过 → 返回 `{"ok": false, "error": "沙箱隔离未确认：<原因>"}`，**不执行**；同时 emit `runtime_warning` 事件（提案 A 的事件流）

**C. 审计**：每次执行记录（用户/代码指纹/检查结果/耗时）——对齐 DSH"权限切换入 Session Log"

**D. 影响面**：
- `packages/app/src/anyspark/server/codex.py`（run_code 前置检查）
- `routes_tools.py`（错误返回格式，前端已有错误展示）
- 无 DB 变更

### 3.4 验证标准

- 单元：注入写路径/敏感环境变量/无超时 → 全部拒绝且报原因
- 集成：正常只读统计仍可跑（回归现有 codex 测试）
- 安全：尝试 `open('chapters/x.md','w')` → deny；尝试读 `os.environ['DEEPSEEK_API_KEY']` → 空

### 3.5 讨论点（已定结论）

- Q7：写路径 deny——**先 Python 层路径前缀判断（已确认）**：零依赖跨平台；
  OS 级 ACL 二期（对抗性威胁才需要，当前白名单主要防误操作）
- Q8：codex 恢复执行——**不做（已确认，YAGNI）**：检查不过用户改代码重提即可，
  多一套状态机收益≈0

---

## 4. 提案 D：内容生态基础设施——skill 文件导入/导出 + 全局通道（生态第一刀）

### 4.1 现状盘点（已核实）

- `writing_skills` / `skill_drafts` 表**无 book_id**——skill 天然全局（所有项目共享）✅
- skill 创建通道仅两个：`POST /api/skills`（JSON 手填五段式）+ `POST /api/skills/generate`（原文提炼）
- **无文件导入通道**——拿到别人分享的 skill 文件只能手工把 5 个字段粘进 UI（非技术用户做不到）
- 资料库双层（§12.39）：全局池→项目池有（import/promote）；**项目→全局无通道**
- 上传端口仅项目内：`POST /api/upload`（必须带 book_id）+ `POST /api/ingest`（消化，带 book_id）；
  `POST /api/library`（全局书库，但它是整本书不是卡/技能）

### 4.2 设计决策（已讨论确认）：复用上传区 + 判别路由，不建独立功能

上传区 ingest 管线本来就是“文件→判别→路由”（chapterize → is_card → 摘要卡/拆章），
skill 是**第三种判别结果**——上传区只加一个分支，不新建存储、不加新入口 UI：

```
上传 skill 文件（任意 book_id）
  → /api/upload 存原始档（现有逻辑零改动）
  → /api/ingest 判别分支：front-matter 有 name+target → kind="skill"
      → 解析五段式 → skill_drafts（草稿，全局）——复用现有表
      → 前端收到 kind=skill → SkillPanel 草稿区待确认（现有 UI/闸门）
  → 不满足 front-matter → 走原 card/chapters 分支（天然降级，防误判）
```

**关键设计点**：
- 判别要严：完整 front-matter（`--- name/target/tags ---`）或 `.skill` 扩展名才认；
  否则走原分支（普通 md 笔记不被误判）
- 进草稿不进生效：复用 S54“候选→确认生效”闸门，错误 skill 不直接进表
- agent 也能用：上传端点 agent 可调，同样走判别+草稿（人工闸门不变）

**导出闭环（分享方向）**：`GET /api/skills/{id}/export` 导出标准五段式 md（带 front-matter）——
导出格式 = 导入判别格式，分享出去的文件正好被对方上传区识别。

### 4.3 三个缺口与优先级

| 缺口 | 方案 | 优先级 |
|---|---|---|
| **skill 文件导入/导出**（生态货币） | 上述上传区判别路由 + export 端点 | **最高**（生态死活看它） |
| 全局上传端口 | `/api/upload` 允许 `book_id="global"`（或新端点），素材卡进公共池 | 中 |
| 项目→全局提交 | `POST /api/materials/publish`（复制+标来源+人工确认进全局） | 低（可后置） |

### 4.4 影响面

- `packages/app/src/anyspark/server/ingest.py`：+skill 判别分支（kind="skill"）
- `routes_skills.py`：+import 解析（或复用 add_draft）+ export 端点
- `routes_workspace.py`：upload 允许 book_id="global"（二期）
- 前端：SkillPanel 加“导入文件/导出”按钮（薄 UI）
- 零新表、零新存储（skill_drafts/上传区现成）

### 4.5 验证标准

- 单元：skill 文件导入→草稿→promote 转正；非 skill md 走原分支不误判；导出→导入格式闭环
- 集成：上传一份 skill 文件 → SkillPanel 出现待确认 → 确认后 writing_skills 可见

---

## 5. 优先级建议

| 提案 | 价值 | 成本 | 风险 | 建议 |
|---|---|---|---|---|
| A 会话事件溯源 | 高（修 bug/复盘/训练素材升级） | 低（改发射点+事件类型，无 schema 变更） | 低 | **先做**（1-2 天） |
| C 沙箱失败关闭 | 中（安全底线） | 低 | 低 | 可与 A 同批（0.5 天） |
| D 内容生态（skill 导入导出） | 高（生态货币打通） | 低-中（ingest 分支 + 2 端点 + 薄 UI） | 低 | 与 A 同批或紧随（1-2 天） |
| B 子 Agent 内核 + workflow 固定流程 | 高（调研/收集/并行起草等固定流程外包重活） | 中高（loop 子 Agent 内核 + workflow 节点升级 + 护栏） | 中（并行/成本失控需护栏） | 子 Agent 内核 + workflow 节点升级先做（3-5 天）；主循环 run_subagent 二期 |

## 6. 不做清单（YAGNI）

- 不做 DSH 的插件化微内核/自指动态插件（写作引擎价值在领域深度，不在可插拔）
- 不做 LSP 语义导航/PTY 终端（非编程工具）
- 不做 ACP/JSON-RPC 协议前门（HTTP API + CLI 已覆盖当前场景）
- 不做子 Agent 心智档位/记忆（自由度 ≤ 父命令边界，已确认）
- 不做压缩原始内容全量保留（token 数 + 区间足够，存储成本敏感）
- 不做“用户自定义 UI 布局”（拖拽面板/自定义工作区）：技术上可行（React 生态成熟），
  但北极星是“沟通成本 ≤ 写作成本”，自定义 UI 对北极星帮助很小；第三方前端走 HTTP API 已够

---

## 附：DSH 参考来源

- 机器之心《刚刚，DeepSeek Harness震撼开源：一切皆插件》（2026-08-13）
- 开源仓库：github.com/deepseek-ai/deepseek-harness
- 相关：Cordis 论文《A Programming Paradigm for Spatiotemporal Composability》
