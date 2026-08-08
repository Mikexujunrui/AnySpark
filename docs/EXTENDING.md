# EXTENDING.md — 贡献者指南：如何给 AnySpark 加能力

> 目的：让新贡献者（不熟悉项目的人）知道**加一个功能有哪几条路、每条路改哪些文件、怎么测试怎么提交**。不重复 DESIGN.md 的设计细节，只讲"动手路径"。
> 阅读前提：先读 `docs/DESIGN.md` 第 1 节（设计哲学/硬编码边界）与第 4 节（架构/单向依赖），再读本指南。

---

## 0. 先决定：你做的是哪一类扩展？

| 类型 | 复杂度 | 改主项目代码？ | 适合做什么 | 看哪节 |
|------|--------|---------------|-----------|--------|
| **A. 数据工具**（P5 扩展注册表） | 🟢 低 | 不需要 | 一段独立逻辑：统计/转换/检索/小工具 | §1 |
| **B. 独立包**（仿 workflow） | 🟡 中 | 3 处接线 | 一类领域能力：新引擎/新存储/新 API | §2 |
| **B+. 在现有包内加东西**（explore/align/template/graph/check/workflow） | 🟢🟡 低-中 | 基本不用（接口稳定则 app 无感） | 给探索/对齐/图谱/检测/工作流加能力 | §3 |
| **C. 动 core 或跨包接口** | 🔴 高 | 深度改动 | 改 Agent 循环/协议/包间接口 | §4 |

**快速判断**：如果"一句话能说清要做什么、且不涉及新存储/新 API/新模型调用"→ 走 A。如果是一个完整能力域 → 走 B。如果是在某个现有包内增强（加新探索者/新策略/新检测项）→ 走 B+（鼓励，难度低）。如果是要改变 core 或包间公开接口 → 走 C（先找主人确认）。

---

## 1. 类型 A：数据工具（零代码改主项目）

**机制**（S48-P4/B）：扩展工具 = SQLite 里的一条记录（代码字符串），**人工批准才生效**。执行走沙箱（白名单 + 只读数据环境 + 超时），即使批准也不接触文件系统原始能力。

**写一段 Python 函数**：
```python
def run(args: dict) -> str:
    text = args.get("text", "")
    return f"字数：{len(text)}"
```

**注册**（HTTP API）：
```json
POST /api/tools/register
{
  "name": "count_chars",
  "description": "统计文本字数",
  "params": [{"name": "text", "type": "string", "required": true, "description": "要统计的文本"}],
  "code": "def run(args: dict) -> str:\n    text = args.get('text', '')\n    return f'字数：{len(text)}'"
}
```
→ 状态 draft（不生效）→ `POST /api/tools/{id}/approve` 人工批准 → active 注入 Agent 工具集（无需重启）。

**可用数据环境**（codex 沙箱注入的 `ws_*`）：只读章节/图谱/设定——查看 `packages/app/src/anyspark/server/codex.py` 的 `make_data_env`。

**测试**：`uv run pytest packages/app/tests/test_codex.py packages/app/tests/test_tools_extras.py`

**要点**：
- 代码契约：必须定义 `run(args: dict) -> str`，返回文本即工具输出
- 沙箱内不可写文件系统、不可网络（默认）；需要更强能力请走类型 B
- 安全底线是双保险：人工批准 + 沙箱执行，两边都不可绕过

---

## 2. 类型 B：独立包（推荐路径，workflow 是现成模板）

**前提**：`packages/workflow/` 是 S59 做的完整范例（顺序/分支/循环 + 断点恢复 + AI 生成）。照它的结构做，几乎不会踩坑。

### 2.1 建包

```
packages/<yourpkg>/
├── pyproject.toml          # 照抄 workflow 的，依赖只写 anyspark-core
├── src/anyspark/<yourpkg>/ # 注意：包名空间是 anyspark.*（workspace 约定）
│   ├── __init__.py         # 导出公共 API
│   ├── store.py            # SQLite 存储（可选）
│   ├── engine.py           # 核心逻辑（可选）
│   └── ...
└── tests/test_<yourpkg>.py
```

`pyproject.toml` 模板（copy workflow 的）：
```toml
[project]
name = "anyspark-<yourpkg>"
version = "0.0.1"
description = "..."
requires-python = ">=3.11"
dependencies = ["anyspark-core==0.0.1"]  # workspace 成员

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/anyspark"]

[tool.uv.sources]
anyspark-core = { workspace = true }
```

### 2.2 注册进 workspace（改根 `pyproject.toml` 两处）

```toml
# ① members 数组加你的包
[tool.uv.workspace]
members = ["packages/*"]   # 已通配，无需改

# ② 如果 app 包需要依赖它，在 [tool.uv.sources] 加
anyspark-<yourpkg> = { workspace = true }

# ③ [project] dependencies 加 "anyspark-<yourpkg>==0.0.1"
```

### 2.3 组合根接线（改 `packages/app/src/anyspark/server/app.py` 3 处）

以 workflow 为例，共 3 个触点：

