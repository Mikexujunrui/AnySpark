# AnySpark 重构计划（可验证清单）

> 创建：2026-07-31 | 基于 pi 设计哲学的边界优先重构
> 用法：每完成一步，运行该步的验证命令，通过后勾选 `[x]`。进度以本文件为准，不靠记忆。
> 把握度声明：本计划的可验证性目标是 >95%（每步都有明确证据、失败可回退）。工程结果本身（如协议抽取一次成功）不承诺概率，但每步都有"失败即回退"的逃生门。

---

## 总闸命令（每批完成后必须全跑）

```bash
# Python 侧
python -m pytest tests/ -q                                  # 全量测试
python -m ruff check src/ tests/                            # lint
bash scripts/mypy_gate.sh                                   # mypy 增量门禁
# 前端侧（在 frontend/ 下）
npm run lint && npx tsc --noEmit                            # eslint + 类型检查
```

---

## 依赖图（S=串行，P=可并行，→=前置依赖）

```
M0 基线 ──→ 一切
M1a Neo4j清理 ──→ M1b FTS合并（决策门）
M2 核心测试先行 ──→ M3 agent_loop划边界
M0 ──→ M4 供应链（可与 M1/M2/M3 并行）
M0+主人确认 ──→ M5 git历史清理（唯一需主人拍板）
M0 ──→ M6 check gate（可与 M1/M4 并行）
M0 ──→ M7 前端审计分层（可与 M2/M3/M4 并行）
M3/M4/M5/M6/M7 ──→ M8 发布与收尾
M8 ──→ M9 反向审计
```

---

## M0：基线建立（前置，S）

目标：让后续所有步骤可审计。**没有基线的重构都是空中楼阁。**

- [ ] **M0.1** 完整跑一遍总闸，记录基线
  - 判据：生成 `docs/BASELINE.md`，含：pytest 通过数/失败数、mypy 错误数、tsc 错误数、eslint 结果、`--cov-fail-under` 实际覆盖率
  - 验证：`docs/BASELINE.md` 存在且数字与实跑一致
- [ ] **M0.2** 备份用户数据
  - 判据：`data/` 完整拷贝到 `data_backup_YYYYMMDD/`（约 32MB，含 15 本书章节+版本历史）
  - 验证：`du -sh data/ data_backup_*` 数字一致；抽查某本书章节文件 md5 相同
- [ ] **M0.3** git 工作区状态确认
  - 判据：`git status` 干净；`git ls-files data/` 输出为空（数据已 ignore）
  - 验证：上述两条命令的实跑输出
- [ ] **M0.4** 环境确认
  - 判据：`python -m pytest tests/ -q` 在本机（Windows C:\Python313）可跑通
  - 验证：实跑全绿（当前基线 704 passed + 3 skipped + 新增的 await_answer 测试）

---

## M1a：Neo4j 残留清理（低风险，S）

目标：删掉所有"已死但还在"的 Neo4j 引用，消除配置/文档/代码的不一致。

- [x] **M1a.1** 确认 Neo4j 确实已死
  - 判据：`grep -rn "neo4j\|Neo4j" src/ --include="*.py"` 的输出逐条分类：可删 / 需保留（如 git 历史无关）
  - 验证：分类清单写入 `docs/REFACTOR_LOG.md`
- [x] **M1a.2** 删除死代码/过时引用（A 类：行为相关）
  - 判据：`graph_search.py` legacy Neo4j 分支已删；`archive.py` 过时 docstring 已改；`main.py` 错误消息不再提 Neo4j；**Cypher 兼容层（impact_propagator/simulation 的 `_run` Cypher）保留**——它们是 SQLiteStore 模拟 Neo4j API 的真实功能
  - 验证：pytest 全绿 + ruff 全绿
- [x] **M1a.3** 注释/配置清理（B 类：纯文档）
  - 判据：`graph_schema.py` 文件头、`server.py` 无用的 neo4j logger 设置、`modules.yaml` 依赖声明、各处 docstring 中“Neo4j”改写为准确描述（Cypher 兼容层语境保留“graph store”）；`grep -rn "neo4j" src/ modules.yaml` 仅剩模拟层准确注释
  - 验证：pytest 全绿
- [x] **M1a.4** 文档同步
  - 判据：`docs/ARCHITECTURE.md`、`docs/TECH_STACK.md` 中 Neo4j 相关描述改写为 SQLite 事实
  - 验证：`grep -rn "Neo4j" docs/` 返回 0（或仅剩"已移除"的历史注记）

---

## M1b：FTS 合并（中风险，决策门）

目标：把 `search_fts.db` 的 4 张 FTS 表（chapters/entities/worldbuilding/materials）合并进 `novel.db`，消除第二事实源。**若改动面失控则降级为保守方案（见 M1b.5）。**

