# 火花 AnySpark — 智能小说创作引擎 v3.0.0

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](../LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![CI](https://github.com/Mikexujunrui/AnySpark/actions/workflows/ci.yml/badge.svg)](https://github.com/Mikexujunrui/AnySpark/actions/workflows/ci.yml)

> **每个人心中都有一簇火花，AnySpark 帮你点燃它。** 火花是一个基于 LLM 自主循环架构的全流程 AI 叙事创作平台——不止是写作助手，更是你的故事引擎。

> ⚠️ **设计哲学：AI 为笔，你为执笔人。** 火花的开发初衷是让 AI 在不脱离人类作家掌控的前提下辅助创作——第一目标是提升写作效率的同时，确保故事**不偏离**你设定的方向。Autopilot、全书变换、批量改写等涉及大规模自动操作的特性目前均为**实验功能**，请在充分审核每步输出的前提下谨慎使用。人类作家的判断力始终是创作的最后一道闸门。

> 🌐 **在线体验**：[www.anyspark.xyz](https://www.anyspark.xyz) — 无需部署，即刻体验火花。⚠️ 体验站同时在线人数和最大用户数有限，如需稳定使用建议自部署。

> 💬 **QQ 群：805461309（火花使用反馈群）** — Bug 反馈、功能建议、写作交流，扫码或搜索群号加入。

---

## 为什么选择火花？

| 🧠 自主决策 | 🎯 知识约束 | 🔄 持久运行 |
|:---:|:---:|:---:|
| Agent 自主规划执行多步创作任务，你只需给出方向，它来完成全流程 | SQLite 知识图谱确保角色、世界观、事件严格一致，告别前后矛盾 | Autopilot 引擎支持后台持久任务，一句话指令即可驱动整本书的批量创作 |

| 🎨 全流程覆盖 | 🛡️ 工程级可靠 | 🔌 高度可扩展 |
|:---:|:---:|:---:|
| 从灵感构思 → 大纲规划 → 章节写作 → 评审修订 → 全书变换，一套工具走完全程 | 轮次/Token 双重预算、确定性终态出口、Doom Loop 防护、Book 级写锁、指数退避重试——生产级 Agent 基础设施 | 插件系统、技能 YAML、文风 Profiles、自定义评审员——所有创作范式均可定制 |

---

## 典型用例

### 📖 长篇网文：从大纲到百万字

> *"我有一个世界观雏形，帮我把它变成一部完整的连载小说。"*

1. **灵感发散** — 告诉火花你的核心设定，Agent 生成多个剧情方向供你选择
2. **大纲搭建** — 选定方向后，火花自动规划分卷结构、章节大纲、伏笔布局
3. **角色体系** — 自动抽取并管理角色档案，知识图谱确保人物关系始终一致
4. **逐章写作** — 每章写作前自动检索当前时空点的所有已知事实，杜绝前后矛盾
5. **评审迭代** — 14 位评审员多维度审视每章质量，不满意随时调方向
6. **持久推进** — 开启 Autopilot，火花在后台自主完成多章写作，你只需审核结果

**适用场景**：网文连载、系列长篇、世界观驱动型小说

---

### 🎭 同人文 / 原著改写：忠实于原作的二次创作

> *"我喜欢《XXX》的前半部，但不满意结局，帮我基于原著重写后半部。"*

1. **导入原著** — 上传原作文档，火花自动提取知识图谱（角色、事件、时间线）
2. **注入上下文** — 写作时原著对应章节完整注入 Prompt，确保角色语气和世界细节精准还原
3. **拆书分析** — 提取原著的文风特征、叙事节奏、情节节拍
4. **段落级对齐改写** — 基于 diff-patch 技术，精准替换目标段落而不误伤原文其他部分
5. **情节对比** — 改写完成后自动对比原文与改写版的剧情走向差异

**适用场景**：同人创作、结局改写、文风迁移、"如果当初……"假设式创作

---

### 🎯 精确修改：剧情链节点编辑，只改关键不碰其余

> *"这章整体还行，但主角的反应太软弱了——我只需要改她那几个关键场景，别动其他部分。"*

传统 AI 改写常犯的毛病：你让它润色一段对话，它把整章重写了一遍，角色性格走样、伏笔被删、文风跑偏。火花的剧情链编辑彻底解决了这个问题：

1. **自动拆解为剧情链** — AI 将整章拆解为结构化节点（场景地点、出场人物、情节节拍、关键对话、情绪弧线），每个节点附带原文锚点（`source_text`）
2. **三模式选择** — 对每个节点独立指定编辑策略：`keep`（原样保留）/ `tweak`（微调特定处）/ `rewrite`（大幅改写）
3. **段落级精准替换** — 基于 segment_id + confirm 双重锚定 + diff-patch 技术，只替换目标段落，不误伤任何原文
4. **原文锚点防幻觉** — 改写时原文锚点注入 Prompt，LLM 参照真实原文而非凭空编造
5. **逐节点审核** — 每个节点的改动结果独立呈现，改错了只回滚那一个节点

> 💡 **核心优势**：只改你想改的，其余原文纹丝不动。一条 3000 字的章节，可能只改其中 200 字的 3 个节点——而不是推倒重来。

**适用场景**：角色性格微调、对话语气修正、单场景重写、伏笔补入、删改敏感内容

---

### 🔧 全书批量修改：一句话重塑整部作品

> *"把全书中所有'张三'改成'李四'，并把第3-15章的对话风格统一为更冷峻的调子。"*

1. **自然语言指令** — 用日常语言描述你的修改意图
2. **智能分发** — 火花自动判断需要修改哪些章节，串行还是并行执行
3. **批量执行** — 后台逐章应用修改，每章完成后生成 Diff 供你审查
4. **全书套用文风** — `restyle_book` 一键为整本书换上新的叙事风格
5. **全局查找替换** — 支持字面匹配与正则表达式，替换后自动提交版本历史

**适用场景**：角色改名、统一术语、全文润色、风格重铸、大幅修订迭代

---

### ✨ 灵感起步：从0到1快速试错

> *"我只有一个模糊的想法，想看看它能长成什么故事。"*

1. **自由对话** — 把火花当作创作伙伴，漫谈你的灵感碎片
2. **知识自动积累** — 对话中提到的角色、设定自动沉淀为结构化知识
3. **剧情卡片推演** — 火花生成多个可能的剧情走向，选一个继续发散
4. **一键生成大纲** — 满意某条故事线后，让火花自动生成完整章回大纲
5. **随时重来** — 不满意就换方向，低成本快速试错

**适用场景**：新书起航、卡文破局、灵感验证、世界观探索

---

### 🎮 互动故事：读者驱动的分支叙事

> *"我想写一部让读者选择走向的互动小说。"*

1. **图谱设定** — 定义角色、场景、事件节点及其分支关系
2. **开局配置** — 设定起始章节、初始场景、可选角色
3. **自动叙事** — LLM 根据当前图节点生成叙事段落
4. **分支选择** — 每个关键节点生成多个选项，读者选择后继续
5. **状态追踪** — 图谱记录玩家的所有选择路径和后果

**适用场景**：互动小说、文字冒险游戏、跑团剧本、视觉小说脚本

---

## 功能全景

### 🧠 智能创作核心

| 功能 | 说明 |
|------|------|
| **Agent 自主循环** | while-true 自主循环架构，LLM 自行决定工具调用链与停止时机，无需逐步手动指令 |
| **Autopilot 自主写作引擎** | 8 种创作意图自动分类 → 动态生成 TaskStep 序列 → 后台持久执行，支持动态 Replan |
| **持久任务引擎** | TaskQueue + TaskRunner + Supervisor 三层架构，Agent 可持久运行数小时完成全书的批量操作 |
| **子 Agent 派生** | 支持 general / extract / plan / write / research 五种子 Agent 类型，独立上下文并行处理 |
| **对话式创作** | 聊天界面 + SSE 流式输出，消息内嵌剧情卡片、评审报告、章节 Diff 等富交互组件 |
| **高保真改写** | 段落级对齐 + diff-patch 精准替换，支持原著同人改写、文风迁移、定向扩写/缩写 |
| **剧情卡片交互** | Agent 生成 3-5 个剧情走向选项，可视化卡片供选择，阻塞等待用户决策后继续 |
| **结构化 Part 系统** | TextPart / ToolCallPart / ReasoningPart / ChapterDiffPart，完整历史持久化，刷新不丢上下文 |
| **草稿/定稿双轨** | 章节 promote/demote 流程，前端状态栏 Badge 标识，支持稳定版与草稿版并行管理 |
| **叙事导演** | 6 维度叙事策略控制（POV / Pacing / RevealDensity / ForeshadowBudget / ChapterArc / ToneGuidance） |
| **叙事逻辑引擎** | 约束检查 + 置信度评分 + 影响传播，写作时自动检测叙事约束违规 |
| **交互式故事系统** | 图谱驱动的分支叙事引擎，支持读者选择驱动剧情走向 |

### 📊 知识体系与可视化

| 功能 | 说明 |
|------|------|
| **SQLite 知识图谱** | 角色、世界观、事件、关系的结构化存储，图查询 + 自动知识抽取 |
| **时间线可视化** | 事件/章节在水平时间轴上的分布，标注伏笔与关键节点 |
| **角色关系图** | D3.js 力导向图展示角色间关系网络，支持交互式探索 |
| **角色热度图** | 角色在各章节的出场频次热力图，辅助把控叙事重心 |
| **世界地图** | Leaflet 地理可视化 + 时间滑块，4D 呈现世界观空间与时间维度 |
| **伏笔追踪看板** | 伏笔 → 回收全链路追踪，悬疑类创作的刚需工具 |
| **全文检索** | SQLite FTS5 搜索引擎，跨章节关键词检索 + 语义搜索 |
| **统计仪表盘** | 字数趋势、章节分布、角色频次等多维度统计面板 |
| **知识百科 (Wiki)** | 类 Wiki 的结构化知识条目查看与编辑界面 |

### 🔍 评审与质量控制

| 功能 | 说明 |
|------|------|
| **评审团系统** | 14 位评审员（10位通用 + 4位续写专项），支持并发/串行评审，YAML 自定义人设 |
| **自定义评审员** | 通过 YAML 人设文件自定义评审员的人格、关注点和评价标准 |
| **质量门控** | 复用评审团轻量评审，章节质量低于阈值自动暂停，确保输出水准 |
| **幻觉安全网** | fake_tool/fake_write 两层 warning-only 检测（不中断执行），符合大厂「结构化验证优先、文本检测兑底」方向 |
| **一致性校验** | 知识冲突自动检测，写作内容与知识库事实严格对齐 |
| **AI味扫描引擎** | 7项纯规则检测（过渡词/模板句式/模糊词/面部微表情/段落同构/句长均匀度/对话标签），零token消耗，写后自动评分 + 反馈闭环 |

### ⚙️ 高级工程特性

| 功能 | 说明 |
|------|------|
| **双模型分拆** | Pro 模型负责创作/规划，Flash 模型负责抽取/校验，兼顾质量与效率 |
| **两阶段上下文压缩** | Prune（裁剪旧 tool output）+ Summarize（LLM 摘要），保护最近 40k tokens |
| **精确 Token 计算** | 基于 tiktoken 的精确 token 统计，替代字符估算避免误判溢出 |
| **Doom Loop 检测** | 同一工具+参数连续调用 3 次自动检测并打断死循环 |
| **轮次/Token 双重预算** | write=100/其他=30 轮硬上限 + 累计 Token 80% 预算（大厂标配双重成本控制） |
| **确定性终态出口** | 每条终止路径均 yield 带原因的 done 事件，finish_reason 透传前端做⚠️差异化展示，消灭「莫名中止/无报告」 |
| **指数退避重试** | 识别 5xx/rate-limit/overloaded，backoff 2s→4s→8s→30s |
| **Book 级写锁** | threading.RLock 保证并行会话写入安全，实测 20 并发零数据丢失 |
| **章节版本控制** | Git 风格 version history / revert / diff，每次编辑自动创建新版本 |
| **联网搜索** | MCP JSON-RPC 2.0 协议，Exa / Parallel 双后端，支持 research 子 Agent 深度调研 |
| **参考书注入** | 多本参考书同步注入写作上下文，支持原著单章完整注入辅助同人创作 |
| **事件总线** | 类型化事件系统，解耦工具执行、知识抽取、章节变更等模块通信 |

### 🎨 创作工作流与扩展

| 功能 | 说明 |
|------|------|
| **工作流引擎** | 15 种步骤类型（read / decompose / annotate / rewrite / ask_user / search / compare_plot / diff / generate_outline 等），上下文自动传递 |
| **技能系统** | YAML 定义复合工作流技能，预装 full_novel_reconstruct / chapter_rewrite / daily_writing 等 7 个技能 |
| **文风系统** | 系统默认 + 用户自定义双源分离，每本书独立活跃风格，支持 CRUD 管理 |
| **插件系统** | Python 钩子插件（on_write / on_extract / modify_system_prompt），支持自定义提取器和写作风格 |
| **交互故事系统** | 图谱驱动的分支叙事引擎，支持读者选择驱动剧情走向 |
| **剧情推演** | 基于已有知识库和大纲，自动推演后续剧情发展 |

### 📦 全书变换工具集

| 工具 | 功能 |
|------|------|
| `apply_directive_globally` | 一条自然语言指令应用于全书所有章节（自动判断串行/并行执行策略） |
| `find_replace_book` | 全书字面/正则查找替换 |
| `transform_chapters_batch` | 批量变换指定章节（支持 patch 精准编辑 / rewrite 全文重写两种模式） |
| `restyle_book` | 全书统一套用指定文风 |
| `summarize_book` | 全书摘要生成，作为长程上下文注入后续创作 |

### 📤 导入导出

| 功能 | 说明 |
|------|------|
| **多格式导出** | txt / docx / markdown 三种格式，支持整本导出或单章导出 |
| **批量导入优化** | 一次加载、一次保存，O(n) 批量写入，支持千章级小说秒级导入 |
| **文档导入** | 支持 txt / docx / md 文件上传解析，自动提取知识与章节结构，10种章节格式正则识别 |

---

## 架构概览

```
用户 (React SPA, port 8190)
  │  SSE 流式交互 + REST API
  ▼
FastAPI Backend (port 8191)
  │
  ├─ Agent 引擎 ─────────────────────────────────────────
  │   ├── Agent Loop (while-true 自主循环, 8 阶段处理器)
  │   ├── Run State (Session 级并发控制 + Cancel 中断)
  │   ├── Sub-Agent 系统 (5 种类型, 独立上下文派生)
  │   ├── Autopilot 引擎 (意图分类 → 步骤生成 → 后台执行)
  │   ├── TaskQueue + Supervisor (持久任务调度与监督)
  │   ├── Retry (指数退避) + Compaction (两阶段压缩)
  │   ├── Doom Loop 检测 + 幻觉安全网 + 轮次/Token 双重预算 + 确定性终态
  │   ├── Book Lock (可重入写锁, 并发安全)
  │   └── System Prompt (分层动态组装)
  │
  ├─ 业务层 ───────────────────────────────────────────
  │   ├── 知识库管理器 (SQLite 图查询 + 知识抽取)
  │   ├── 上下文管理器 (知识检索 → Token 预算 → Prompt 构建)
  │   ├── 工作流引擎 (15 种步骤类型, 上下文自动传递)
  │   ├── 评审团 (14 位评审员, 并发/串行, 质量门控)
  │   ├── AI味扫描引擎 (7项纯规则检测, 零token, 反馈闭环)
  │   ├── 插件管理器 (钩子系统 + 自定义工具)
  │   ├── 技能管理器 (YAML 技能加载, 双源分离)
  │   ├── 文风管理器 (Profiles CRUD, 双源分离)
  │   └── 叙事导演 (6 维度策略控制)
  │
  ├─ 工具层 ───────────────────────────────────────────
  │   ├── 写作工具 (约束写作 / 拆解 / 复写 / 文风分析 / 高保真改写)
  │   ├── 管理工具 (章节管理 / 文档读取 / 知识检索 / 联网搜索)
  │   ├── 评审工具 (评审团评审 / 评审员管理)
  │   ├── 变换工具 (全书指令 / 查找替换 / 批量变换 / 文风套用 / 摘要)
  │   └── Tool Registry (Schema 校验 + 输出截断 + 权限标记)
  │
  └─ 数据层 ───────────────────────────────────────────
      ├── SQLite 嵌入式图存储
      ├── SQLite FTS5 (全文检索)
      ├── JSON 文件 (章节 / 会话 / 大纲 / 任务, 代码与数据分离)
      └── pygit2 (Git 风格版本历史)
```

---

## 前置要求

| 你需要什么 | 说明 | 如何获取 |
|-----------|------|---------|
| **Python 3.11+** | 后端运行环境 | [python.org](https://www.python.org/downloads/) |
| **Node.js 20+** | 前端构建环境 | [nodejs.org](https://nodejs.org/) |
| **DeepSeek API Key** | 用于调用 AI 大模型 | [platform.deepseek.com](https://platform.deepseek.com) 注册后获取（新用户有免费额度） |

> 💡 **无需 Docker**：v3.0 已将知识图谱迁移到嵌入式 SQLite，不再依赖 Neo4j 和 Docker。只需 Python + Node.js 即可运行。

### 硬件建议

| 环境 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 日常创作 | 8GB RAM + 双核 CPU | 16GB RAM + 四核 CPU |
| 批量写作 | 16GB RAM | 32GB RAM |
| 磁盘空间 | 10GB 可用 | 20GB+ SSD |

---

## 快速开始

### 🚀 方式一：一键启动（推荐）

克隆仓库后直接运行启动脚本：

**Windows：**
```powershell
.\start.ps1
```

**Mac / Linux：**
```bash
bash start.sh
```

**Windows（备选）：**
```bat
start.bat
```

脚本会自动启动后端和前端服务，完成后打开浏览器访问 `http://localhost:8190`。

### 🔧 方式二：手动启动

```bash
# 1. 克隆仓库
git clone https://github.com/Mikexujunrui/AnySpark.git
cd AnySpark

# 2. 创建环境变量文件
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY（必填）

# 3. 安装依赖
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. 启动后端
python -u src/server.py

# 5. 启动前端（新终端）
cd frontend
npx vite --port 8190 --host

# 6. 打开 http://localhost:8190
```

---

## 常见问题

<details>
<summary><b>需要 GPU 吗？</b></summary>

不需要。火花调用云端 DeepSeek API 进行 AI 推理，本地只运行前端界面和后端任务调度，普通 CPU 笔记本即可流畅运行。
</details>

<details>
<summary><b>端口被占用怎么办？</b></summary>

默认端口：前端 8190、后端 8191。如果冲突，编辑 `.env` 修改 `SERVER_PORT` 即可。
</details>

<details>
<summary><b>如何更新到最新版本？</b></summary>

```bash
git pull                    # 拉取最新代码
pip install -r requirements.txt  # 更新依赖
cd frontend && npm install && cd ..  # 更新前端依赖
```
你的数据在 `data/` 目录中，更新不会丢失。
</details>

<details>
<summary><b>如何备份数据？</b></summary>

```bash
# 备份整个 data 目录即可
cp -r data/ data_backup_$(date +%Y%m%d)/
cp .env .env.backup
```
</details>

<details>
<summary><b>启动失败怎么办？</b></summary>

```bash
# 常见原因：
# 1. DEEPSEEK_API_KEY 未填写或无效 → 检查 .env 文件
# 2. 端口冲突 → 关闭占用端口的程序，或修改端口映射
# 3. 依赖缺失 → 重新运行 pip install -r requirements.txt
```
</details>

---

## 配置说明

所有配置通过 `.env` 文件管理，详见 [.env.example](.env.example)：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | LLM API 密钥 | *必填* |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | Pro 模型（创作/规划） | `deepseek-v4-pro` |
| `DEEPSEEK_MODEL_FLASH` | Flash 模型（抽取/校验） | `deepseek-v4-flash` |
| `LLM_MODE` | 调度模式：`split` / `pro` / `flash` / `custom` | `split` |
| `SERVER_PORT` | 后端端口 | `8191` |
| `WEBSEARCH_ENABLED` | 启用联网搜索 | `true` |

`LLM_MODE` 策略：

| 模式 | Pro 模型 | Flash 模型 | 适用场景 |
|------|----------|------------|----------|
| `split` | 创作、规划、评审 | 抽取、校验、分类 | **推荐** — 质量与成本的平衡 |
| `pro` | 全部任务 | — | 追求最高质量 |
| `flash` | — | 全部任务 | 快速迭代、低成本试错 |
| `custom` | 按模型名自由组合 | 按模型名自由组合 | 接入其他 OpenAI 兼容 API |

---

## 端口说明

| 服务 | 端口 |
|------|------|
| 前端（Vite） | 8190 |
| 后端 API（FastAPI） | 8191 |

---

## 项目结构

```
├── src/                         # 后端源码
│   ├── server.py                # FastAPI 入口
│   ├── core/                    # 核心引擎 (61 模块, 含 2 子包)
│   │   ├── agent_loop.py        #   Agent 自主循环 (8 阶段处理器)
│   │   ├── autopilot_runner.py  #   Autopilot 自主写作引擎
│   │   ├── autopilot/           #   Autopilot 子包 (配置 + 规划器)
│   │   ├── headless_loop.py     #   无头循环 + TaskRunner
│   │   ├── supervisor.py        #   后台任务监督进程
│   │   ├── task_queue.py        #   持久任务队列
│   │   ├── loop_state.py        #   循环状态 + 漂移/幻觉检测
│   │   ├── system_prompt.py     #   分层动态 System Prompt
│   │   ├── compaction.py        #   两阶段上下文压缩
│   │   ├── knowledge.py         #   知识库管理器
│   │   ├── graph_store.py       #   Neo4j 图存储（已弃用，由 sqlite_store.py 替代）
│   │   ├── graph_search.py      #   图搜索与路径分析
│   │   ├── context_manager.py   #   写作上下文构建
│   │   ├── review_panel.py      #   评审团编排 (14 位评审员)
│   │   ├── ai_flavor_scanner.py  #   AI味扫描引擎 (7项纯规则检测)
│   │   ├── workflow_engine.py   #   工作流引擎 (15 种步骤)
│   │   ├── narrative_logic/     #   叙事逻辑子包 (约束检查/置信度/影响传播)
│   │   ├── interactive_agent.py #   交互式故事引擎
│   │   ├── config.py            #   集中配置管理
│   │   ├── event_bus.py         #   类型化事件总线
│   │   ├── book_locks.py        #   Book 级写锁
│   │   └── ...                  #   更多核心模块
│   ├── routes/                  # 22+ API 路由模块
│   ├── tools/                   # Agent 工具集 (16 文件, 含 impl/ 子包)
│   │   ├── impl/                #   工具实现 (13 文件)
│   │   ├── executor.py          #   工具执行器
│   │   └── chapter_tools.py     #   章节变换工具
│   └── data/                    # 数据层 (stores/ 子包, Git 版本存储)
├── frontend/                    # React 19 + TypeScript 6 + Vite 8
│   └── src/components/          # 68 前端组件 (含 chat/ editor/ panels/ ui/ 子目录)
├── plugins/                     # 插件目录 (Python 钩子)
├── skills/                      # 技能配置 (YAML, 系统默认)
├── styles/                      # 文风模板 (YAML, 系统默认)
├── reviewers/                   # 评审员人设 (YAML, 系统默认)
├── data/                        # 运行时用户数据 (.gitignore)
├── tests/                       # pytest 测试套件 (34 测试文件, 451 用例)
├── scripts/                     # 运维脚本
├── docs/                        # 技术文档
├── .github/workflows/           # CI/CD (ci.yml)
├── start.ps1                     # Windows 一键启动
└── pyproject.toml               # Python 项目配置
```

---

## API 文档

启动后端后访问：

- **Swagger UI**：`http://localhost:8191/docs` — 交互式 API 文档，可直接测试所有接口
- **ReDoc**：`http://localhost:8191/redoc` — 结构化 API 文档

> 所有端点遵循 OpenAPI 3.0 规范，可导入 Postman 等工具。

---

## 开发

```bash
# 后端
python -u src/server.py

# 前端（开发模式，自动代理 API 到后端）
cd frontend && npx vite --port 8190

# 运行全部测试
pytest

# 仅运行核心测试
pytest tests/test_agent_loop.py tests/test_config.py

# 本地 CI 检查
python -m ruff check src/ tests/      # Python lint
python -m mypy src/ --ignore-missing-imports  # 类型检查
npm run build --prefix frontend        # 前端构建
npx eslint . --prefix frontend --max-warnings 90  # 前端 lint
```

---

## 数据与安全

火花采用**代码与数据严格分离**的设计：

```
data/
├── books.json              # 书籍元数据
├── chapters_*.json         # 章节内容（版本化管理）
├── sessions_*.json         # 会话消息（结构化 Part 持久化）
├── worldbuilding_*.json    # 世界观设定
├── timeline_*.json         # 时间线数据
├── outline_*.json          # 大纲数据
├── plot_chain_*.json       # 剧情链数据
├── volumes_*.json          # 分卷数据
├── reviews_*.json          # 评审记录
├── tasks_*.json            # 持久任务数据
├── search_fts.db           # 全文检索索引
├── repos/                  # Git 版本仓库
├── uploads/                # 用户上传的参考文件
├── reviewers/              # 自定义评审员
├── styles/                 # 自定义文风
└── skills/                 # 自定义技能
```

- `data/` 目录已被 `.gitignore` 完全排除
- 项目代码仅包含系统默认配置
- **备份**：定期备份 `data/` 目录 + `.env` 文件即可保存全部私有数据
- **迁移**：部署新版本时保留 `data/` 目录即可无缝迁移

---

## 技术栈速览

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TypeScript 6 + Vite 8 |
| UI | TailwindCSS 4 + Radix UI + Framer Motion 12 |
| 编辑器 | TipTap (ProseMirror) |
| 可视化 | D3.js 7 + Leaflet 1.9 |
| 后端框架 | Python FastAPI + Uvicorn |
| 实时通信 | SSE (sse-starlette) |
| AI 模型 | DeepSeek v4-pro / v4-flash（OpenAI 兼容） |
| Agent 架构 | 自研 while-true 自主循环 |
| 知识图谱 | SQLite (嵌入式图存储) |
| 全文检索 | SQLite FTS5 |
| 版本控制 | pygit2 (libgit2) |
| 容器化 | 无需容器，直接运行 |

> 完整技术栈说明见 [TECH_STACK.md](TECH_STACK.md)

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构设计、分层说明、数据主流向 |
| [MODULES.md](MODULES.md) | 23 个核心模块定义、接口与实现状态 |
| [TECH_STACK.md](TECH_STACK.md) | 完整技术栈与版本 |
| [FRONTEND.md](FRONTEND.md) | 前端开发指南：组件架构、状态管理、SSE 交互模式 |
| [TESTING.md](TESTING.md) | 测试策略：分层说明、运行命令、编写规范 |
| [EXTENDING.md](EXTENDING.md) | 扩展开发：插件、技能、文风、评审员自定义 |
| [ROADMAP.md](ROADMAP.md) | 开发路线图与版本历史 (v1.0 → v3.0) |
| [IMPROVEMENTS.md](IMPROVEMENTS.md) | 改进跟踪 (36/36 项已完成) |
| [CHANGELOG.md](../CHANGELOG.md) | 版本变更日志 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 贡献指南 |

---

## 反馈与社区

💬 **QQ 群：805461309（火花使用反馈群）** — 见页面顶部，扫码或搜索群号加入。

🤝 **商业合作**：如有意合作开发企业版或定制方案，欢迎邮件联系 [mikexujunrui@mail.ustc.edu.cn](mailto:mikexujunrui@mail.ustc.edu.cn)。

---

## 许可证

本项目采用 **双许可证** (Dual Licensing) 模式：

| 许可证 | 适用场景 |
|--------|---------|
| [AGPL-3.0](../LICENSE) | 开源社区使用、个人创作、学术研究 |
| 商业许可证 | 闭源商用、SaaS 服务、企业部署 |

> **对个人写作者**：你可以自由使用、修改、自部署火花进行个人创作，你写的小说、角色、设定完全归你所有。
>
> **对商业使用**：如需将火花或其修改版本闭源商用（如 SaaS 服务），请联系版权持有者获取商业许可证。
>
> 🤝 **商业合作**：邮件联系 [mikexujunrui@mail.ustc.edu.cn](mailto:mikexujunrui@mail.ustc.edu.cn)
>
> Copyright © 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.