```python
# ① import（文件顶部）
from anyspark.workflow import WorkflowStore, WorkflowEngine, ...   # 你的包

# ② 实例化（build_app 内，与其他 Store 并列）
your_store = YourStore(real_db)          # 约 app.py:913 一带
your_engine = YourEngine(your_store, ...)

# ③ 装配：HTTP API 路由（build_app 内 @app 装饰器块）+ Agent 工具（build_toolkit）
@app.post("/api/your-feature", ...)       # 在 API 块里加路由
def your_feature(req: ...): ...
# 以及工具：build_toolkit 里加 make_xxx_implementer（看 toolkit.py 的 enable_workflow 分支）
```

### 2.4 Agent 工具（可选）

- 仿 `packages/app/src/anyspark/server/tools_workflow.py`：`make_xxx_tools(...) -> list[tuple[ToolSpec, impl]]`
- 在 `toolkit.py` 加开关（默认关，如 `enable_workflow`），组合根传参
- 工具哲学：只读/启动类权限，删除/修改留给用户 API（见 tools_domain.py 顶部注释）

### 2.5 测试与门禁

```bash
uv run pytest packages/<yourpkg>/tests/     # 新包测试
uv run pytest                                # 全量（约 8 分钟）
uv run python scripts/gate.py                # 总闸：ruff + mypy + pytest
```

**提交纪律**：
- 禁 `git add -A`，显式路径 add
- commit 标阶段编号（如 `S64: ...`），说明新增什么 + 测试结果
- 提交前 `git status --short` 确认不含并行会话的改动

**硬性约束（违反会被拒）**：
- 你的包**只依赖 anyspark-core**，绝不反向依赖 app/align 等上层包（单向依赖铁律）
- core 一行不许动（除非主人批准）
- 机制硬编码、内容自然语言（不要用正则/关键词"猜"语义判断——见 S62 教训）

---

## 3. 类型 B+：在现有包内加东西（推荐，难度低）

**关键认识**：项目包之间是**单向依赖 + 稳定接口**。explore/align/template/graph/check/workflow 都只依赖 core，对外通过各自 `__init__.py` 暴露稳定接口（如 explore 的 `run_exploration`/`IntentUnderstander`/`run_roleplay`）。

**含义**：
- **包内加新能力**（新探索者/新策略/新检测项/新伏笔类型）→ 在该包内加模块/函数，**只要不动 `__init__` 的公开接口，调用方（app）零改动**
- 改包内部实现 → 接口不变则 app 无感
- 谁在调这个包：查 `grep -rln "from anyspark.<pkg>" packages/ --include="*.py" | grep -v /<pkg>/`——app 和 tools 是调用方

**怎么做**（以给 explore 加新探索者为例）：
1. 在 `packages/explore/src/anyspark/explore/` 加新模块（或改 `explorers.py`）
2. 若需要对外暴露：在 `__init__.py` 加导出（不动既有导出名）
3. 跑该包测试：`uv run pytest packages/explore/tests/`
4. 如需 app 层接入（新 API/新工具）：参考 §2.3 组合根接线

**边界**：如果改的是**跨包行为**（比如探索产出的内容形态会流进图谱/心智）——代码不耦合，但行为影响下游，改动前想清楚下游是否接受（必要时问主人）。

---

## 4. 类型 C：动 core 或跨包接口（高，先确认）

**适用**：改 core（Agent 循环/协议/上下文管道——零依赖、全项目依赖它、改坏全崩）、改包间公开接口（波及所有调用方）、改架构行为（如心智/对齐/C 架构）。

**必须做的**：
1. **先向主人确认**（AGENTS.md 纪律：对设计的偏离/新增先确认）
2. 深度读 DESIGN.md 相关章节（§1 哲学、§12 演进补记——理解"为什么这么设计"）
3. 改动后更新 DESIGN.md（新 §12.x，先 `grep -n "^### 12\." docs/DESIGN.md | tail -3` 查最大编号，防撞号）

**常见坑（前人踩过）**：
- "人类预设规则"：用正则/关键词/阈值做语义判断（S62 已清理一批，如正则猜负例/8 关键词猜弱信号/首字否定词解析模型回答）——**语义判断交给模型，规则只做机制**
- 破坏单向依赖：core 被上层 import
- 编号冲突：并行会话可能同时写文档

---

## 5. 参考索引

| 想做什么 | 看哪 |
|---------|------|
| 设计哲学/硬编码边界 | DESIGN.md §1 |
| 架构/单向依赖/包划分 | DESIGN.md §4 |
| 工具注册机制 | `toolkit.py` + `tools_domain.py`（注释即规范） |
| 数据工具（P5） | `tools_extensions.py`（顶部注释） |
| 独立包范例 | `packages/workflow/`（S59） |
| API 风格 | `app.py` 的 @app 装饰器块 |
| 测试/门禁/提交 | 本文件 §2.5 + AGENTS.md（Git 纪律） |
| 接入通道（pi 工具） | `docs/DEV-AGENT.md` |
