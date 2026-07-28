# Changelog

本文档记录项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [3.0.0] - 2026-07-24

### 重大变更

- **SQLite 替代 Neo4j**：`sqlite_store.py` 完全替代 `graph_store.py`，知识图谱存储从 Neo4j 迁移到嵌入式 SQLite，零外部依赖，无需 Docker
- **移除 Docker 依赖**：删除 `docker-compose.yml`、`Dockerfile.backend`、`frontend/Dockerfile`、`frontend/nginx.conf`、`.dockerignore`、`install.sh`、`install.ps1`
- **移除 Neo4j 配置**：删除 `Neo4jConfig` 类、`Neo4jError` 异常类、`.env.example` 中 Neo4j 环境变量

### 优化

- 启动脚本简化：`start.ps1` / `start.sh` 移除 Neo4j Docker 启动步骤，从 [1/3][2/3][3/3] 简化为 [1/2][2/2]
- CI 简化：移除 Neo4j 服务容器和相关环境变量，测试不再依赖 Docker 服务
- `.gitignore` 新增 `dist/`、`build/`、`.mypy_cache/`、`dist/NovelAgent.zip`
- 新增 `.gitattributes` 统一行尾规范

### 修复

- 无

### 验证

- `ruff check src/ tests/`：0 errors
- `pytest`：全部通过

---

## [2.7.0] - 2026-07-19

### 新增

- **Prompt 模板化**：`prompts/` 模块 — 5 个文件（`__init__.py` + 4 个模板），`extractor.py` 中 ~90 行硬编码 prompt 替换为 `load_prompt()` 调用，`compaction.py` 的 `COMPACTION_SYSTEM` 同步迁移
- **三级优先级内容保留策略**：Entity 新增 `priority` 字段（Tier 1/2/3），`ContextManager` 新增 `_calculate_entity_priority()` 方法，`build_writing_context` 按优先级排序注入实体
- **证据锚点解析引擎**：`anchor_resolver.py`（481 行），支持 `full` 和 `head_tail` 两种锚点模式；评分策略：0.35 × char n-gram + 0.35 × LCS + 0.2 × Levenshtein + 0.1 × 长度惩罚；30 个测试用例全部通过
- **知识库归档格式**：`archive.py`（516 行），ZIP + SQLite + JSON 格式；后端 3 个 API：`format=spark` 导出、`upload-spark` 上传、`import-spark` 导入；前端 ExportMenu 新增 `.spark 归档` 按钮
- **EPUB 导出**：`export_epub()` 函数，支持竖排/横排切换，自动生成 NCX + NAV 目录，章节自动分页；前端 ExportMenu 新增 `EPUB 电子书` 按钮

### 修复

- 无

### 优化

- 无

### 验证

- `ruff check src/ tests/`：0 errors
- `pytest`：707 passed（新增 30 个锚点解析测试）

---

## [2.6.0] - 2026-07-16

### 新增

- **AI味扫描引擎**：`core/ai_flavor_scanner.py` — 7项纯规则检测（过渡词密度/模板句式/模糊词/面部微表情/段落同构/句长均匀度/对话标签多样性），零token消耗，写后自动评分，集成到 `finalize_chapter` 和 `run_quality_gate`
- **AI味嗅觉审查员**：`reviewers/ai_flavor_sniffer.yaml` — 评审团新增LLM审查员，检测机械表达/情感表演性/肢体逻辑/对话自然度/描写重复，默认关闭按需启用
- **AI味扫描API**：`GET /books/{book_id}/ai-flavor-scan` — 对指定章节或最新章节进行7项纯规则检测
- **AI味反馈闭环**：`knowledge_scope.py` 新增 `prev_chapter_issues`，`context_manager.py` 自动注入上一章发现的问题，`headless_loop.py` 在 step_result 中持久化AI味评分

### 修复

- **知识检索零匹配**：`_prepare_writing` 新增子串匹配fallback，FTS无结果时遍历实体名/别名匹配大纲摘要，并有明确提示
- **Neo4j宕机防御**：`batch_add_entities`/`batch_add_relations`/`batch_add_foreshadows` 增加 `_driver is None` 检查，优雅降级不再崩溃
- **启动脚本自动创建Neo4j**：`start.bat`/`start.ps1` 容器不存在时自动 `docker run` 创建，不再静默失败；`start.bat` 删除重复内容
- **评审团前端显示**：新增"续写专项"分类区，4位 `continuation` 类别评审员不再不可见

### 优化

