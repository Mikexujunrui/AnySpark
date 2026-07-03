# Changelog

本文档记录项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [2.0.2] - 2026-07-02

### 修复

- **导入小说功能崩溃**：修复后端 `JsonStore` 缺少 `add_doc`/`get_doc`/`save_docs` 方法导致的 `AttributeError`，上传文件时不再报错
- **导入进度显示误导**：将"上传中..."拆分为"上传中..."和"正在检测章节结构..."两个阶段，用户不再误以为上传本身卡顿

### 优化

- **D3 力模拟图谱性能优化**：移除三处图谱组件（FullGraphView、RelationGraph、WorldMap）中阻塞主线程的同步 `sim.tick(N)` 调用，改为 D3 默认异步自然收敛
- **移除 SVG glow 滤镜**：删除 FullGraphView 中 12 种节点类型的 `feGaussianBlur` 发光滤镜及每节点的光晕圆，大幅降低大规模图谱的渲染开销
- **斥力固定化**：三处图谱的 `forceManyBody().strength()` 从随节点数线性增长改为固定值 `-400`，避免节点越多越卡
- **力模拟收敛加速**：`velocityDecay` 统一调整为 0.4，移除冗余的 `alpha(1).alphaDecay()` 显式设置，使用 D3 默认冷却速度

## [2.0.0] - 2026-07-02

### 新增

- **叙事逻辑引擎**：`core/narrative_logic/` 子包，含约束检查器（`constraint_checker`）、置信度评分器（`confidence_scorer`）、约束持久化（`constraint_store`）、影响传播器（`impact_propagator`），支持写作时自动检测叙事约束违规
- **交互式故事系统**：`core/interactive_agent.py` + `core/interactive_store.py`，图谱驱动的分支叙事引擎，支持读者选择驱动剧情走向
- **叙事事件追踪**：`core/narrative_events.py`，结构化记录章节中的叙事事件
- **本体生成器**：`core/ontology_generator.py`，自动从知识图谱生成世界观本体
- **图搜索增强**：`core/graph_search.py`，高级图搜索与路径分析
- **版本更新检测**：`core/update_checker.py`，通过 GitHub Releases API 检查新版本
- **事件存储**：`core/event_store.py`，事件持久化与查询
- **会话状态管理**：`core/session_state.py`，会话级状态追踪
- **设置管理**：`core/settings.py`，用户设置持久化
- **线程池管理**：`core/thread_pools.py`，统一的线程池配置
- **工作流 Agent**：`core/workflow_agent.py`，工作流驱动的 Agent 执行
- **写作核心**：`core/writer.py`，写作引擎核心逻辑
- **Agent 配置与上下文**：`core/agent_config.py` + `core/agent_context.py` + `core/app_context.py`
- **前端大量新组件**：CharacterArcTimeline（角色弧线时间线）、ForeshadowBoard（伏笔看板）、FullGraphView（全图视图）、GraphInsights（图谱洞察）、InteractivePanel（交互面板）、MaterialsPanel（素材面板）、ReferenceBooksPanel（参考书面板）、WorldbuildingMetrics（世界观指标）、CommandPalette（命令面板）、ShortcutsModal（快捷键）、ExportMenu（导出菜单）、ImportDialog（导入对话框）、StylesPanel（文风面板）、WorkflowPoolPanel（工作流池）、AutopilotModal（自动写作弹窗）、TaskProgressPanel（任务进度）、SupervisorBadge（监督指示器）、BookTransformPanel（全书变换）
- **CI/CD 基础设施**：`.github/workflows/ci.yml`（ruff + mypy + pytest + tsc + eslint + build）、`.github/workflows/docker-publish.yml`
- **预提交钩子**：`.pre-commit-config.yaml`（ruff + ruff-format + mypy + eslint）
- **启动脚本**：`start.bat` / `start.ps1` / `start.sh`（多平台一键启动）
- **聊天子组件**：AutopilotConsole、ContextBar、MessageInput、MessageList、PatchNotification、PlotCardSelector、ProgressIndicator、QuestionCard、RunLedger、SlashMenu、TaskListPanel、WorkflowProgress、WritingPreview
- **编辑器增强**：MarkdownEditor（TipTap 富文本）、WordCountGoal（字数目标组件）
- **新路由模块**：`routes/narrative_logic.py`、`routes/materials.py`、`routes/scheduler.py`、`routes/update.py`、`routes/volumes.py`
- **新工具实现**：`tools/impl/narrative_logic.py`、`tools/impl/plot.py`、`tools/impl/imports.py`
- **数据层重构**：`data/stores/` 子包，BookStore / ChapterStore / MetaStore / SessionStore / WorldbuildingStore 模块化存储

### 变更

- **前端 100% TypeScript**：47 个 `.jsx` + 2 个 `.js` 全部迁移为 `.tsx`/`.ts`
- **Emoji 图标统一治理**：UI 中所有 emoji 替换为统一 SVG Icon 组件
- **原生码字体验增强**：自动保存（30s 间隔）、专注模式（Ctrl+Shift+F）、打字机模式、字数目标进度条
- **键盘章节导航**：Ctrl+Alt+↑/↓ 快速切换章节
- **前端组件数**：从 40+ 增至 68 个
- **测试套件**：从 20+ 测试文件增至 34 个，451 个测试用例，3 个跳过
- **核心模块**：从 40+ 增至 61 个（含 `autopilot/` 和 `narrative_logic/` 子包）
- **API 路由**：从 22 个增至 22+ 个路由模块
- **工具实现**：`tools/impl/` 从 10 个增至 13 个文件

### 修复

- **导入小说功能失效**：修复上传缺少 `session_id` 导致 400 错误、`detect_chapters` Content-Type 不匹配
- **全书变换工具 `ModuleNotFoundError`**：修复 6 处裸导入为 `from tools.chapter_tools import`
- **流式工具异常导致 Agent 卡死**：`_execute_tool_streaming` 加 try/except，异常转为 error result
- **Agent 循环终止机制大厂对齐**：轮次/Token 双重预算 + 确定性终态出口 + finish_reason 前端差异化展示
- **TypeScript 属性名错误**：InsightsData 接口字段名修正
- **Ruff C401**：set 生成器改写为 set comprehension

### 验证

- `pytest`：451 passed, 3 skipped
- `ruff check src/ tests/`：0 errors
- `tsc --noEmit`：0 errors
- `eslint --max-warnings 90`：0 errors, 90 warnings
- `npm run build`：构建成功
- 63 个核心模块导入健康度审计通过

---

## [1.2.1] - 2026-06-29

### 修复

- **导入小说功能失效**：修复上传缺少 `session_id` 导致 400 错误、`detect_chapters` 的 Content-Type 不匹配导致 422 错误、上传响应字段 `docId` → `data.id` 读取错误，三处问题导致导入小说完全无法使用
- **全书变换工具 `ModuleNotFoundError`**：修复 `executor.py` 中 6 处 `from chapter_tools import` 裸导入为 `from tools.chapter_tools import`，该错误导致 `summarize_book`（生成全书摘要）、`apply_directive_globally`、`find_replace_book`、`transform_chapters_batch`、`restyle_book` 五个工具全部失效

### 验证

- `pytest`：451 passed, 3 skipped
- 63 个核心模块导入健康度审计通过
- `tsc --noEmit`：0 errors

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
