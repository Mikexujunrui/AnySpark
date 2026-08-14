# 第三方评审报告 · 第一部分：落地层面（问题清单）

> 评审基准：commit `2c0fed7`（S141 后，feat/shell-port）· 2026-08-14
> 方式：只读审计（未改任何代码）——依赖方向扫描 / 工具真实装配 / 端点-前端对账 / 测试抽查 / 文档对照
> 原则：**只列问题，不动代码**。分级：P0（真缺陷/误导）> P1（过期失准）> P2（卫生/死代码）

---

## 🔴 P0：真缺陷（会导致运行时错误或能力落空）

### P0-1 工具 `reference_lookup` 生产装配缺席——"参考书检索"能力从未对 agent 开放

**证据链**（三处代码 + 一处文档互相矛盾）：

| 位置 | 内容 | 问题 |
|---|---|---|
| `toolkit.py:192` | `if ctx.library is not None: rl_spec, rl_impl = make_reference_lookup_implementer(...)` | 注册**有条件**（library 非空才注册） |
| `agent_factory.py:71-110` | `ToolContext(...)` 装配**没有传 `library=`** | 生产装配中 `ctx.library` 恒为 None → **reference_lookup 永不注册** |
| `scripts/current_state.py:99-117` | 同款 ToolContext，**也没传 library** | 审计装配同样缺——S141 审计结论"46 工具全量注入"掩盖了该工具缺席 |
| `tools_writing.py:469` | `"查参考书用 reference_lookup——read_file 只读沙箱笔记文件。"` | 引导 LLM 调用一个**不存在的工具** → 运行时必然"工具未找到" |
| `routes_library.py:5` | `"检索走 agent 工具 reference_lookup（只读）"` | 设计声称与实现不符 |

**旁证**：`app.py:913` 创建了 `library = LibraryStore(real_db)` 且注入 AppDeps，但 **agent_factory 没有把它转发给 ToolContext**——断链点在装配层。`test_reference_lookup.py` 直接调 `make_reference_lookup_implementer`（单元级），**没有"装配后注册"的集成断言**，所以全绿也发现不了。

**唯一可用路径**：workflow 的 `query_reference` script 函数直接调 `search_reference_books`（`app.py:1149`），绕过了工具层——但这是"工作流专属"，主循环 agent 用不到。

**建议动作**：`agent_factory.py` 装配补 `library=deps.library`；补一条集成测试断言 `reference_lookup in registry.specs()`；顺带修 current_state.py（见 P1-4）。

---

### P0-2 前端"校验一致性"按钮指向不存在的端点——用户点击必失败

**证据**：
- `MessageList.tsx:271`：agent 消息 >100 字时渲染 `校验一致性` 按钮 → `onValidate(msg.text)`
- `ChatPanel.tsx:540` `handleValidate` → `fetch('/api/books/${bookId}/validate', POST)`
- 后端 grep `validate`：routes_*.py **无此路由**（仅有 `validate_protocol/validate_thinking/validate_thinking` 参数校验函数）

**结论**：真实可点的 UI 功能，点了必然 404（或 SPA fallback 返回 HTML → JSON 解析失败）。属于 S141 人类可见性审计漏网——按钮存在、后端不存在。

**建议动作**：删除该按钮与 handleValidate，或接到真实能力（如 check_text 工具的 HTTP 化）。

---

## 🟡 P1：文档/数字过期失准（误导后来者）

### P1-1 `BACKEND-ISSUES.md` 整体过期（8/10 快照，未标注已修复状态）

- P0"SQLite 并发锁定"：**已修复**（`core/db.py` S79 收敛 connect：WAL + timeout=30 + check_same_thread=False；`sqlite.py:456` S75 补 commit；`test_sqlite.py:76` 断言 WAL）——但文档仍标注"待修复/建议优先修复"，无任何状态标记
- 引用的 `chatStore.ts:338-348` **已不存在**（前端重构为 ChatPanel + useSSE，无 chatStore）——引用失效
- P1"前端聊天错误处理"同样未标注是否已修

**建议动作**：文档加"已修复（S75/S79）"标注 + 更新失效引用；或归档到 docs/archive。

### P1-2 `docs/uml/` 过期（最后更新 8/11 = S78，S79-S141 变化未同步）

实证两条：
- `sequence_explore.puml` 画 `POST /api/explore/confirm`、`POST /api/explore/select`——**实际不存在**（routes_explore.py 只有 intent/cards/path/dims/archive）
- `activity_tasks.puml` 画 `batch_rewrite`/`batch_review` 后台任务——**S140 已删**（收编为 workflow 模板）

违反 AGENTS.md"地图更新纪律"（S78 固化：改后端必须同步 uml）。后续接手者会看到已死的流程。

