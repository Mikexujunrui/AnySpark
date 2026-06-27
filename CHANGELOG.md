# Changelog

本文档记录项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [3.0.0] - 2026-06-22

### 新增
- 持久任务引擎（TaskQueue + TaskRunner + Supervisor），Agent 具备持久运行能力
- Autopilot 自主写作引擎：8 种意图分类 + 多类型步骤模板 + 动态 Replan
- 全书变换工具集（apply_directive_globally, find_replace_book, transform_chapters_batch, restyle_book, summarize_book）
- 质量门控（quality_gate），复用评审团轻量评审
- TaskProgressPanel、AutopilotModal、SupervisorBadge、BookTransformPanel 前端组件

### 修复
- scheduler→runner 断链修复
- quality_gate 孤立修复
- token 预算追踪死代码修复
- supervisor.record_activity 未接线修复

## [2.9.0] - 2026-06-20

### 新增
- 结构化 Part 类型系统（TextPart/ToolCallPart/ToolResultPart/ChapterDiffPart/ReasoningPart）
- reasoning 内容捕获与持久化（不注入回 LLM 上下文）
- 完整历史持久化（Turn 序列化/重建，向后兼容旧格式）
- 章节变更浮现卡片（ChapterDiffPart）

## [2.7.0] - 2026-06-20

### 重构
- Agent Loop 结构化重构：640 行 God Function 拆分为阶段处理器
- LoopState dataclass 收编 10 个循环状态变量
- TOOL_META 单一事实源替代 4 处硬编码工具名集合
- 幻觉脉冲改事件驱动，漂移信号分离，sitrep 异步化

## [2.6.0] - 2026-06-17

### 新增
- 文风/技能系统双源分离（系统默认 + 用户自定义）
- 文风 CRUD REST API
- manage_styles 工具

### 修复
- agent_loop 活跃风格不自动注入系统提示的遗留 bug

## [2.5.0] - 2026-06-16

### 新增
- Book 级可重入写锁（threading.RLock）
- 并行写入安全保护，解决 JSON 文件丢失写入问题

## [2.4.0] - 2026-06-16

### 新增
- 联网搜索架构（MCP JSON-RPC 2.0，Exa/Parallel 双后端）
- web_search、web_fetch 工具
- research 子 Agent 类型

## [2.3.0] - 2026-06-16

### 新增
- 剧情卡片交互（suggest_plot_directions 工具）
- 前端 PlotCardSelector 卡片组件
- 阻塞式用户选择机制

## [2.2.0] - 2026-06-15

### 新增
- 评审团系统：8 位预设评审员，并发/串行评审
- run_review、manage_reviewers 工具
- 评审面板前端（卡片墙 + 激活管理 + 历史 + 报告）

## [2.1.0] - 2026-06-12

### 新增
- Git 风格章节版本控制（history/revert/diff）
- edit_chapter、chapter_history、revert_chapter、diff_chapters 工具

## [2.0.0] - 2025-06-12

### 重构
- while-true 自主循环架构（替代单向流水线）
- 指数退避重试、两阶段上下文压缩
- Session 并发控制 + Cancel
- Doom Loop 检测
- 子 Agent 派生系统
- 分层动态 system prompt
- 精确 tiktoken token 计算

## [1.0.0] - 2025-01

### 新增
- 核心 MVP：对话界面 + 知识抽取 + 知识约束写作 + Wiki 查看器
- FastAPI + React + SQLite 脚手架
- LLM 网关（Claude API 接入）
