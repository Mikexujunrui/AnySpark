# 实施路线图

> 当前版本: v2.6.0 | Phase 1-4 全部完成 | Phase 5-7 持续迭代

---

## 阶段概览

| 阶段 | 状态 | 时间 | 关键交付 |
|------|------|------|----------|
| Phase 1: 核心MVP | ✅ 完成 | 2025-01 | 对话界面 + 知识抽取 + 写作Agent |
| Phase 2: 知识体系 | ✅ 完成 | 2025-02 | 一致性校验 + 可视化 + 上下文管理 |
| Phase 3: 工作流+可视化 | ✅ 完成 | 2025-03 | 知识图谱 + 4D地图 + 伏笔看板 + 工作流 |
| Phase 4: Neo4j+生产化 | ✅ 完成 | 2025-06 | Neo4j迁移 + Docker + 导出 |
| Phase 5: 全栈成熟化 | ✅ 完成 | 2026-06~07 | 叙事逻辑 + 交互故事 + CI/CD + 68组件 |
| Phase 6: 质量增强 | ✅ 完成 | 2026-07 | 参考书分析 + 文风系统 + 角色语言指纹 |
| Phase 7: AI味扫描 | ✅ 完成 | 2026-07 | AI味扫描引擎 + 批量导入优化 + 多项修复 |

---

## 追加记录

### v15 — 2026-07-16: v2.6.0 AI味扫描 + 批量导入优化
- 变更类型: 新增 + 修复 + 优化
- 涉及模块: ai_flavor_scanner(新), quality_gate, continuation_pipeline, context_manager, knowledge_scope, headless_loop, chapter_store, imports, knowledge, search, graph_store, reviewers, start.bat, start.ps1, ReviewPanel.tsx
- 描述: 新增AI味扫描引擎（7项纯规则检测），集成到finalize_chapter和quality_gate。新增AI味嗅觉审查员（评审团第14位）。修复知识检索零匹配、Neo4j宕机崩溃、启动脚本Neo4j容器缺失、评审团前端分类缺失。优化章节拆分正则（2→10种格式）、批量导入（O(n²)→O(n)）。

### v14 — 2026-07-10: v2.5.1 记忆系统 + [object Object]修复

### v11 — 2026-06-20: 结构化 Part 系统 + 完整历史持久化
- 变更类型: 新增 + 重构
- 涉及模块: parts(新增), llm_client, agent_loop, loop_state, token_counter, routes/chat, frontend/MessageList, tests/test_parts(新增)
- 描述: 引入 Part 类型系统,补齐 reasoning 捕获(静默丢弃修复)、完整历史持久化(刷新可回放执行过程)、章节变更结构化浮现(变更卡片)。reasoning 捕获但不注入回 LLM(文学创作显式输出优先)。新增 13 用例,全部 303 测试通过。

### v9 — 2026-06-20: Agent Loop 结构化重构
- 变更类型: 重构
- 涉及模块: loop_state(新增), agent_loop, tools, agent, config, tests/test_agent_loop(新增)
- 描述: 将 640 行 `_loop_inner` God Function 拆分为阶段处理器，状态收编进 `LoopState`/`LoopMetrics`。工具行为元数据收敛为 `TOOL_META` 单一事实源，消除 4 处硬编码工具名集合。幻觉脉冲改事件驱动，漂移信号分离，sitrep 异步化，prompt 注入统一 role:user。新增 29 用例测试覆盖。
- 影响: 对外 API（`run_agent_loop`/`AgentConfig`/`LoopEvent`）不变；`sub_agent.py`/`chat.py` 无需改动；所有 277 测试通过。

### v8 — 2026-06-16: 剧情卡片交互
- 变更类型: 新增
- 涉及模块: tools, executor, agent_loop, chat.py, ChatPanel.jsx, system_prompt
- 描述: 新增剧情卡片工具——Agent规划剧情时生成多个走向选项以可视化卡片呈现，用户可选择/自定义/拒绝，使用question_manager阻塞等待。前端PlotCardSelector组件渲染富卡片。

### v7 — 2026-06-15: 评审团系统
- 变更类型: 新增
- 涉及模块: review_panel, sub_agent, system_prompt, tools, executor, json_store, routes/reviews, ReviewPanel.jsx, reviewers/default.yaml
- 描述: 新增评审团系统——8位预设评审员（编剧/文学编辑/逻辑审校/爽文读者/情感型读者/硬核党/挑刺王/休闲读者），支持自定义评审员、并发/串行评审模式、汇总报告+个人详细反馈。前端卡片墙管理+评审历史。

### v5 — 2026-06-11: Run Loop + 拆书复写工具集
- 变更类型: 新增
- 涉及模块: Agent 决策引擎、工具注册表、拆书复写工具集
- 描述: Agent 架构从单向流水线升级为 Run Loop（LLM ↔ tool result 循环）。新增 5 个拆书复写工具（decompose_chapter/extract_style/reconstruct_chapter/compare_plot/count_words）。新增 full_novel_reconstruct 和 chapter_rewrite 两个 Skill。

### v13 — 2026-07-02: v2.0.0 全栈成熟化
- 变更类型: 里程碑发布
- 涉及模块: 全栈
- 描述: 项目从 v1.x 系列跨越至 v2.0.0。核心新增叙事逻辑引擎（`narrative_logic/` 子包）、交互式故事系统、本体生成器、图搜索增强。前端 68 组件，34 测试文件 451 用例。CI/CD 全链路（ruff + mypy + pytest + tsc + eslint + build）。数据层模块化重构（stores/ 子包）。详见 CHANGELOG.md 和 ARCHITECTURE.md。

### v12 — 2026-06-24: 草稿/定稿双轨 + 叙事导演 + RunLedger增强
- 变更类型: 新增
- 涉及模块: chapters.py, json_store.py, git_store.py, styles_route.py, loop_state.py, agent_loop.py, ChaptersPanel.tsx, MarkdownEditor.jsx, RunLedger.jsx, types/index.ts
- 描述: 新增草稿/定稿双轨流程（章节status字段，promote/demote API，前后端完整UI）；叙事导演系统API（NarrativeStrategy六维度：pov/pacing/reveal_density/foreshadow_budget/chapter_arc/tone_guidance）；RunLedger增强为展示工具调用分布。同步修正TECH_STACK.md为实际技术栈。

### v4 — 2026-06-11: Agent 架构重构
- 变更类型: 新增
- 涉及模块: Agent 决策引擎、工具注册表、技能系统
- 描述: chat 端点从固定 `/s` `/w` 工作流升级为 Agent 自主分类→规划→执行环路。支持 skills/ 自定义技能文件。上传改为全文处理（不再截断）。