### P1-3 `BACKEND-MAP.md` §2.2 内部矛盾：声称"7 种任务"，实际 4 种

- 文档：`_bg_queue → 7 种任务：chapter/refine/skill_drafts/summarize（S140 删 batch）`
- 实际 `tasks.py`：**恰好 4 种**（chapter/refine/skill_drafts/summarize），无第 5-7 种
- 数字"7"是 S140 删除 batch 前的老数字，删了 3 种后没改

### P1-4 `scripts/current_state.py` 硬编码工具数"46"

- `current_state.py:279`：`md.append("### Agent 工具（46 个，全量注入主循环 LLM）")`——**硬编码**
- 表格行 `| Agent 工具 | **{len(tools)}** 个 |` 是动态的，但标题行不是——下次工具数变化，标题与表格就打架
- 且该脚本装配时同样漏传 library（与 P0-1 同源）——它生成的"46 工具"清单里永远没有 reference_lookup，S141 审计正是基于此清单得出"46 工具全量注入"结论

### P1-5 数字口径漂移

- 路由：CURRENT-STATE 声称 143，源码扫描 190 定义 / 140 去重路径（口径差异未说明）
- 工具：CURRENT-STATE 46 = 生产装配 46（缺 reference_lookup）；全量 spec 定义 48（run_code 默认关，47 装配 + reference_lookup 条件缺席）

---

## 🟢 P2：死代码 / 卫生

### P2-1 前端 Autopilot 残留（旧壳对端专属能力，stub 化后未清理）

- `api/tasks.ts`：9 个任务 API + 4 个 autopilot API **全部降级空实现**（`Promise.resolve({ok:true})`）
- `ChatPanel.tsx`：`connectAutopilotBridge`（1186 行大文件里的 ~40 行死代码）+ mount 时 `getAutopilotStatus` 探测（恒 idle，永不走通）+ `filterAutopilotNoise`（过滤永不产生的 autopilot 消息）+ 20 处 DIAG console.log
- `ChatPanel.tsx` 已 1186 行——单文件过大 + 死代码叠加，维护风险

### P2-2 6 个后端端点前端零引用（有测试无 UI）

`/api/graph/context`、`/api/graph/types`、`/api/graph/types/{type_id}`、`/api/mind/agency-suggest`、`/api/mind/reconcile`、`/api/records/{conv_id}`——测试覆盖齐全，但前端无任何调用。部分可能被 agent 工具/注入块间接使用（graph/context 用于注入），其余属"API 完备无 UI 入口"死角，与 S141"人类可见性"审计目标相悖（审计只查了工具→前端映射，没查端点→前端映射）。

### P2-3 未跟踪垃圾 + .gitignore 缺口

- `.review_tmp/`（8/11 的比对脚本 + 183KB app_orig_full.txt）未跟踪未清理
- `.pi/`（remote-pi 扩展目录）未跟踪，.gitignore 只有 `.pi-subagents/` 无 `.pi/`
- 开源 README 已清洗（S120），仓库根却挂临时目录——开源前必须清

### P2-4 实测记录习惯不一致

- S139 声称"真实库冒烟（curl 实战链路）"，日志有证据（19:08 rollback 实战），但 `data/dev/runs/` 无对应记录（最新 runs 记录停在 8/12）——同一项目内"实测落盘"习惯不一致，后续追溯困难

---

## 附：验证过的健康项（非问题，供参考）

- ✅ 依赖方向：core 零依赖（dependencies=[]），领域包仅依赖 core，play 依赖 explore（复用），app 为组合根——单向无环
- ✅ 工具装配：47 工具真实装配验证通过（含 workflow/play/panel_review 等增强工具）
- ✅ 测试质量：fake model 走**完整 HTTP 链路**（非 mock 壳）；回滚测试含防循环回滚断言；规模化测试用版本条数检测重复处理（精确）
- ✅ S141 三项交付（sandbox API + AI文件 tab、搜索对称、delegate 教学）均真实存在且配套测试
- ✅ BACKEND-MAP 主结构（路由表/工具表）已同步 S140/S141（仅 §2.2 数字漏改）

---

## 修复优先级建议（供主人定夺，非本次执行）

1. **P0-1**（reference_lookup）：一行装配 + 一条集成测试——低成本高价值，建议优先
2. **P0-2**（校验一致性按钮）：删按钮或接 check_text——用户可感知的失败，建议次优先
3. **P1 文档批**（uml/BACKEND-MAP/BACKEND-ISSUES/current_state 硬编码）：一次性文档同步
4. **P2**（Autopilot 死代码/垃圾清理）：随下次前端重构顺手清

> 第二部分（抽象/哲学层面评审）待第一部分确认后另行产出。
