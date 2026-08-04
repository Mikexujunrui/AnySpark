# AnySpark benchmark

半独立评测子项目：客观指标 + 人工评价并存，评估 AnySpark v4 是否符合设计哲学、
单机制是否工作、相比裸 LLM 是否真的更好。

## 定位（三个独立问题）

| 层 | 回答的问题 | 判据 | 频率 |
|---|---|---|---|
| `unit/` 单元层 | 每个机制单独工作正常吗 | 客观断言（F1/发现率/命中率/相似度） | 常跑 |
| `system/` 系统层 | 总体运行符合哲学吗（摩擦前置递减/对齐累积） | 过程指标（复用 /api/stats + 剧本） | 定期 |
| `compare/` 对比层 | 相比裸 LLM 好在哪 | 客观（token/冲突/违规）+ 人工（终稿质量） | 发布验收 |
| `human/` 人工层 | 产出是不是垃圾/能不能读/哪个更好 | 人工三档粗筛 + 成对盲测二选一 | 每轮对比 |

原则：
- **黑盒**：只通过 HTTP API 交互，不 import 任何 `anyspark.*` 内部模块
- **半独立**：可单独拷走运行（需后端可达）；不修改主项目代码（除 `--db` 启动参数，属后端通用能力）
- **不入库**：`report/`、`assets/`、`unit/gold/` 均为本地资产（gitignore），gold 需人工准备

## 用法

```bash
# 单元层：自动启动隔离后端（独立 db，不污染主库）跑全部任务
uv run python -m benchmarks.unit.run_unit --spawn

# 连外部后端（如已起 anyspark-server --port 9000 --db /tmp/bench.db）
uv run python -m benchmarks.unit.run_unit --base http://127.0.0.1:9000

# 只跑单个任务
uv run python -m benchmarks.unit.run_unit --spawn --task T1

# 对比层：AnySpark vs 裸 LLM（同模型、长程任务、客观指标）
uv run python -m benchmarks.compare.run_compare --spawn
```

## 对比层设计（诚实原则）

- 同一任务 × 同一模型（deepseek-v4-flash）× 同一输入：裸 LLM = 无任何系统的直接调用
- 三任务：A 设定忠实度（哈利波特设定续写）/ B 长书一致性（原创种子 5 章）/ C 偏好跨轮记忆（禁破折号，第 2 章不重复偏好）
- 判据：token 计数客观；设定违规/名字漂移用 LLM 裁判（同模型双方同一裁判，公平可重复）
- **已知事实（2026-08-04 首轮）**：短/中程任务（≤5 章）裸 LLM 与 AnySpark 质量相当、裸 LLM 便宜 1.7-2.4x；AnySpark 的差异价值在长书记忆/多轮对齐/可观测性（如能动性【AI补充】标注）——对比层 v1 诚实呈现，不夸大

## 评测资产（本地手工，不入库）

- `assets/ch1-3.txt`：哈利波特与魔法石（人文社译本）前三章原文（版权合理使用，不公开分发）
- `unit/gold/`：前 3 章实体/关系/事件 gold 标注 + 预埋冲突文本 + 记忆核对点 + 时序测试文本
  （事实性数据；标准译名 + OCR 变体记录，匹配用双向包含宽容）
- 为什么用哈利波特而非系统自产文本：独立性（避自产自测偏差）+ 可核验性（公认答案）

## 报告

`report/unit-<时间戳>.md`：每任务 PASS/FAIL + 数值指标；记录后端环境。
