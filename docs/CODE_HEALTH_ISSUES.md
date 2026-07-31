# 代码健康度问题清单

> 生成日期：2026-07-21 | 版本：v2.7.0 | 状态：持续消化中
>
> 最近更新：2026-07-31（v3.2.1 重构批次，见「〇、最近进展」）

---

## 〇、最近进展（2026-07-31）

| 项目 | 结果 |
|------|------|
| `core/sqlite_store.py`（2649 行单体） | ✅ 拆分为 `core/sqlite_store/` 子包（base/crud/graph/analytics/search mixins + `__init__`），每文件 ≤ 676 行 |
| `core/tools.py`（2135 行单体） | ✅ 拆分为 `core/tool_registry.py` + `core/tool_defs/`（9 个领域模块）+ 门面 `core/tools.py`，118 个工具完整注册 |
| `data/stores/*.py` Mixin 类型可见性 | ✅ 各 Mixin 继承 `BaseStore`/链式继承，`JsonStore` 组合类 MRO 修正 |
| mypy 错误数 | ⚠️ 786 → **290**（在 `mypy_path=src` 正确解析下统计；修复了 mixin 链、`_read_json` 泛型、`_cached` 泛型、`with_retry` 泛型、`ToolRegistry.list` 遮蔽内建 `list` 等系统性问题） |
| CI mypy | ✅ 从 `|| true` 放行改为**增量门禁**（`scripts/mypy_gate.sh` + `.mypy-baseline`），只允许存量，禁止新增 |
| 工具接线 | ✅ 新工具 `manage_inspirations` 补注册到 executor；修复灵感 ID 截断回查与 FTS `index_material` 调用签名两个真实 bug |

---

## 一、已完成的死代码清理（历史记录）

共删除 **10 个源码文件 + 2 个测试文件**，净减约 **2,900 行**。

| 文件 | 行数 | 删除原因 |
|------|------|----------|
| `src/core/incremental_sync.py` | 212 | 增量知识图谱同步，零生产引用 |
| `src/core/prophecy_parser.py` | 253 | 预言→伏笔解析器，零生产引用 |
| `src/core/continuation_pipeline.py` | 351 | 4阶段续写管线，零生产引用 |
| `src/core/interactive_store.py` | 427 | 已标记 DEPRECATED 2.0，仅被废弃模块引用 |
| `src/core/interactive_agent.py` | 267 | 已标记 DEPRECATED 2.0，仅被废弃模块引用 |
| `src/routes/interactive_routes.py` | 253 | 已标记 DEPRECATED 2.0，未在路由注册中 |
| `src/core/foreshadow_network.py` | 268 | 伏笔网络图结构，被 Neo4j 方案取代 |
| `src/core/anchor_resolver.py` | 481 | 锚点解析引擎，`patch_chapter` 用内置 `_fuzzy_find` |
| `frontend/src/components/InteractivePanel.tsx` | 150 | 已标记 DEPRECATED，PanelHost 已切换为 SimulationPanel |
| `frontend/src/features/interactive/StoryStage.tsx` | 126 | 仅被废弃的 InteractivePanel 引用 |
| `tests/test_foreshadow_network.py` | 170 | 测试死代码模块 |
| `tests/test_anchor_resolver.py` | 191 | 测试死代码模块 |

---

## 二、修复的真实类型错误（mypy）

| 文件 | 行号 | 问题 | 修复方式 |
|------|------|------|----------|
| `src/core/graph_store.py` | 2253-2274 | `time_order` float→int 类型不匹配（dict 索引、range、slice） | 添加 `int()` 转换 |
| `src/core/context_manager.py` | 144→154 | `sr` 变量名复用（`StructureReport`→`SentenceRhythm`） | 重命名为 `struct_rpt` / `rhythm` |
| `src/core/context_manager.py` | 375-377 | `fp` 类型冲突（`StyleFingerprint`→`VoiceFingerprint`） | 重命名为 `voice_fp` |

---

## 三、预存 mypy 类型注解问题（290 条，非紧急）

> 2026-07-31 从 786 条降至 290 条（系统性修复了 store mixin 继承、JSON I/O 泛型、
> `_cached`/`with_retry` 泛型、`ToolRegistry.list` 遮蔽内建 `list` 等）。
> 剩余均为非类型化 dict 代码的注解缺失，不影响运行时行为。CI 通过
> `.mypy-baseline`（当前 320，含容差）做增量门禁。按类别分布：