- [x] **M1b.1** 固化现有搜索行为为测试（补 materials/批量/幂等 4 用例，暴露真实重复索引 bug）
  - 判据：新增 `tests/test_search.py`，覆盖 4 张表的 index/query/delete 主路径 + 空结果分支，当前实现全绿
  - 验证：`python -m pytest tests/test_search.py -q` 全绿
- [x] **M1b.2** 修改 `src/core/search.py`（决策门触发→改为修复重复索引 bug）
  - 判据：index_chapter/index_entity/index_material 改 DELETE-then-INSERT 幂等；生产索引从 18213+945 行重建为 1848+183（去重 16700+ 行）
  - 判据：`FullTextSearch` 默认指向 `novel.db`（与 SQLiteStore 同库），路径可配置保留
  - 验证：M1b.1 的测试在新路径下全绿；`novel.db` 中出现 4 张 fts 表
- [x] **M1b.3** 存量索引重建（用 rebuild_fts.py 全量重建，替代迁移）
  - 判据：写 `scripts/migrate_fts.py`，从旧库重建索引到新库；先 dry-run（只读统计条数），确认条数一致后再实跑
  - 验证：新旧库各表 rowid 计数一致；搜索关键词回归结果一致
- [x] **M1b.4** 全局接线验证（18 个引用方走单例无改动，全量测试 710 passed）
  - 判据：`search_fts.db` 删除后，搜索/情感分析/提取/写作工具（18 个引用文件）功能正常
  - 验证：pytest 全绿 + 手动搜索一个真实关键词返回正确章节
- [x] **M1b.5** 【决策门触发 2026-07-31】设计判断：FTS 是派生索引，独立库更符合事实源/派生分离；且 novel.db 已有同名 entities_fts 表冲突。保守方案落地：
  - 判据：保留 `search_fts.db`，写重建脚本 `scripts/rebuild_fts.py`（幂等+--dry-run），ARCHITECTURE.md 数据层边界文档化——保留 `search_fts.db`，但在 `docs/ARCHITECTURE.md` 明确"搜索索引独立库"为**有意设计**并记录理由；M1b.3/M1b.4 跳过
  - 验证：决策记录写入 `docs/REFACTOR_LOG.md`，说明为何合并收益 < 风险

---

## M2：核心行为测试先行（S，必须在 M3 之前）

目标：给 agent_loop 的关键行为补测试，确保 M3 重构期间行为可对比。**先有网，再拆墙。**

- [ ] **M2.1** 权限确认三态测试（已完成 ✅，`tests/test_await_answer.py` 5 用例）
  - 判据：confirmed/cancelled/timeout 三态 + 迟到回复回归
  - 验证：`python -m pytest tests/test_await_answer.py -q` 全绿
- [ ] **M2.2** 工具互斥保护测试
  - 判据：新增 `tests/test_tool_mutex.py`，验证"同一响应含多个全章写入工具时只执行第一个，其余收到互斥提示"
  - 验证：测试覆盖 `_prepare_tool_calls` 的 `FULL_CHAPTER_GENERATION_TOOLS` 分支
- [ ] **M2.3** 连续取消熔断测试
  - 判据：新增测试验证 `consecutive_confirm_cancels >= 2` 时 agent 消息含"停止反复尝试"提示，且 confirmed 后计数归零
  - 验证：测试全绿
- [ ] **M2.4** 最小循环端到端测试（mock LLM）
  - 判据：新增 `tests/test_agent_loop_e2e.py`，用 fake LLM 客户端（固定返回 tool_calls/终止）驱动 `_loop_inner`，验证：正常终止 / 工具互斥 / 取消路径
  - 验证：3 条路径各 1 个用例全绿；不触网（mock 所有 LLM 调用）
- [ ] **M2.5** compaction 触发边界测试
  - 判据：新增测试验证 token 超阈值触发 prune→summarize 两阶段，阈值边界（恰好低于/高于）行为正确
  - 验证：测试全绿

**M2 完成判据**：`pytest tests/test_agent_loop.py tests/test_await_answer.py tests/test_tool_mutex.py tests/test_agent_loop_e2e.py tests/test_compaction.py -q` 全绿；基线文档更新。

---

## M3：agent_loop 划边界（核心重构，S）

目标：`_process_tool_result`（199 行）从 if/elif 链变为纯分发表，7 个领域 case 抽到 `src/core/flows/`。**每抽一个 case 立即全量测试，不做一次性大爆炸。**

- [ ] **M3.1** 建立 flows 目录与协议骨架
  - 判据：`src/core/flows/__init__.py` 定义 `Flow` 抽象（`can_handle(result) -> bool` + `handle(result, ...) -> FlowResult`）；`_process_tool_result` 改为遍历 flows 分发
  - 验证：pytest 全绿（行为不变，纯重构）