- **章节拆分正则增强**：从2种格式扩展到10种（第X章/回/节/幕/话、序章/楔子/番外、纯数字/罗马数字、Chapter/Volume），LLM fallback改为头尾中三段采样
- **批量导入优化**：新增 `batch_add_chapters`，导入从 O(n²) 降到 O(n)，1281章从数十秒降到秒级

### 验证

- `ruff check src/ tests/`：0 errors
- `pytest`：27 passed（新增21个AI味扫描测试）


---

## [2.5.1] - 2026-07-10

### 修复

- **[object Object] 渲染修复**：知识库/角色详情/角色卡片/图谱节点等面板中，AI 生成的嵌套对象字段（如外貌、性格、能力、背景）不再显示为 `[object Object]`，改为可读的键值对格式展示
- **编辑表单嵌套对象支持**：EntityDataForm 支持 JSON 格式嵌套对象的编辑与保存
- **推演 Store 类型修复**：`simulation-store.ts` 新增 `choicePrompt` / `currentBranchId` 字段；`initSimRun` 参数改为可选默认值；修复 `SimulationLayout` 中 `runs[simId]` 访问改为扁平状态
- **SnapshotPanel / FullGraphView / ReviewPanel**：同类 `[object Object]` 渲染问题一并修复

### 新增

- **项目记忆系统**：新增 `core/memory/` 模块（MemoryManager、MemoryInjector、MemoryStore 等），支持项目级记忆与用户偏好的自动提取、注入、查询和删除
- **MemoryPanel 前端组件**：知识库面板新增记忆管理界面
- **记忆路由**：`routes/memory.py` 提供完整的 REST API

### CI 与质量

- **Ruff lint 零错误**：修复 24 项问题（F401 未使用导入 / F841 未使用变量 / I001 导入排序 / UP042 StrEnum 迁移）
- **TypeScript 零错误**：修复 13 个类型错误（simulation-store 接口与 SimulationLayout 对齐）
- **pytest 全通过**：656 passed, 3 skipped
- **ESLint**：0 errors, 147 warnings（< 150 上限）
- **前端构建**：Vite 构建成功

---

## [2.5.0] - 2026-07-08

### CI 与质量

- **Ruff lint 零错误修复**：修复 20+ 项 F401（未使用的 import）/ F841（未使用的变量）/ I001（import 排序）问题
- **TypeScript 类型检查**：`tsc --noEmit` 零错误通过
- **ESLint 检查**：0 errors, 145 warnings（< 150 上限）
- **前端构建**：Vite 构建成功
- **Python 测试**：653 passed, 3 skipped

### 修复

- **移除未使用的 import 和变量**：`annotation_engine.py`、`continuation_pipeline.py`、`graph_store.py`、`voice_fingerprint.py`、`reference_analysis.py` 及测试文件中冗余代码清理

---

## [2.4.0] - 2026-07-07

### 新增

- **深度文风分析引擎**：`core/reference_analyzer.py` 新增 4 个分析维度——句式韵律（`SentenceRhythm`：对仗/骈文密度/文言标记/长短交替/倒装）、修辞密度（`RhetoricDensity`）、谶语特征（`ProphecySignature`）、叙事视角（`NarrativePOVSignature`），纯 Python 确定性分析，结果自动注入写作 Prompt
- **情感弧线分析**：`core/emotion_analyzer.py` — 章节级情感曲线提取，注入写作约束
- **角色语言指纹增强**：`core/voice_fingerprint.py` 新增 8 项古典小说续写专用指标——独有标记词、独有词汇、称呼模式、反问句率、引经据典频率、命令/请求比、反讽标记、句长标准差
- **伏笔网络分析**：`core/foreshadow_network.py` — 伏笔关联图谱与生命周期分析
- **谶语解析器**：`core/prophecy_parser.py` — 古典小说谶语/预叙特征提取
- **续写流水线**：`core/continuation_pipeline.py` — 结构化续写执行流程
- **注释引擎**：`core/annotation_engine.py` — 章节内容标注
- **图谱子包重构**：`core/graph/`（`entity_store.py` / `relation_store.py` / `analysis_store.py`）— 模块化图谱存储
- **Pydantic 工具验证**：`core/pydantic_validation.py` — 工具参数从手工类型校验迁移至 Pydantic 动态模型验证
- **图谱洞察算法**：`graph_store.py` 新增关键路径分析（DAG 拓扑排序 + 最长路径）和链接预测（Adamic-Adar / Jaccard 相似度）
- **伏笔手动回收工具**：`resolve_foreshadow` 工具，支持手动标记伏笔为已回收
- **世界观条目更新工具**：`update_worldbuilding_entry` 工具
- **深度文风分析工具**：`analyze_deep_style`（4 种分析类型）和 `analyze_emotional_curve` 两个 Agent 工具
- **前端 API 层补全**：`api.ts` 新增 12 个 API 方法（章节 CRUD / 分卷 / 导出 / 升降级 / 大纲 / 版本历史）
- **章节历史面板**：`ChapterHistoryPanel.tsx` — 从 ChaptersPanel 抽离的独立组件

