# AnySpark v4

> **每个人心中都有一簇火花，AnySpark 帮你点燃它。**

AnySpark 是一个 AI 小说创作引擎。**最终目的：AI 写小说。**

v4 是一次**二次项目**——绿地独立建设，不复用旧代码（旧系统只作思想参考），**不做旧数据导入/转移，绿地空库起步**（主人 2026-08-02 决策A，旧系统仅作思想参考）。核心理念：**写作即对话**——用户说话，智能体直接写；智能体的第一能力不是守规矩，而是**懂你**。

本仓库为 **AnySpark v4 后端**（Python）。前端已独立（由他人基于后端 HTTP API 开发新创作台），本仓库不含前端代码。

## 快速开始（开发环境）

```bash
# 1. 配置真实模型（复制 .env.example 为 .env，填入 DeepSeek key）
cp .env.example .env

# 2. 安装依赖 + 启动后端（8000）
uv sync && uv run anyspark-server
```

**对话 CLI（S49）**：`uv run anyspark-chat`——终端里直接对话驱动（流式/工具状态/Ctrl+C 取消/多轮延续）。领域工具默认全开（图谱查证/伏笔/计划/设定/推演/检索/skill_lookup）。

## 总闸（全门禁）

```bash
uv run python scripts/gate.py   # ruff + mypy + pytest + tsc + eslint + build
```

## 文档导航（实现前必读）

| 文档 | 内容 |
|------|------|
| [docs/DESIGN.md](docs/DESIGN.md) | **完整设计规格**（实现者的唯一主文档，覆盖全部设计，必须完整遵循；§12 为演进补记 S32-S63） |
| [docs/AUDIT-V1.md](docs/AUDIT-V1.md) | **设计实现审计报告**（现状快照：哪些实现/哪些缺失/优先级，接手 AI 必读） |
| [docs/PROGRESS.md](docs/PROGRESS.md) | 连续推进台账（各阶段完成情况 + 踩坑记录，最新到 S63） |
| [docs/UPGRADE-DISCUSSION.md](docs/UPGRADE-DISCUSSION.md) | 讨论纪要与推理过程（查证设计意图用） |
| [docs/HANDOFF-L-SERIES.md](docs/HANDOFF-L-SERIES.md) | 与旧仓库 L 系列收尾的边界交接 |
| [docs/FRONTEND-HANDOFF.md](docs/FRONTEND-HANDOFF.md) | **前端开发交接**（API 全契约/现状盘点/设计意图——前端开发智能体必读） |
| [docs/EXTENDING.md](docs/EXTENDING.md) | **贡献者指南**（如何加能力：数据工具/独立包/改核心，含 workflow 模板） |

## 当前状态

- **S0~S63 全部完成**（pytest 346 全绿，总闸通过）：第一版七阶段 + 全部补缺 + 实测驱动演进 + 特化路线 P1-P5 + 架构深化（S53-S63）
  - 智能体闭环：探索工具化（S32）/写作技巧内容化（S43，参考 pi skills）
  - 档位记录集（S35：可增删改/恢复默认/温度入档）+ **心智档位 L2/L3**（S61：AI 建议档位/自然语言生成档位，人工确认闸门）+ 活跃度衰减 + context 动态选取
  - 超长书五场景（S37-S42）：图谱高频保底注入/批量灌入/理解/续写/批量任务/设定档（正典+提炼）
  - 编辑与连锁（S44-S46）：定点编辑/影响分析/剧情计划（计划→执行）
  - **运行时模型**（S47）：多模型配置注册表 + 思考强度；**V4 系列 1M 上下文**
  - **特化路线 P1-P5（S48 系，主人拍板：小说特化版 pi）**：
    - P1 工作区化：每项目一路径（上传存档/章节 md 权威/卡片）+ 双写 + import 同步
    - P2 领域工具化：图谱/伏笔/计划/设定查证全 agent 可自主调用（写作闭环实证）
    - P3 格式管线：零依赖提取（txt/md/docx/pdf）+ 规则拆章 + 摘要卡 + EPUB 导出携图
    - P4 角色推演：低成本多探索 + 判别选优；codex 只读数据环境（真实统计）
    - P5 代码扩展：沙箱 run_code + 扩展工具注册表（工具=数据，人工批准生效）
    - 正文检索实用化：search_chapters（词表批量/句级排除/regex/fragment 可调）+ read_context（锚点读段落）
  - **架构深化（S53-S63，主人讨论驱动）**：
    - **心智模型=会话规划器**（S50/S53b）：manual 分类 collab/style/habit——不再全量注入写作
    - **全项目内容化**（S53）：explore 维度 / graph 实体类型 / worldsettings 类别 内容载体化+CRUD
    - **叙事技巧生成器**（S54）：原文提炼 skill 五段式 + 人工确认闸门；**类型 skill 生成器**（S58，mode=main）
    - **C 架构**（S56）：write_chapter 意图模式（intent+references）→ 干净写作调用（无历史/无工具记录，治累积毒化）；多章实验实证 0 幻觉 vs 累积 3 幻觉
    - **skill 三改进**（S57）：轻量写作/笔记约定/target 分流
    - **S59 工作流扩展包**（S59，新增 packages/workflow）：顺序/分支/循环三结构 + 断点恢复 + 失败策略 + AI 生成（草稿→人工确认）；模板与书解耦可迁移
    - **叙事树 + 线进度**（S59）：分叉路径树 + 线进度映射锚——探索=树的生长器
    - **会话继承 fork**（S58c）：parent 链条 + continue 注入进程记忆
    - **项目智能体简介 + context_mode**（S58）：每项目总览常驻 + fresh/auto/continue 上下文模式；图谱停止常驻注入改按需查询
    - **心智模型完善**（S61）：档位 L2/L3 + 活跃度衰减 + context 动态选取
    - **哲学审查修复**（S62）：去垃圾补丁（正则猜内容改 LLM 判断等）
    - **S60 skill 注入瘦身**（S60/S61）：主循环只注入全部技巧索引（名字+描述）+ `skill_lookup` 按需细看 + `write_chapter` 的 `skills` 点名参数——写作调用不自行选技巧，所有注入由主循环点名决定
    - **画蛇添足清理**（S63）：死代码 mood 删除 + role_play 双通道收敛 `load_role_card` + check_text 工具退役
