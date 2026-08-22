# 修复清单（质量债/死代码——主人 S147 质询后系统扫描产物）

> 2026-08-14：主人问"还有没有 bug / 代码质量有没有降低 / 架构有没有变丑"，
> vulture + ruff + 调用链扫描确认以下清单。**从简单到困难排序**，逐项实施；
> D 类复杂项见单独文档 `docs/REPAIR-WF-SCRIPT-SPLIT.md`。

---

## A 类：立即修（低风险，纯删除/签名清理，~30 分钟）

### A1. 删 `mindgen._strip_fence`（真死代码）
- **位置**：`packages/align/src/anyspark/align/mindgen.py:120`
- **问题**：无任何调用方（生产+测试均无）
- **方案**：删除函数
- **工作量**：5 分钟 | **风险**：无（vulture 100% 未用）

### A2. 删 `skills.tag_list`（真死代码）
- **位置**：`packages/align/src/anyspark/align/skills.py:124`
- **问题**：无调用方（S127 skills 表 type 列后该方法被弃）
- **方案**：删除方法
- **工作量**：5 分钟 | **风险**：无

### A3. `_sent_has` 删 `kw_len` 参数（签名垃圾参数）
- **位置**：`packages/app/src/anyspark/server/tools_domain.py:693`
- **问题**：参数 `kw_len` 函数体内未使用——调用方以为"句级排除按关键词长度"生效，
  实际是误导（无害但错误）
- **方案**：删参数 + 清理调用点（search_chapters 里 2 处 `_sent_has(content, idx, len(term), exclude)` → 3 参）
- **工作量**：10 分钟 | **风险**：低（纯签名，行为不变）

### A4. 删 `skillgen.generate_main / generate_plot`（生产无调用）
- **位置**：`packages/align/src/anyspark/align/skillgen.py:878,887`
- **问题**：生产全走 `generate()` 主方法（routes_skills/tasks/tools_domain 均调 generate）；
  这两个便捷方法仅测试引用（S127 重构后遗留）
- **方案**：删方法 + 删 `tests/test_skillgen.py` 的 2 个相关测试（generate_main 用例、
  generate_plot 用例——若语义已被 generate(mode=) 覆盖则删，否则改调 generate）
- **工作量**：20 分钟 | **风险**：低（需同步改测试）

---

## B 类：需决策（仅测试锚点——YAGNI 删 vs 未来 API 留）

### B1. `manual.dedupe`（仅测试）
- **位置**：`packages/align/src/anyspark/align/manual.py:205`
- **现状**：生产无调用，仅 `tests/test_manual.py` 2 个用例
- **决策**：说明书去重能力——S62 后生产走增量游标不调它。按 YAGNI 删（连同测试）
  or 保留作公共 API？**建议删**（有替代机制，防死代码回流）

### B2. `storytree.current_path`（仅测试）
- **位置**：`packages/align/src/anyspark/align/storytree.py:216`
- **现状**：仅 `tests/test_storytree.py:25` 调用
- **决策**：叙事树当前路径能力——前端/生产是否用？若 S58c 会话继承后无消费者则删。
  **建议删**（同 B1）

### B3. `pipeline.find_image_refs`（仅测试）
- **位置**：`packages/app/src/anyspark/server/pipeline.py:146`
- **现状**：仅 `tests/test_pipeline.py:102` 调用
- **决策**：提取文档图片引用——EPUB 导出携图（P3）曾用？现在导出走哪？若 EPUB 不再
  用则删。**建议保留**（导出管线可能按需用，但需确认当前导出路径）

> B 类统一决策后一次性处理（三个一起删/留，避免逐个往返）。

---

## C 类：中改（质量改善，~1 小时）

### C1. 测试装配抽 helper（6 处 ToolContext 复制粘贴）
- **位置**：`packages/align/tests/test_skills.py`、`test_adapters.py`、
  `test_reference_lookup.py`(×2)、`test_workflow_delegate.py`、`test_workspace.py`
- **问题**：每处复制 ~25 行 `build_toolkit(ToolRegistry(), ToolContext(...))`——
  新增依赖字段时（如 S121 subagent_deps）所有测试手动同步，S105 就漏传过 book_id
- **方案**：抽 `packages/app/tests/conftest.py`（或 `tests/_toolkit.py`）helper：
  `make_registry(deps, **overrides)`——测试一处装配、参数化覆盖
- **工作量**：1 小时 | **风险**：中（测试面广，改后全量 pytest 验证）

---

## D 类：复杂改造（单独文档 `docs/REPAIR-WF-SCRIPT-SPLIT.md`，~2-3 小时）

### D1. `_wf_run_script` 拆分（500 行 if/elif → script 注册表）
- **位置**：`packages/app/src/anyspark/server/app.py:1002-1560`
- **问题**：20 个 script 分支（batch_prepare/book_refine_*/chapter_*/conversation_*/
  enrich_stitch/list_chapters/noop/query_reference/read_chapter/read_graph/
  read_settings/review_chapter/signal_refine/write_chapter）全堆一个函数——
  每个 workflow 阶段都在加分支，函数持续膨胀（S129 起 +14 个）
- **方案**：`WF_SCRIPTS: dict[str, Callable]` 注册表——每个 script 独立函数定义 +
  一行注册；`_wf_run_script` 只做 dispatch + 统一错误处理。**详见单独文档**

### D2. app.py 1763 行瘦身（组合根瘦身）
- **位置**：`packages/app/src/anyspark/server/app.py`
- **问题**：组合根 + 8 个模板种子函数 + _wf_run_script + 闭包中间件全在 app.py
- **方案**：D1 完成后 script 分发迁出；模板种子（_seed_*）拆 `seed_templates.py`；
  组合根保持（FastAPI 装配本就该一处）
- **工作量**：D1 后 1 小时 | **风险**：中（行为零变化原则，逐块搬移 + 全量测试）

---

## 实施顺序（从简单到困难）

```
A1 → A2 → A3 → A4 → B（统一决策）→ C1 → D1 → D2
```

- A 类：一个 commit（低风险批量清理）
- B 类：决策后一个 commit
- C 类：一个 commit（conftest helper + 6 处替换 + 全量验证）
- D 类：按单独文档分步，D1 独立 commit，D2 独立 commit，各跑全量 gate