### 变更

- **工具执行器重构**：`tools/executor.py` 重构为 dispatch table 架构（97 个直接工具 + 自动注册机制），支持「只写 handler 即可注册工具」的极简工作流
- **Tool 元数据增强**：`tools.py` 新增 `doc` 扩展文档字段，`to_doc()` 自动生成工具使用说明，`validate_tool_input` 委托 Pydantic 引擎
- **工具元信息更新**：`tool_meta.py` 新增 `batch_edit_chapters`（流式+危险）、`resolve_foreshadow`、`update_worldbuilding_entry`、`analyze_deep_style`、`analyze_emotional_curve` 元数据
- **移除冗余工具**：删除 `add_timeline_event` 工具（功能未实现），system prompt 同步清理
- **章节识别增强**：`documents.py` + `imports.py` 正则从 `第X章` 扩展为 `第X章|第X回`，支持古典章回体小说；detect_chapters 不再截断返回 20 章上限
- **知识范围扩展**：`knowledge_scope.py` 新增 5 个深度文风约束字段 + 2 个功能开关，`to_dict` / `from_dict` / `to_summary` 同步支持
- **上下文注入增强**：`context_manager.py` 注入句式韵律、修辞密度、谶语特征、叙事视角、情感弧线 5 项深度约束到写作 Prompt
- **文件上传限制提升**：`MAX_FILE_SIZE` 从 50MB 提升至 200MB
- **graph_store.py 精简**：从 3981 行精简至 3291 行（-690 行），新增图分析算法

### 修复

- **前端 ChaptersPanel 直接 fetch 调用**：迁移至统一 `api.*` 方法调用（章节删除/降级/大纲加载/版本历史/回退/版本删除共 6 处）

### 验证

- `pyproject.toml` 版本号更新至 2.4.0

---

## [2.3.0] - 2026-07-03

### 新增

- **参考书分析引擎**：`core/reference_analyzer.py` — 纯 Python 确定性分析引擎（无 LLM 调用），对导入参考书进行结构分析（字数/对话比/段落/句子/节奏曲线）和文风量化（句长分布/词汇丰富度/标点模式/成语密度/段落统计），结果自动注入写作 Prompt
- **分析 REST API**：`routes/analysis_routes.py` — 5 个端点（触发/获取结构分析、触发/获取文风量化、列表缓存）
- **分析工具**：`tools/impl/reference_analysis.py` — `analyze_structure` / `quantify_style` 两个工具
- **前端分析 UI**：ReferenceBooksPanel 重构 — 可展开分析区、结构报告视图（指标+柱状图+节奏曲线）、文风指纹视图（TTR/成语密度/句长分布图+标点标签）、缓存状态徽章

### 优化

- **主动式陈旧工具结果裁剪**：每轮 Stage 0 运行 `prune_stale_tool_results()`，保护尾 60K tokens，裁剪消息截断至 800 tokens，减少未触发 compaction 前的上下文膨胀
- **Compaction 激进调优**：threshold 0.95→0.70，protected_tail 80K→60K，tail_turns 5→4，max_tool_output 50K→30K；token_budget_ratio 0.8→0.0（1M 窗口模型不再需要累计 token 上限）
- **LLM 客户端连接可靠性**：自定义 httpx 客户端绕过系统代理（`trust_env=False`），避免 VPN/Clash 代理 TLS 拦截；同步 chat 新增重试（5 次指数退避）；流式 chat 在首个内容前可重试；重试延迟 0.5s→1.0s / 8.0s→15.0s
- **动态图谱 Schema**：`graph_store.py` 支持自定义关系类型（不在 `RelationType` 枚举中的类型优雅降级），`suggest_relationships` 改用动态 schema 查询替代硬编码排除列表
- **Writer 系统 Prompt 缓存优化**：`_write_by_nodes` 构建单一 `stable_system` 传递给所有节点，利用 DeepSeek prefix caching 节省后续节点输入 token
- **参考文风自动注入写作**：`writer.py` 在写作时自动注入缓存的结构分析和文风指纹数据
- **System Prompt 章节列表优化**：仅显示最近 5 章详情，早期章节以计数摘要替代，保持上下文稳定利于 prefix caching
- **Planner 指令优化**：不再要求读取前文全文，改为基于前情提要和纲要保持连贯

