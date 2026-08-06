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

**对话 CLI（S49）**：`uv run anyspark-chat`——不经过前端/pi，终端里直接对话驱动（流式/工具状态/Ctrl+C 取消/多轮延续）。

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
| [docs/FRONTEND-HANDOFF.md](docs/FRONTEND-HANDOFF.md) | **前端重开交接**（API 全契约/现状盘点/设计意图——前端开发智能体必读） |

## 当前状态

- **S0~S58 全部完成**（pytest 全绿，总闸通过）：第一版七阶段 + 全部补缺 + 实测驱动演进 + 特化路线 P1-P5 + 架构深化（S53-S58）
  - 智能体闭环：探索工具化（S32）/粒度感知（S33）/写作技巧内容化（S43，参考 pi skills）
  - 档位记录集（S35：可增删改/恢复默认/温度入档，与心智模型正交）
  - 超长书五场景（S37-S42）：图谱高频保底注入/批量灌入/理解/续写/批量任务/设定档（正典+提炼）
  - 编辑与连锁（S44-S46）：定点编辑/影响分析/剧情计划（计划→执行）
  - **运行时模型**（S47）：多模型配置注册表 + 思考强度（reasoning_effort）；**V4 系列 1M 上下文**
  - **特化路线 P1-P5（S48 系，主人拍板：小说特化版 pi）**：
    - P1 工作区化：每项目一路径（上传存档/章节 md 权威/卡片）+ 双写 + import 同步
    - P2 领域工具化：图谱/伏笔/计划/设定查证全 agent 可自主调用（写作闭环实证）
    - P3 格式管线：零依赖提取（txt/md/docx/pdf）+ 规则拆章 + 摘要卡 + EPUB 导出携图
    - P4 角色推演：低成本多探索 + 判别选优（复用 pi-multi-agent room_compare 模式）；codex 只读数据环境（真实统计）
    - P5 代码扩展：沙箱 run_code + 扩展工具注册表（工具=数据，人工批准生效）
    - 正文检索实用化：search_chapters（exclude 句级排除/regex/fragment 可调）+ read_context（锚点读段落）
  - **架构深化（S53-S58，主人讨论驱动）**：
    - **心智模型=会话规划器**（S50/S53b）：manual 分类 collab/style/habit——collab→档位+协作约定，style→文风偏好+驱动 skill，habit→习惯块；**不再全量注入写作**
    - **全项目内容化**（S53）：explore 维度 / graph 实体类型 / worldsettings 类别 / mood 维度全部内容载体化+CRUD（数值语义化进模型）
    - **叙事技巧生成器**（S54）：原文提炼 skill 五段式（负面约束+真实案例），A 手动/B 心智联动/C 信号驱动 + 人工确认闸门
    - **C 架构**（S56）：write_chapter 意图模式（intent+references）→ 干净写作调用生成正文（无历史/无工具记录，治累积毒化）；多章实验实证 0 幻觉 vs 累积 3 幻觉
    - **skill 三改进**（S57）：轻量写作标记（与 patch 正交）/ write_file 笔记/ 前缀约定（纯文档）/ target 分流（writing→写作调用，main→主循环，both→两者）
    - **类型 skill 生成器**（S58）：mode=main 生成结构/类型/节奏/组织指导（主循环看）
- **实测验证**：pi 循环行为对照 7/7；长书压力有界；哈利波特/猎手准则颗粒度矩阵（12 版）；猎手准则第一卷 164 章灌入+理解+续写；单元层 benchmark 17/17（S32-S46 回归）；**上下文形态对比（S55）+ 多章毒化实证（S58）**
- **知识分层**：图谱（自动事实+weight）/设定档（作者正典）/说明书（偏好）/写作技巧（skill 式，target 分流）/剧情计划（执行蓝图）
- **剩余**：P6 前端壳（主人说后做）；多模态（图片理解/OCR，未来计划）；B 真自我修复（补丁应用，按需）；心智模型完整化（L2/L3 档位指导、渐进式披露的按需引入）；httpx2 迁移（等 starlette 原生支持）

## 设计一句话

> 一个**机制硬编码、内容自然语言、模型无关**的多包系统：用户以**写作即对话**驱动——智能体自主查图谱、埋伏笔、推进计划、检索正文、推演角色，靠**多智能体探索**找方向、**说明书对齐**懂用户、**检测网**当第二双眼睛——从种子到作品，摩擦前置且递减。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLite / uv workspace
- 前端：React 19 / TypeScript / Vite / Tailwind 4 / TipTap / Zustand
- 桌面：轻量自研壳（Python WebView）+ PyInstaller

## 仓库结构

```
├── pyproject.toml        # uv workspace 根
├── packages/
│   ├── core/             anyspark-core     内核包（不依赖任何包：Agent 循环/工具协议/存储）
│   ├── explore/          anyspark-explore  探索包（意图理解/并行探索/角色推演）
│   ├── align/            anyspark-align    对齐包（说明书/心智规划器/技能/氛围/档位）
│   ├── template/         anyspark-template 模式库包（模板/资料摘要卡/伏笔）
│   ├── graph/            anyspark-graph    知识图谱包（实体/关系/事件存储+抽取+注入）
│   ├── check/            anyspark-check    检测网包（骨架检测/规则编译）
│   ├── app/              anyspark-app      组合根（FastAPI 服务/工具装配/模型适配）
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