- **实测验证**：pi 循环行为对照 7/7；长书压力有界；哈利波特/猎手准则颗粒度矩阵；猎手准则第一卷 164 章灌入+理解+续写；单元层 benchmark 17/17 回归；**上下文形态对比（S55）+ 多章毒化实证（S58）**；工作流真实链路（AI 生成→审读发现设定冲突→改写→3 轮复检→确认）
- **知识分层**：图谱（自动事实+weight）/设定档（作者正典）/说明书（偏好）/写作技巧（skill 式，索引+点名注入）/剧情计划（执行蓝图）/心智（会话规划器）
- **剩余**：多模态（图片理解/OCR，未来计划）；B 真自我修复（补丁应用，按需）；httpx2 迁移（等 starlette 原生支持）；新前端创作台（他人基于后端 API 开发）

## 设计一句话

> 一个**机制硬编码、内容自然语言、模型无关**的多包系统：用户以**写作即对话**驱动——智能体自主查图谱、埋伏笔、推进计划、检索正文、推演角色，靠**多智能体探索**找方向、**说明书对齐**懂用户、**检测网**当第二双眼睛——从种子到作品，摩擦前置且递减。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLite / uv workspace
- 前端（独立仓库，他人开发）：React 19 / TypeScript / Vite / Tailwind 4 / TipTap / Zustand

## 仓库结构

```
├── pyproject.toml        # uv workspace 根
├── packages/
│   ├── core/             anyspark-core     内核包（不依赖任何包：Agent 循环/工具协议/存储）
│   ├── explore/          anyspark-explore  探索包（意图理解/并行探索/角色推演）
│   ├── align/            anyspark-align    对齐包（说明书/心智规划器/技能/档位）
│   ├── template/         anyspark-template 模式库包（模板/资料摘要卡/伏笔）
│   ├── graph/            anyspark-graph    知识图谱包（实体/关系/事件存储+抽取+注入）
│   ├── check/            anyspark-check    检测网包（骨架检测/规则编译）
│   ├── workflow/         anyspark-workflow 工作流扩展包（S59：顺序/分支/循环+断点恢复）
│   ├── app/              anyspark-app      组合根（FastAPI 服务/工具装配/模型适配）
│   └── desktop/          anyspark-desktop  桌面包
├── data/                 # 运行时用户数据（.gitignore，不入库）
├── docs/                 # 设计文档（DESIGN/PROGRESS/AUDIT/FRONTEND-HANDOFF）
├── benchmarks/           # 基准测试（代码/报告入库，产物不入库）
├── tests/
└── scripts/              # 门禁 + 冒烟脚本
```

## 纪律

- 禁 `git add -A`，显式路径
- `data/` 不入库
- 依赖 pin + 锁文件
- 对设计的任何偏离/新增，先与主人确认，再更新 `docs/DESIGN.md`