| 类别 | 数量 | 典型文件 |
|------|------|----------|
| `[no-any-return]` 返回 Any | ~120 | `agent_loop.py`, `chat.py`, `headless_loop.py` |
| `[annotation-unchecked]` 未标注函数体 | ~80 | `workflow_engine.py`, `permissions.py`, `headless_loop.py` |
| `[var-annotated]` 缺少变量类型注解 | ~60 | `graph_store.py`, `context_manager.py`, `workflow_tools.py` |
| `[attr-defined]` Mixin 属性访问 | ~100 | `session_store.py`, `meta_store.py` |
| `[arg-type]` / `[return-value]` 参数/返回值类型 | ~100 | `graph_store.py`, `documents.py`, `planner.py` |
| 其他 | ~62 | 分散各处 |

---

## 四、可读性问题

### 4.1 超长函数（>100 行）

| 文件 | 函数 | 行数 | 严重程度 |
|------|------|------|----------|
| `src/core/agent_loop.py` | `_loop_inner` | ~345 | 🔴 |
| `src/core/context_manager.py` | `build_scoped_context` | ~330 | 🔴 |
| `src/core/agent_loop.py` | `_process_tool_result` | ~199 | 🟡 |
| `src/core/context_manager.py` | `build_writing_context` | ~194 | 🟡 |
| `src/core/agent_loop.py` | `_handle_tool_calls` | ~184 | 🟡 |
| `src/core/graph_store.py` | 多个方法 | 150-200 | 🟡 |

### 4.2 魔法数字

主要集中在 `src/core/context_manager.py`，多处散布预算阈值常量：

```
200, 300, 400, 500, 600, 800, 1000 (token 预算阈值)
3, 5, 6, 8 (截断数量)
0.5, 0.85, 0.3 (比例系数)
```

建议提取为模块级常量并添加注释说明选择依据。

### 4.3 单字母/双字母变量名

| 文件 | 行号 | 变量 | 建议命名 |
|------|------|------|----------|
| `context_manager.py` | 135 | `fp` | `fingerprint` |
| `context_manager.py` | 163 | `rd` | `density` |
| `context_manager.py` | 172 | `ps` | `signature` |
| `context_manager.py` | 181 | `np` | `pov` |
| `context_manager.py` | 190 | `ec` | `curve` |
| `agent_loop.py` | 254 | `kb` | `graph_store` |
| `chat.py` | 204 | `sid` | `session_id` |

### 4.4 深层嵌套（>3 层）

| 文件 | 行号 | 最大嵌套深度 | 结构 |
|------|------|-------------|------|
| `agent_loop.py` | 279-541 | 5 | while→try→if/elif→for→if |
| `agent_loop.py` | 927-997 | 5 | for→try→async for→if/elif |

### 4.5 缺少 docstring 的函数

主要集中在 `src/routes/chat.py`（约 10 个小函数）和 `src/core/agent_loop.py`（内部工具函数）。

---

## 五、安全相关

| 文件 | 行号 | 问题 | 风险 |
|------|------|------|------|
| `src/core/graph_store.py` | 42 | 硬编码 Neo4j 密码 `"novel_agent_2024!"` | 🔴 低（生产通过 `.env` 覆盖，但代码中留有明文密码） |

---

## 六、配置相关

| 问题 | 文件 | 状态 |
|------|------|------|
| pytest 配置重复（`pytest.ini` vs `pyproject.toml`） | 两处 | ✅ 已修复（删除 `pyproject.toml` 中重复段） |
| `ruff` import 排序 | 2 处 | ✅ 已自动修复 |

---

## 七、CI 当前状态

| 检查项 | 结果 |
|--------|------|
| ruff (lint) | ✅ 0 errors |
| tsc --noEmit | ✅ 0 errors |
| pytest | ✅ 704 passed, 3 skipped |
| mypy | ⚠️ 290 errors（存量，由 `.mypy-baseline` 增量门禁兜底，禁止新增） |

---

## 八、建议修复优先级

| 优先级 | 问题 | 预估工作量 |
|--------|------|-----------|
| P0 | 无 | — |
| P1 | 超长函数拆分（`_loop_inner`, `build_scoped_context`） | 2-3 天 |
| P2 | 魔法数字常量化（`context_manager.py`） | 0.5 天 |
| P2 | 单字母变量重命名 | 0.5 天 |
| P2 | 剩余 mypy 存量消化（290 条，集中在 `routes/*`、`tools/impl/*` 的非类型化 dict 代码） | 持续，按 `.mypy-baseline` 刷新节奏进行 |
| P3 | 补充缺失 docstring | 0.5 天 |
| P4 | 移除硬编码密码 | 0.1 天 |