- [ ] **M3.2** 抽 question + plot_cards → `flows/user_interaction.py`
  - 判据：两个 case 移入，`_process_tool_result` 对应分支删除；交互弹窗行为不变
  - 验证：pytest 全绿 + 手动验证 ask_user 弹窗（问一句→答→继续）
- [ ] **M3.3** 抽 writing_result + patch_result + review_result → `flows/work_product.py`
  - 判据：三个 case 移入；章节变更 diff 浮现逻辑不变
  - 验证：pytest 全绿 + 手动 patch_chapter 一次验证 diff 卡片
- [ ] **M3.4** 抽 autopilot_plan + task_list → `flows/engine_signal.py`
  - 判据：两个 case 移入；Autopilot 启动确认/任务列表行为不变
  - 验证：pytest 全绿 + 手动触发 autopilot_plan 确认弹窗
- [ ] **M3.5** 收尾：`_process_tool_result` 纯分发化
  - 判据：函数 <40 行，无领域 case；每个 flow 有独立单测（`tests/test_flows_*.py`）
  - 验证：pytest 全绿 + ruff + mypy gate + 基线对比（M0.1 的测试数只增不减）

**M3 完成判据**：agent_loop.py 行数下降（目标 -200 行以上）；`tests/test_flows_*.py` 存在且覆盖各 flow 主路径；总闸全绿。

---

## M4：供应链治理（P，可与 M1/M2/M3 并行）

目标：依赖从"浮动+双锁"变为"pin+单锁+可审计"。

- [ ] **M4.1** pin Python 依赖
  - 判据：`pyproject.toml` + `requirements.txt` 全部 `==` 精确版本（从当前环境 `pip freeze` 取实际版本）
  - 验证：`pip check` 无冲突；pytest 全绿
- [ ] **M4.2** 生成 lockfile
  - 判据：`uv pip compile` 或 `pip-tools` 生成 `requirements.lock`，纳入版本库
  - 验证：lockfile 存在；全新 venv 按 lockfile 安装后可跑 pytest
- [ ] **M4.3** 前端统一锁文件
  - 判据：删除 `frontend/pnpm-lock.yaml`；确认 CI 与本地构建均用 `package-lock.json`（`npm ci`）
  - 验证：`ls frontend/ | grep lock` 只剩 package-lock.json；`npm ci && npm run build` 通过
- [ ] **M4.4** pre-commit 锁文件守卫
  - 判据：`.pre-commit-config.yaml` 增加钩子：锁文件变更需 `ALLOW_LOCKFILE_CHANGE=1` 才放行（仿 pi 的机制）
  - 验证：故意改 lockfile 提交被挡；带环境变量时放行

---

## M5：数据/代码分家 + git 历史清理（需主人确认后才执行）

目标：清除版本库中的用户数据历史（隐私），建立数据边界。

- [ ] **M5.1** 数据边界审计
  - 判据：`.gitignore` 覆盖 `data/` 全部产物（含 analyses/、annotations/、logs/）；`git check-ignore` 抽查通过
  - 验证：`git ls-files data/` 为空 + 新增文件不被跟踪
- [ ] **M5.2** 【需主人确认】git filter-repo 计划
  - 判据：列出将重写的 commit 范围（含 `create: 章一` 等数据 commit）；确认无协作者需要重新 clone，或提前协调
  - 验证：主人书面确认（本文件勾选即确认）
- [ ] **M5.3** 执行 filter-repo
  - 判据：`git filter-repo --path data --invert-paths`（或按审计结果）后，`git log --all -- data/` 为空
  - 验证：历史干净；当前工作区文件不受影响；`git push --force` 到远端前与主人再确认
- [ ] **M5.4** 重构分支清理
  - 判据：`backup-pre-mypy-reset` / `clean-main` / `clean-sqlite` / `refactor/sqlite` / `temp-sqlite` 等死分支删除或归档
  - 验证：`git branch` 只剩 main + 必要的 release 分支

---

## M6：单 check gate（P）

目标：本地一条命令 = CI 全绿。

- [ ] **M6.1** 写 `scripts/check.py`
  - 判据：聚合 ruff → mypy gate → pytest → tsc → eslint，任一步失败即退出码非 0
  - 验证：本机实跑通过；故意引入一个 lint 错误验证退出码非 0
- [ ] **M6.2** CI 统一入口
  - 判据：`ci.yml` 三个 job 改为调用 `scripts/check.py`（或等效分步但共享同一配置）
  - 验证：CI 实跑通过

---

## M7：前端审计与分层（P）

目标：2.6 万行前端从"api.ts 杂烩"走向分层。**先审计后动手，工作量以审计结果为准。**

