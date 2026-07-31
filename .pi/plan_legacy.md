# 遗留问题清理计划（L 系列）

> 创建：2026-08-01 | 承接 `.pi/plan.md` M0-M9 完成后的遗留项
> 来源：`docs/ONBOARDING.md` 第 6 节 + `docs/CODE_HEALTH_ISSUES.md`
> 用法：每完成一步，运行该步验证命令，通过后勾选 `[x]`。进度以本文件为准。
> 纪律：沿用 plan.md 纪律条款（禁 `git add -A`、显式路径、每批跑门禁、data/ 不进 git）。

---

## 基线（2026-08-01 实跑）

| 项 | 值 |
|----|----|
| pytest | 743 passed, 1 skipped |
| 覆盖率 | 38%（gate 38） |
| ruff | 全绿 |
| mypy | 269（baseline 271，低于基线 2） |
| tsc/eslint | 待跑（需 npm） |

---

## 依赖图

```
L0 基线 ──→ L1 mypy清零 ──→ L2 覆盖率40 ──→ L3 前端拆分 ──→ L4 收尾复核
L4.0 git污染协调（贯穿，需主人配合外部进程）
```

---

## L1：mypy 存量清零（269→0，低风险）

目标：把 `.mypy-baseline` 数字压到 0，删除 baseline 门禁机制（或设为 0 容差）。

策略：按文件分批修复，每批跑 `mypy` 计数 + 相关 pytest，只增不减。

- [x] **L1.1** writing.py（19 条）：工具返回类型 `-> str` 实为 `str | dict`（guard 返回 str，正文返回 dict），改签名 `-> str | dict`（与 executor `_call_handler` 返回 `str | dict` 对齐）
  - 判据：`writing.py` 错误数 19→0；`pytest tests/test_generation_writing.py tests/test_writing*.py -q` 全绿
- [x] **L1.2** workflow_tools.py（16 条）：`Workflow` 变量被标注为 dict，类型注解修正（flow/exec_context 改名 + results 注解）
- [x] **L1.3** context_manager.py（16 条）：dict 返回值/变量注解（foreshadow 对象化修复链，见 L1.4）
- [x] **L1.4** sqlite_store（13+ 条）：`_row_to_*` 签名 `sqlite3.Row`→`dict[str, Any]`（与 `_run` 返回 `list[dict]` 对齐）；`list_scheduled_foreshadows` 改返回真 `Foreshadow` 对象（此前调用方对象属性访问实际拿到 dict，是静默 bug 隐患）；`Relation.type` 两处 str→RelationType
- [x] **L1.5** desktop_launcher.py（12 条）：`_MEIPASS`/类型注解（window: Any、fcntl 平台 ignore、bool cast）
- [x] **L1.6** handlers.py + plot.py + extractor.py（28 条）：handler 变量名冲突（c/names/e 复用）；**修复 list_snapshots(character_entity_id=) 无效参数真实 bug（阶段计数曾统计全部角色）**；extractor 修复 `EntityType.value` 真实崩溃 bug（str 子类无 .value，spaCy NER 分支未测覆盖）；plot 返回类型 str|dict + llm_chat cast
- [ ] **L1.7** agent_loop/headless_loop/flows（22 条）
- [ ] **L1.8** 其余散落（routes/*、tools/impl/* 余量 ~140 条）
- [ ] **L1.9** baseline 归零：`.mypy-baseline` 写 0；`scripts/mypy_gate.sh` 实跑通过
  - 验证：`bash scripts/mypy_gate.sh` 输出 errors: 0

## L2：覆盖率 38→40+（中风险）

目标：补大文件测试，覆盖率 ≥40%，CI gate 同步升到 40。

- [ ] **L2.1** 覆盖率缺口清单（writing.py 724 missed / knowledge.py 685 / generation.py 554 等）
- [ ] **L2.2** 补 writing.py 测试（+7% 目标，写主路径 + 错误分支，mock LLM）
- [ ] **L2.3** 补 knowledge.py 测试（+2%）
- [ ] **L2.4** 补 routes/chat.py + extractor.py 测试
- [ ] **L2.5** gate 升 40：`--cov-fail-under=40` 实跑通过
  - 验证：`pytest --cov=src --cov-fail-under=40` 全绿

## L3：前端拆分（中高风险）

- [ ] **L3.1** api.ts 全量拆分（按后端 route 域拆 `api/books.ts` 等，api.ts 保留 re-export）
- [ ] **L3.2** ChaptersPanel 1329 行拆分（tab 管理 / 章节列表 / 编辑器 / 历史 / diff 预览抽离）
- [ ] **L3.3** 其他巨型组件（ChatPanel 1156 / SettingsModal 1045）按需拆分
  - 验证：`npx tsc --noEmit` 全绿 + `npm run build` 通过 + 手动回归

## L4：收尾

- [ ] **L4.1** 文档同步（ONBOARDING 第 6 节、CODE_HEALTH_ISSUES、BASELINE）
- [ ] **L4.2** 总闸全跑 + 勾选核对

## L4.0：并发 git 污染（贯穿，需主人协调）

现状：外部自动化进程曾 `git add -A` 提交 chapters 数据（7+ 提交污染历史，已恢复）。
- [ ] 确认当前无外部进程再提交；如需保留自动化提交 → 约定只操作 `data/` 子目录且显式路径
- [ ] 最终确认：`git log --oneline` 无数据提交；`git ls-files data/` 为空

---

## 风险登记

| 风险 | 等级 | 缓解 |
|------|------|------|
| mypy 修复破坏运行时行为 | 中 | 每批跑相关 pytest；类型标注改动不涉及逻辑 |
| 覆盖率补测时间成本高 | 中 | 挑大文件主路径，mock LLM/DB |
| 前端拆分影响交互 | 高 | 纯提取不重构；tsc+build+手动回归 |
| 外部进程再次污染 git | 中 | 需主人协调；pre-commit 钩子已拦截（`--no-verify` 除外） |