### 修复

- **Context Usage API 磁悬浮**：`sessions.py` 中 `get_context_usage` 改用 `turns_from_history` + `count_message_tokens` 精确计算，包含 tool_calls/tool_results/system prompt 开销
- **Provider API Key 清空**：`settings.py` 前端编辑时空字符串不再覆盖已存储的 key
- **图谱关系类型加载**：`graph_store.py` 自定义关系类型不再因 `ValueError` 崩溃

### 测试

- 新增 `tests/test_reference_analyzer.py` — 286 行覆盖文本工具/结构分析/文风量化/缓存
- 新增 `tests/test_optimizations.py` — 131 行覆盖 compaction 配置/裁剪逻辑/planner 指令

## [2.2.0] - 2026-07-03

### 新增

- **叙事节奏曲线**：`core/pacing_analyzer.py` — 五维度章节节奏分析（对话占比/句长方差/场景转换/情感波动/综合节奏分），D3 折线图可视化
- **角色语言指纹**：`core/voice_fingerprint.py` — 从章节对话中提取角色语言风格（高频词/句式/口头禅/情感倾向），注入 Prompt 确保对话一致性，前端 CharacterDetail 可折叠面板
- **伏笔-回收自动匹配**：`core/foreshadow_matcher.py` — TF-IDF 余弦相似度自动匹配伏笔与回收点，悬空伏笔检测，ForeshadowBoard 集成 AI 悬空检测按钮
- **章节间内容查重**：`core/dedup.py` — SimHash + 滑动窗口 Jaccard 相似度检测章节重复内容，StatsDashboard 新增查重 tab
- **增量知识图谱同步**：`core/incremental_sync.py` — 章节写入后自动触发知识 diff，通过事件总线推送 KNOWLEDGE_PROPOSED 事件
- **章节依赖图**：`core/chapter_dependency.py` — 构建章节间内容依赖关系图，BFS 影响传播分析，D3 力导向图可视化
- **创作成本仪表盘**：`core/cost_tracker.py` — 按工具/书籍/时间维度统计 token 消耗与 API 成本，D3 饼图+趋势图
- **语义 Diff**：`core/semantic_diff.py` — LLM 驱动的章节版本语义级对比（角色情绪/场景/情节走向变更），Agent 工具注册
- **灵感碎片管理器**：`core/inspiration_box.py` — 三列看板（收件箱/已提升/已归档），支持关联角色/章节/伏笔，可提升为正式结构
- **大纲逐级展开 Pipeline**：`core/outline_pipeline.py` — 一句话设定→总纲→分卷纲→章节纲→细纲四级自动展开，OutlinePanel 集成入口

### 优化

- **分卷前端优化**：ChaptersPanel 侧边栏按卷分组展示章节，每卷独立彩色头部+缩进列表，未分卷章节单独分组
- **灵感碎片面板挂载**：BookDetail 辅助 Tab 组 + PanelHost 路由注册
- **统计图表 SVG 响应式缩放**：全部 6 个图表（字数趋势/章节分布/Agent 趋势/节奏曲线/成本饼图/成本趋势）统一使用 `viewBox` + `preserveAspectRatio` 方案，彻底解决坐标轴被裁切或溢出面板的问题

### 新增模块

- `core/pacing_analyzer.py` — 叙事节奏分析
- `core/dedup.py` — 章节查重
- `core/cost_tracker.py` — 成本追踪
- `core/semantic_diff.py` — 语义 Diff
- `core/voice_fingerprint.py` — 角色语言指纹
- `core/incremental_sync.py` — 增量知识同步
- `core/inspiration_box.py` — 灵感碎片管理
- `core/foreshadow_matcher.py` — 伏笔自动匹配
- `core/chapter_dependency.py` — 章节依赖图
- `core/outline_pipeline.py` — 大纲逐级展开
- `routes/pacing.py` — 节奏分析 API
- `routes/inspiration.py` — 灵感 API

### 新增前端组件

- `PacingCurve.tsx` — 节奏曲线（D3 多指标折线图）
- `CostDashboard.tsx` — 成本仪表盘（饼图+趋势+Top5）
- `InspirationInbox.tsx` — 灵感看板（三列式）
- `ChapterDependencyGraph.tsx` — 章节依赖图（D3 力导向）
- `CharacterVoicePanel.tsx` — 角色语言指纹面板
- `OutlinePipelinePanel.tsx` — 大纲逐级展开 UI

### 新增测试

- 8 个测试文件，96 个测试用例，覆盖纯函数逻辑（SimHash/Jaccard/TF-IDF/BFS/情感分析/成本估算/灵感 CRUD）

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