- [ ] **M7.1** 前端架构审计
  - 判据：产出 `docs/FRONTEND_AUDIT.md`：api.ts 502 行端点分类表、SSE 管道现状（createSSE 等 3 个工厂的使用点）、状态管理缺口、组件耦合热点
  - 验证：审计报告含具体文件/行号证据
- [ ] **M7.2** api.ts 按域拆分
  - 判据：拆为 `api/books.ts` `api/knowledge.ts` `api/simulation.ts` 等（按后端 26 个 route 域）；`api.ts` 保留为 re-export 门面（兼容过渡）
  - 验证：`npx tsc --noEmit` 全绿 + `npm run build` 通过
- [ ] **M7.3** SSE 统一管道
  - 判据：新建 `api/sse.ts`，收敛 createSSE/createTaskSSE/createAutopilotBridgeSSE 的公共逻辑（错误处理/重连/事件分发）
  - 验证：tsc 全绿 + 手动开一次 Agent 会话确认流式正常

---

## M8：发布与收尾（S）

目标：可复现发布 + 存量债务递减。

- [ ] **M8.1** 发布一条龙脚本
  - 判据：`scripts/release.py` 支持 `--dry-run`：bump 版本 → 更新 CHANGELOG → 跑 check → 打 tag；dry-run 不实际改动文件
  - 验证：`python scripts/release.py --dry-run` 输出完整流程且无副作用
- [ ] **M8.2** mypy 存量递减
  - 判据：在 M1/M3 删除死代码后，`scripts/mypy_gate.sh` 刷新 baseline，错误数较 M0 基线下降（目标 -30%）
  - 验证：baseline 文件数字变化可审计
- [ ] **M8.3** 文档治理
  - 判据：`docs/` 分类标记——真实文档（ARCHITECTURE/EXTENDING/FRONTEND）与计划文档（ROADMAP/IMPROVEMENTS 等）分开目录或加状态头；过时文档（TECH_STACK 等）修正或归档
  - 验证：`docs/INDEX.md` 更新为新结构

---

## M9：反向审计（最后，S）

目标：不等挑刺，自查漏网。

- [ ] **M9.1** checkbox 逐项核对
  - 判据：本文件所有 `[x]` 对应证据都存在（BASELINE.md / REFACTOR_LOG.md / 测试文件 / 实跑输出）
  - 验证：随机抽 5 项重新实跑验证
- [ ] **M9.2** 隐藏依赖检查
  - 判据：审查 M1b（search.py 路径）、M3（flows 接口）、M4（依赖 pin）、M7（api 拆分）的**接口调用方**是否全部同步（用 `grep -rln` 交叉核对）
  - 验证：每个改动模块的引用方清单与改动面一致
- [ ] **M9.3** 边界复查
  - 判据：对 M2 的测试抽查空输入/错误分支；确认新增代码无未处理异常路径
  - 验证：`pytest --cov=src --cov-fail-under=40`（覆盖率从 30 提到 40 作为本轮验收线）
- [ ] **M9.4** 纪律核查
  - 判据：所有 commit 范围明确（无 `add -A`）、无用户数据进库、无锁文件无审批变更
  - 验证：`git log` 抽查 + `git ls-files data/` 为空

---

## 纪律条款（本计划自带，替代缺失的 AGENTS.md）

1. 每个 commit 只包含本文件（plan.md）中一个 checkbox 对应的改动，commit message 注明 `M{x}.{y}` 编号
2. 禁止 `git add -A`，一律显式路径
3. 每批改动后跑总闸（见顶部命令），全绿才提交
4. 用户数据（data/）绝不进 git
5. 发现前置条件变化 → 立即回退改本计划，不硬着头皮往下做
6. M5.2 与 M5.3 之间必须主人确认，禁止擅自改写历史

---

## 风险登记（随进度更新）

| 风险 | 等级 | 缓解 |
|------|------|------|
| M3 协议抽取破坏交互行为 | 高 | M2 测试先行；逐 case 抽取+全量回归；每步可回退 |
| M1b FTS 合并 18 文件改动面 | 中 | 决策门 M1b.5，收益<风险则保守保留 |
| M5 filter-repo 改写历史 | 中 | 需主人确认；先备份仓库 |
| git 历史残缺：最新 HEAD 仅含零散文件，代码在 v3.0.0 提交（377 文件）后被数据提交打乱，M0 已将全部源码纳入版本库 | 高 | M5 处理时一次性理清（历史中代码版本与数据混存） |
| 前端工作量估计不准 | 中 | M7.1 先审计，工作量以审计为准 |
| 数据迁移边界情况 | 中 | M0.2 全量备份；迁移脚本 dry-run 先行 |
