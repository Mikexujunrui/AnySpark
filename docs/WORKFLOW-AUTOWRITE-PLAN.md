# 全自动续写工作流规划（工作流自足 + 参考书分级联动）

> 状态：**规划中，未实现**。主人确认方向后按阶段实施。
> 关联：参考书分级（已实现，f758ef8）+ 工作流引擎（S59，已实现）。

## 0. 背景与已确认的架构判断

**主人拍板的三个原则**（对话确认）：

1. **工作流 = 主循环 + 用户共同打磨、可跨项目迁移的模板**。工作流是"打法"（§12.22：
   同一套改书标准换书复用），不是绑定某个用户/某本书的一次性程序。
2. **工作流不需要规划自身的智能，不需要心智**。可迁移性论证：工作流读心智 =
   绑定"这个用户"，换用户/换项目就失效。心智（collab/style/habit）的唯一消费方是
   主循环（MindPlanner 现有注入点），工作流不重复消费。
3. **搭好最好全自动**（不一定全流程，可以只是一个小任务工作流）；最多全流程
   加"必要时候问用户的出口"（approval 节点，已有）。

**由此推出的分工模型**：

| 角色 | 职责 | 智能 | 了解用户 |
|---|---|---|---|
| 主循环（agent） | 读心智 → 定策略 → 打磨/触发工作流 | ✅ 智能端 | ✅ 唯一消费心智处 |
| 工作流 | 执行骨架：声明输入 → 跑节点 → 产出 | ❌ 不自我规划 | ❌ 只认输入/数据 |
| 用户 | 打磨流程定义（generate → 确认）、approval 出口决策 | — | — |

**关键认知**：工作流的 **agent 节点就是一次模型调用**（内嵌迷你主循环）——
执行中"需要动脑"的地方由 agent 节点承担，不需要反向调用主循环。
全自动的三个支撑引擎已全有：后台线程跑完整个流程（run_task）、任意节点组合
（小任务工作流）、approval 节点（人控出口）+ gate 模型判断（决定何时该问人）。

## 1. 参考借鉴（桌面 ai ide 各项目扫描结论）

**已扫描**：dify-workflow（CLI-Anything 内）、opencode（agent 编排）、claude-code（agent 包）、hermes-agent（自动化/委托）。

**与 V4 同构、无需参考的**：
- **plan/act 分离**（opencode plan 模式禁编辑工具）≈ V4 S56 主循环规划→干净写作调用，已实现。
- **agent 节点角色化**（opencode explore/general 等 subagent 专用化）≈ V4 agent 节点不同
  system_prompt 实现不同角色，已支持。
- **节点能力声明**（opencode 每个 agent 自带 permission 子集）：V4 的 script 节点本来
  就靠 params.function 指定单个函数 = 节点声明能力，理念已天然满足，无需再加权限层。
- **subagent 并行**（hermes/opencode 委托并行）：V4 工作流是串行编排，并行是另一问题域，不做。

**值得补进规划的（2 条）**：
1. **变量插值 + 人控出口 + 节点目录**（Dify/opencode 共通）：V4 已有 {{var}} + approval + generator 目录，已对齐。
2. **触发方式**（hermes cron 无人值守思想）：V4 工作流现只能手动/agent 工具触发；
   "自动续写"若需无人值守可加**调度触发**（定时/事件），但不是节点形态，属于外围机制，
   暂列入远期（YAGNI，先手动+agent 触发）。

**借鉴结论**：五节点（agent/script/approval/gate/loop）在编排范式上已与主流对齐，
节点形态不改；缺的仍是写作领域知识输入函数（§2）与运行时定制通道（§3）。

## 2. 核心缺口与改动：script 白名单加 3 个只读知识函数

工作流要"自足全自动"，需要能读到"这本书的数据"（绑定 book_id 即得，不算了解用户）：

| 函数 | 读取 | 解决什么 | 实现 |
|---|---|---|---|
| `read_graph` | 本项目图谱实体/关系 | 人物状态/伏笔 → 跨章一致 | `graph.list_entities(book_id, q=?)` + `list_relations` |
| `read_settings` | 本项目设定档 | 正典设定 → 防 OOC/冲突 | `settings.list(book_id)` |
| `query_reference` | 参考书（分级） | 原作事实/文风 | **复用已实现的 reference_lookup 分级检索**（高级项目=图谱+设定+原文；低级书库=原文） |

设计要点：
- 全部**纯只读、book_id 隔离**——复用 `test_knowledge_retrieval_is_read_only` 的
  快照验证模式（检索前后数据不变）。
