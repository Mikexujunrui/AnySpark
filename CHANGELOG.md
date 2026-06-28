# Changelog

本文档记录项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [1.2.0] - 2026-06-28

### 新增

- **原生码字体验增强**：章节编辑器新增自动保存（30s 间隔，脏状态追踪，页面关闭保护）、专注模式（Ctrl+Shift+F 隐藏侧边栏/标签栏/大纲，仅保留编辑器）、打字机模式（光标自动居中滚动）、字数目标进度条（点击可编辑目标，持久化到 localStorage）
- **键盘章节导航**：Ctrl+Alt+↑/↓ 在章节间快速切换，无需鼠标
- **自动保存 Hook**：`useAutoSave` 独立 Hook，可复用，含定时保存、脏状态指示、beforeunload 保护
- **字数目标组件**：`WordCountGoal` 独立组件，可视化进度条，嵌入编辑器工具栏
- **Icon 组件新增**：`maximize`、`pause`、`skip-forward`、`alert-triangle`、`eye`、`type` 6 个 SVG 图标

### 变更

- **Emoji 图标统一治理**：UI 中所有 emoji（✍️✦⌨✓✕▶⏸🔄🚫🔒🔓🤖🟢🔴💡⚠️✅❌🎉📢📄🔍⏹ℹ️）替换为统一的 SVG Icon 组件，覆盖 ChaptersPanel、ChatPanel、TaskProgressPanel、WritingPreview、SupervisorBadge、ReviewPanel、WorldMap、TimelineView、WorldbuildingPanel、useSSE 共 12 个文件
- MarkdownEditor 新增 `onDirty`、`typewriterMode`、`showWordCount`、`toolbarRight` 4 个可选 prop，向后兼容

### 验证

- `tsc --noEmit`：0 errors
- `npm run build`：构建成功
- `eslint --max-warnings 100`：0 errors, 72 warnings（均为预存）
- `pytest`：421 passed, 3 skipped

## [1.1.2] - 2026-06-28

### 重构

- **前端全量 TypeScript 迁移**：47 个 `.jsx` + 2 个 `.js` 文件迁移为 `.tsx`/`.ts`，实现前端 100% TypeScript 覆盖
- 移除所有 `.jsx`/`.js` 扩展名导入，统一为无扩展名导入风格
- 为关键组件添加类型注解（ErrorBoundary 泛型类组件、EmptyState/ToolbarButton prop 接口等）
- 修复迁移引入的 77 个 `tsc` 类型错误（`unknown` 属性访问、EventTarget 类型断言、缺失 prop 等）
- 修复 5 个 ESLint trivial warning（未使用变量/import、无用赋值）

### 变更

- 移除 `tsconfig.json` 中 `allowJs: true` 和 `checkJs: false`
- `eslint.config.js` 中 JSX 规则块保留但不匹配任何文件（src 已无 JSX）

### 验证

- `tsc --noEmit`：0 errors
- `npm run build`：构建成功
- `eslint --max-warnings 90`：0 errors, 72 warnings
- `ruff check src/ tests/`：干净
- `pytest`：421 passed, 3 skipped

## [1.1.1] - 2026-06-28

### 修复

- **流式工具异常导致 Agent 卡死（abnormal_exit 根因）**：`_execute_tool_streaming` 的 `_run()` 缺少 try/except，当流式工具（如 extract_all_chapters）执行中抛异常时，`queue.put(None)` 不执行 → 消费者 `await queue.get()` 死锁 → Agent 循环卡住 → 用户看到几个 progress 后「停止啥都没有」→ 最终 abnormal_exit。已加 try/except，异常转为 error result 返回，Agent 能继续或报告，不再卡死。
- 该 bug 在 metrics.jsonl 中表现为 `finish_reason: abnormal_exit` + `rounds: 1` + `tool_calls: 0`，典型场景为「提取知识库/世界观」时 extract_all_chapters 工具转几圈后静默停止。

### 验证
- pytest test_agent_loop + test_executor_utils: 44 passed
- ruff check 干净

## [1.1.0] - 2026-06-28

### Agent 循环终止机制大厂对齐演进

在 v1.1.0 信任 LLM 哲学基础上，引入大厂标配的双重成本控制与确定性终态，彻底消灭「莫名中止 / 完成后无报告」两类用户痛点。

#### 新增
- **轮次硬上限**：per_type 配置，write=100 / 其他=30（大厂约 50，写作场景放宽），替代 v1.1.0 的 max_rounds=0 无限循环
- **Token 累计预算**：token_budget_ratio=0.8 × 模型 context 上限，每轮用 count_message_tokens 估算 input+output 累加，超额即停
- **确定性终态出口**：llm_error / llm_empty / token_budget_reached / round_limit_reached / abnormal_exit 每条终止路径均 yield 带原因的 done 事件，不再依赖外层兜底链
- **finish_reason 前端差异化展示**：useSSE.ts 据 metrics.finish_reason 判断异常终态，加 ⚠️ 标记并强制显示，绕过 trivial 过滤

#### 变更
- done message 禁用「完成」占位符（会被前端 trivial 过滤吞掉导致无报告），final_text 为空时用 metrics 合成总结
- 外层安全网 message 承接 last_error_msg，不再输出空洞占位符
- README「七层幻觉检测」过时描述更新为「幻觉安全网」（fake_tool/fake_write 两层 warning-only）

#### 验证
- pytest 全量 421 passed / 3 skipped
- ruff check + format（改动文件）干净
- 前端 tsc --noEmit + eslint 0 errors

## [1.0.0] - 2026-06-27

### 首次正式发布

AnySpark（火花）AI 小说写作辅助 Agent 首个正式发布版本。版本号从 1.0.0 起始，作为项目的首个公开发布里程碑。

#### 新增
- 版本更新检测功能：设置面板「关于」页签中可开关（默认开启），通过 GitHub Releases 公开 API 检查最新版本，仅检测不自动安装
- 设置面板新增「关于」页签，展示当前版本号、更新开关与检查入口

#### 包含的核心能力
- 三级大纲体系与 AI 自动分卷
- 剧情链节点级精准编辑（decompose → annotate → rewrite）
- 高保真同人改写与段落级对齐
- Autopilot 全链路自动化写作引擎
- 七层幻觉检测与防御体系
- 文风 / 技能 / 评审团多维度系统
- 持久任务引擎（TaskQueue + TaskRunner + Supervisor）

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
