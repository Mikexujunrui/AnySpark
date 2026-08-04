# AnySpark v4

> **每个人心中都有一簇火花，AnySpark 帮你点燃它。**

AnySpark 是一个 AI 小说创作引擎。**最终目的：AI 写小说。**

v4 是一次**二次项目**——绿地独立建设，不复用旧代码（旧系统只作思想参考），**不做旧数据导入/转移，绿地空库起步**（主人 2026-08-02 决策A，旧系统仅作思想参考）。核心理念：**写作即对话**——用户说话，智能体直接写；智能体的第一能力不是守规矩，而是**懂你**。

## 快速开始（开发环境）

```bash
# 1. 配置真实模型（复制 .env.example 为 .env，填入 DeepSeek key）
cp .env.example .env

# 2. 一键启动（后端 8000 + 前端 5173，写作即对话）
bash scripts/dev.sh
# 或分开：
uv sync && uv run anyspark-server   # 后端
cd frontend && npm ci && npm run dev # 前端
```

打开 http://localhost:5173 进入创作台。

## 总闸（全门禁）

```bash
uv run python scripts/gate.py   # ruff + mypy + pytest + tsc + eslint + build
```

## 文档导航（实现前必读）

| 文档 | 内容 |
|------|------|
| [docs/DESIGN.md](docs/DESIGN.md) | **完整设计规格**（实现者的唯一主文档，覆盖全部设计，必须完整遵循） |
| [docs/AUDIT-V1.md](docs/AUDIT-V1.md) | **设计实现审计报告**（现状快照：哪些实现/哪些缺失/优先级，接手 AI 必读） |
| [docs/PROGRESS.md](docs/PROGRESS.md) | 连续推进台账（各阶段完成情况 + 踩坑记录） |
| [docs/UPGRADE-DISCUSSION.md](docs/UPGRADE-DISCUSSION.md) | 讨论纪要与推理过程（查证设计意图用） |
| [docs/HANDOFF-L-SERIES.md](docs/HANDOFF-L-SERIES.md) | 与旧仓库 L 系列收尾的边界交接 |

## 当前状态

- **S0~S31 全部完成**（188 tests 全绿，总闸通过）：第一版七阶段 + 全部补缺（知识图谱/token 压缩/能动性/SSE/交互层/流程基建/T7 指标/循环对齐 pi/多线叙事/伏笔 A/B 分级+老龄化）
- **对齐验证**：pi 循环行为对照 7/7 PASS；长书压力测试有界；分支剧本哲学指标（修改率↓/说明书累积/偏好遵从）真实链路通过；哈利波特第一部全量提取（148 实体/107 关系/54 事件/10 伏笔）vs 旧项目对比占优
- **剩余**：httpx2 迁移（等 starlette 原生支持）；前端高级功能 UI 按需后补（伏笔面板/图谱可视化/指标展示）

## 设计一句话

> 一个**机制硬编码、内容自然语言、模型无关**的多包系统：用户在**创作台**（概念卡→方向卡→稿纸）上以**操作式表达**与 AI 协作，AI 靠**多智能体探索**找方向、**说明书对齐**懂用户、**检测网**当第二双眼睛——从种子到作品，摩擦前置且递减。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLite / uv workspace
- 前端：React 19 / TypeScript / Vite / Tailwind 4 / TipTap / Zustand
- 桌面：轻量自研壳（Python WebView）+ PyInstaller

## 仓库结构

```
├── pyproject.toml        # uv workspace 根
├── packages/
│   ├── core/             anyspark-core     内核包（不依赖任何包）
│   ├── explore/          anyspark-explore  探索包
│   ├── align/            anyspark-align    对齐包
│   ├── template/         anyspark-template 模式库包
│   └── desktop/          anyspark-desktop  桌面包
├── frontend/             # React 创作台（npm 单应用）
├── data/                 # 运行时用户数据（.gitignore，不入库）
├── docs/                 # 设计文档
├── tests/
└── scripts/
```

## 纪律

- 禁 `git add -A`，显式路径
- `data/` 不入库
- 依赖 pin + 锁文件
- 对设计的任何偏离/新增，先与主人确认，再更新 `docs/DESIGN.md`