- 输出形态：**人类可读文本块**（对齐 read_chapter 的产出），供 `{{var}}` 注入 agent
  节点——保持 agent 节点干净调用（S56），不改变引擎。
- **明确不做**：`read_manual`（心智不进工作流）；agent 节点开工具（保持无工具）。

## 3. 可选改动：运行时参数注入（WorkflowRunIn.params）

现状：`WorkflowRunIn` 只有 `book_id`；`{{var}}` 只能引用上游节点输出。
主循环想按需定制一次运行（如传 style_guide / 本章目标）没有通道。

改动（小）：
- `WorkflowRunIn` 加 `params: dict[str, str]`（可选，缺省空）。
- `create_task` 存初始变量表；引擎 `RunContext` 用 params 初始化 `results`；
  `{{var}}` 插值自然引用。
- 用途：主循环驱动的按需运行（一次定制）；全自动工作流可不依赖（用 script 函数自足）。

## 4. 目标形态：自动续写工作流定义（示例 DSL）

```
name: 自动续写
description: 绑定项目自足运行——读知识 → 写下一章 → 审读 → 质量门 → 循环/出口

nodes:
  n1 script   read_settings        → output_key: settings_block
  n2 script   read_graph           → output_key: graph_block
  n3 script   query_reference      → output_key: ref_block
  n4 script   read_chapter(尾章)    → output_key: prev_chapter
  n5 agent    写下一章
              instruction: "根据{{settings_block}}/{{graph_block}}/{{ref_block}}
                            与上一章{{prev_chapter}}，续写下一章。"
  n6 script   write_chapter(落盘)  → 自动触发图谱抽取
  n7 script   review_chapter       → output_key: review
  n8 gate     质量判断: {{review}}硬伤数 < 阈值 → n9 | 否则 → n10
  n9 loop     继续条件: 未达目标章节数 → 回 n1（下一章）
  n10 approval 必要时间用户：质量存疑/新角色/剧情分叉 → 用户决定重写/放行/停

edges: n1→n2→n3→n4→n5→n6→n7→n8 →(好) n9 →(loop回n1) | n8 →(存疑) n10
```

- 全自动：绑定 book_id 后一路跑；gate 判断"必要时候"才到 approval。
- 可迁移：定义不绑定用户/书，任何项目复用。
- 小任务工作流同理：任意子集（如"只审读本章并给建议"= n4→n7 两个节点）。

## 5. 测试计划

1. script 函数单测：read_settings / read_graph / query_reference——命中、未命中、
   只读性（快照一致）、book_id 隔离（A 项目检索不影响 B 项目）。
2. workflow 端到端（假模型注入）：跑一个"读→写→审→判"小流程，验证 `{{var}}`
   注入链路与 gate 分支。
3. params 注入测试：run 时传 params → agent 节点 system_prompt 引用生效。

## 6. 风险与边界

- **agent 节点上下文长度**：知识块（设定+图谱+参考）可能拼很大 → 限量：
  read_graph 取 Top N 实体（如 30）+ 关系精简；query_reference 已有 max_per_book 限制。
- **全自动写文的信任边界**：默认"小步全自动 + 出口前置"（每 2-3 章或质量存疑强制
  approval），用户信任度提高再放开迭代数。信任模型是方向，出口必须存在。
- **兼容性**：workflow 定义 schema 不变（只加 script 函数名 + 可选 params 字段）；
  旧模板与任务照常运行。
- **不做**：工作流反向调用主循环；工作流读心智；agent 节点开工具。

## 7. 实施阶段（确认后按序执行）

| 阶段 | 内容 | 产出 |
|---|---|---|
| 1 | script 白名单加 read_settings / read_graph / query_reference（复用分级检索） | 3 函数 + 单测 |
| 2 | WorkflowRunIn.params 运行时参数注入 | 参数通道 + 测试 |
| 3 | 示例自动续写 workflow 定义（workflow_generate 生成或手写）+ 端到端验证 | 可用模板 + 验证记录 |
| 4 | （可选）前端工作流画布/参考书面板高级标识 | 后端先行，UI 后置 |

> 哲学校验：本规划全部落在"机制硬编码（script 白名单/参数通道）、内容自然语言
> （知识块/流程定义）、相信模型（agent 内嵌智能 + gate 判断）、YAGNI（不做
> read_manual/不反转调用）"——与 V4 既有哲学一致，无新增护栏。
