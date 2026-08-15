# 火花 AnySpark — 智能小说创作引擎 v4

> 🔥 **V4 全新架构已上线**：写作即对话——你说话，智能体直接写。多智能体探索找方向、知识图谱保一致、检测网当第二双眼睛，从种子到作品，摩擦前置且递减。
>
> 💬 使用问题、功能建议、写作交流，请加 QQ 群 **805461309**（火花使用反馈群），第一时间获取版本信息与答疑。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-61dafb.svg)](https://react.dev/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![CI](https://github.com/Mikexujunrui/AnySpark/actions/workflows/ci.yml/badge.svg)](https://github.com/Mikexujunrui/AnySpark/actions/workflows/ci.yml)

> **每个人心中都有一簇火花，AnySpark 帮你点燃它。**

> ⚠️ **设计哲学：AI 为笔，你为执笔人。** 火花的开发初衷是让 AI 在不脱离人类作家掌控的前提下辅助创作——第一目标是提升写作效率的同时，确保故事**不偏离**你设定的方向。涉及大规模自动操作（批量写作、全书变换等）的特性均为实验功能，请在充分审核每步输出的前提下谨慎使用。人类作家的判断力始终是创作的最后一道闸门。

---

## 为什么选择火花？

| 🗣️ 写作即对话 | 🧠 知识永不冲突 | 🛡️ 长篇不"中毒" |
|:---:|:---:|:---:|
| 你说话，它干活——Agent 自主规划执行多步创作任务，自动查图谱、埋伏笔、推进计划、检索正文，你只需给出方向 | SQLite 知识图谱 + 设定档 + 说明书，角色、世界观、事件严格一致，写几百章也不前后矛盾 | 每次写作只参考你指定的内容，不翻陈年旧账——长篇连写不累积走样（多章实测 **0 幻觉**） |

| 🎨 全流程覆盖 | 🔄 越写越懂你 | 🔌 高度可扩展 |
|:---:|:---:|:---:|
| 从灵感构思 → 大纲规划 → 逐章写作 → 评审修订 → 批量变换，一套工具走完全程 | 从你的原文自动提炼写作技巧，叙事手法、偏好设定随书积累，越写越顺 | 沙箱代码扩展 + 扩展工具注册表（人工批准生效）、自定义评审员、可编排工作流 |

---

## 典型用例

### 📖 长篇网文：从种子到百万字

> *"我有一个世界观雏形，帮我把它变成一部完整的连载小说。"*

1. **灵感探索** — 智能体并行探索，生成多个剧情方向供你选择，选一个继续发散
2. **对话即积累** — 聊天中提到的角色、设定自动沉淀为结构化知识图谱，无需手动整理
3. **剧情计划** — 选定方向后规划分卷、章节、伏笔布局，计划 → 执行闭环
4. **逐章写作** — 每章写作前自动查证当前时空点的设定与事实，杜绝前后矛盾
5. **超长书支持** — 百万字级全书：批量灌入、理解、续写，图谱高频注入保持记忆
6. **越写越顺** — 写作技巧生成器从你的原文提炼手法，自动适配你的创作类型

**适用场景**：网文连载、系列长篇、世界观驱动型小说

### 🎭 同人 / 原著改写：忠实于原作的二次创作

> *"我喜欢《XXX》的前半部，但不满意结局，帮我基于原著重写后半部。"*

1. **一键导入** — 上传 txt / md / docx / pdf，自动识别编码（GBK/UTF-8）、规则拆章、提取知识图谱
2. **正典与事实分层** — 作者设定（正典）与 AI 自动抽取（事实）分开管理，防止 AI 自行发挥
3. **参考书用途隔离** — 默认只学文风不学内容，可逐本切换"学事实"——不同作品互不串味
4. **干净续写** — 写什么、参考什么由你点名，写出来的仍是"你的"故事

**适用场景**：同人创作、结局改写、文风迁移、"如果当初……"假设式创作

### 🎯 精确修改：只改关键不碰其余

> *"这章整体还行，但主角的反应太软弱了——我只需要改她那几个关键场景，别动其他部分。"*

1. **定点编辑** — 告诉智能体改哪里、怎么改，它只动目标段落，其余原文纹丝不动
2. **影响分析** — 改动前自动提示这个修改会波及哪些伏笔、设定、后续剧情
3. **一键回滚** — 改错了整轮回滚（章节 + 图谱派生副作用一起还原），不怕试错

**适用场景**：角色性格微调、对话语气修正、单场景重写、伏笔补入

### 📚 批量灌书 / 长书理解

> *"我有一部三百多万字的旧书，帮我读完它、理解它、接着写。"*

1. **格式管线** — 零依赖提取 txt/md/docx/pdf，GBK/GB18030 编码自动识别（不再乱码），卷标题自动跳过
2. **全书消化** — 批量抽取角色、地点、关系、事件到图谱，进度可视化
3. **理解与续写** — 基于全书知识继续写、问答设定、生成设定档、导出 EPUB（带图）

**适用场景**：旧书续写、全集导入、设定整理、跨卷复盘

### ✨ 灵感起步：从 0 到 1 快速试错

> *"我只有一个模糊的想法，想看看它能长成什么故事。"*

1. **自由对话** — 把火花当作创作伙伴，漫谈你的灵感碎片
2. **剧情卡片推演** — 智能体生成多个可能的剧情走向，可视化卡片供你选择
3. **角色推演** — 低成本多探索 + 择优，推演"这样写会怎样"
4. **随时重来** — 不满意就换方向，低成本快速试错

**适用场景**：新书起航、卡文破局、灵感验证、世界观探索

---

## 功能全景

### 🧠 智能创作核心

| 功能 | 说明 |
|------|------|
| **写作即对话** | Agent 自主循环架构，LLM 自行决定工具调用链与停止时机，无需逐步手动指令 |
| **领域工具化** | 图谱查证 / 埋伏笔 / 推进计划 / 设定查证 / 角色推演 / 正文检索，全部由智能体自主调用 |
| **干净写作架构** | 每次写作只看你指定的参考与设定，不带历史包袱——根治长篇"越写越偏"（多章实验实证 0 幻觉） |
| **技巧自学习** | 从你的原文提炼五段式写作技巧（人工确认后生效），类型化 skill 自动适配创作类型 |
| **心智记忆** | 记住你的写作偏好档位与活跃度，自动决定每轮注入什么上下文——不全量塞给你 |
| **任务级控制** | 后台任务可随时取消；本轮修改可一键回滚（章节 + 图谱副作用一起还原） |
| **会话继承** | 新会话可 fork 自旧会话，带着进程记忆继续写；上下文模式 fresh / auto / continue 可选 |

### 📚 知识体系

| 功能 | 说明 |
|------|------|
| **知识图谱** | 实体 / 关系 / 事件结构化存储 + 全文检索 + 自动抽取，事实带权重 |
| **设定档** | 作者正典（worldsettings），与 AI 自动事实分层，写作时按需注入 |
| **说明书** | 记录你的写作偏好（禁破折号、文风倾向……），跨轮记忆、自动对齐 |
| **写作技巧库** | skill 式内容资产，索引 + 点名注入——你决定这章用哪招 |
| **剧情计划** | 执行蓝图：计划 → 执行闭环，伏笔布局、回收追踪 |
| **正文检索** | 关键词批量检索 / 句级排除 / 正则 / 片段长度可调；锚点读段落，精确取用上下文 |
| **叙事树 + 线进度** | 剧情分叉路径树 + 进度映射，探索分支一目了然 |

### 🎨 创作工作流与扩展

| 功能 | 说明 |
|------|------|
| **工作流引擎** | 顺序 / 分支 / 循环三结构 + 断点恢复 + 失败策略；AI 生成草稿 → 人工确认再落地 |
| **格式管线** | 零依赖提取 txt / md / docx / pdf（GBK/UTF-8 自动识别）+ 规则拆章 + 摘要卡 + **EPUB 导出携图** |
| **角色推演** | 低成本多探索 + 判别选优，推演"这个选择后面会怎样" |
| **代码扩展** | 沙箱运行你的代码 + 扩展工具注册表：工具 = 数据，人工批准后生效 |
| **检测网** | 写后自动质检：系统骨架检测 / AI 味扫描 / 规则编译，第二双眼睛 |
| **拟人化评审团** | YAML 人设评审员，多视角审视你的章节，可自定义人设与关注点 |
| **互动推演** | 扮演角色多轮选择推进，适合剧本 / 跑团 / 分支叙事预演 |

### 🖥️ 前端创作台

React 19 + TypeScript + Vite + Tailwind 4 + TipTap + Zustand 构建：图谱可视化（实体/关系/事件）、流式对话、章节编辑、资料管理、工作流画布、推演面板——所有能力都有界面，也能纯 API 调用。

---

## 架构概览

```
用户（前端创作台 / 对话 CLI）
  │  SSE 流式交互 + REST API
  ▼
FastAPI 后端
  ├── Agent 循环 ───── 写作即对话，工具自主调用
  ├── 领域引擎 ─────── 探索 / 对齐 / 图谱 / 模板 / 工作流 / 检测 / 评审 / 推演 / 书库
  ├── 模型适配 ─────── 多模型注册表（DeepSeek 等 OpenAI 兼容），思考强度可调
  └─ 数据层 ───────── SQLite（图谱/设定/计划/心智）+ 章节文件（每项目独立目录）
```

多包**单向依赖**（内核不依赖任何包）：机制硬编码、内容自然语言、模型无关——换模型不换用法。

---

## 前置要求

| 你需要什么 | 说明 | 如何获取 |
|-----------|------|---------|
| **Python 3.11+** | 后端运行环境 | [python.org](https://www.python.org/downloads/) |
| **Node.js 20+** | 前端构建环境（纯 API 场景可不用） | [nodejs.org](https://nodejs.org/) |
| **uv** | Python 包管理器 | [docs.astral.sh/uv](https://docs.astral.sh/uv/) |
| **DeepSeek API Key** | 调用 AI 大模型 | [dashscope.aliyuncs.com](https://dashscope.aliyuncs.com/) 注册获取（新用户有免费额度） |

> 💡 **无需 GPU / Docker**：知识图谱为嵌入式 SQLite，AI 走云端 API，普通 CPU 笔记本即可流畅运行。

### 硬件建议

| 环境 | 最低配置 | 推荐配置 |
|------|---------|---------|
| 日常创作 | 8GB RAM + 双核 CPU | 16GB RAM + 四核 CPU |
| 批量写作（长书灌入/续写） | 16GB RAM | 32GB RAM |

---

## 快速开始

### 🚀 方式一：正式用户 — 下载 Release 安装包（推荐）

去 [GitHub Releases](https://github.com/Mikexujunrui/AnySpark/releases) 下载 `AnySpark_Windows_x64_<版本>.zip`，解压后**双击 `AnySpark.exe`** 即可使用。

- 无需安装 Python / Node.js——exe 已内置前后端
- 首次启动自动在 exe 同目录创建 `data/` 与 `.env` 模板，填入 DeepSeek API Key 后重启即用
- 所有作品数据保存在 exe 同目录 `data/`，整体拷贝即可迁移

### 🔧 方式二：开发者 — 源码运行

```bat
start.bat
```

或手动：

```bash
# 1. 克隆仓库
git clone https://github.com/Mikexujunrui/AnySpark.git
cd AnySpark

# 2. 配置真实模型（必填 API Key）
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY

# 3. 安装依赖
uv sync

# 4. 启动后端（127.0.0.1:8000）
uv run anyspark-server

# 5. 前端创作台（可选——纯 API 场景可不用）
cd frontend && npm ci && npm run dev   # http://127.0.0.1:5173
```

### 💬 对话 CLI

```bash
uv run anyspark-chat
```

终端里直接对话驱动写作：流式输出 / 工具状态 / Ctrl+C 取消 / 多轮延续。领域工具默认全开。

---

## 配置说明

所有配置通过 `.env` 文件管理，详见 [.env.example](.env.example)：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | LLM API 密钥 | *必填* |
| `DEEPSEEK_BASE_URL` | API 地址（OpenAI 兼容） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DEEPSEEK_MODEL` | 模型名 | `deepseek-v4-flash` |
| `DEEPSEEK_CONTEXT_WINDOW` | 上下文窗口（驱动 token 预算） | `1000000`（V4 原生 1M） |

> 启动后可在前端「模型选择器」或 API 运行时增删改 / 切换模型供应商与思考强度，无需改 `.env` 重启。

---

## 常见问题

<details>
<summary><b>需要 GPU 吗？</b></summary>

不需要。火花调用云端 DeepSeek API，本地只运行后端任务调度与前端界面，普通 CPU 笔记本即可。
</details>

<details>
<summary><b>端口被占用怎么办？</b></summary>

默认端口：前端 5173、后端 8000。先运行 `kill_port.bat 8000` / `kill_port.bat 5173` 清理残留进程；仍冲突则改启动参数。
</details>

<details>
<summary><b>如何更新到最新版本？</b></summary>

```bash
git pull
uv sync          # 更新后端依赖
cd frontend && npm ci && cd ..   # 更新前端依赖
```
</details>

<details>
<summary><b>如何备份数据？</b></summary>

```bash
# 备份整个 data 目录即可（小说/章节/图谱/设定全在其中）
cp -r data/ data_backup_$(date +%Y%m%d)/
```
</details>

<details>
<summary><b>启动失败怎么办？</b></summary>

常见原因：① `DEEPSEEK_API_KEY` 未填或无效 → 检查 `.env`；② 端口冲突 → 清理残留进程；③ 依赖缺失 → 重跑 `uv sync`。仍无法解决请加群反馈。
</details>

---

## 项目结构

```
├── pyproject.toml        # uv workspace 根
├── frontend/             # 前端创作台（React 19 + TS + Vite）
├── packages/             # 后端 12 个领域包（单向依赖）
│   ├── core/             内核：Agent 循环 / 工具协议 / 存储（不依赖任何包）
│   ├── explore/          探索：意图理解 / 并行探索 / 角色推演
│   ├── align/            对齐：说明书 / 心智规划 / 技能 / 档位
│   ├── template/         模板：模式库 / 摘要卡 / 伏笔
│   ├── graph/            图谱：实体 / 关系 / 事件 + 全文检索 + 自动抽取
│   ├── check/            检测：骨架检测 / 规则编译
│   ├── workflow/         工作流：顺序 / 分支 / 循环 + 断点恢复
│   ├── review/           评审：拟人化评审团
│   ├── play/             推演：互动角色扮演
│   ├── library/          书库：参考书池 + 用途隔离
│   ├── app/              组合根：FastAPI 服务 / 模型适配 / 工具装配
│   └── desktop/          桌面壳（打包）
├── data/                 # 运行时用户数据（.gitignore，不入库）
├── tests/                # 测试套件（各包内）
├── scripts/              # 门禁 + 冒烟脚本
└── .github/workflows/    # CI（ruff + mypy + pytest + tsc + eslint + build）
```

---

## 开发

```bash
# 总闸（全门禁）：ruff + mypy + pytest + tsc + eslint + build
# 自动按改动面分层，只跑相关检查；锁文件/打包脚本等敏感改动强制全量
uv run python scripts/gate.py

# 分层覆盖
uv run python scripts/gate.py --python      # 只跑 Python 层
uv run python scripts/gate.py --frontend    # 只跑前端层
uv run python scripts/gate.py --all         # 强制全量

# 直接跑测试
uv run pytest
cd frontend && npm run typecheck && npm run lint
```

---

## 打包发布（维护者）

```bash
# exe 发布包（正式用户用）：构建前端 → PyInstaller → 组装 zip
bash scripts/build_release.sh            # 默认 v4.0.0
bash scripts/build_release.sh v4.1.0     # 指定版本
# 产物：<仓库上级>/AnySparkV4-发布-exe/AnySpark_Windows_x64_<版本>.zip

# 源码分发目录（群内测/预览）：完整前后端源码 + 一键启动
uv run python scripts/package_release.py
```

> Release 页面只挂 exe 发布包（正式用户双击即用）；源码即本仓库，无需单独发布源码包。

---

## 数据与安全

火花采用**代码与数据严格分离**的设计：

- 所有用户数据（章节 / 图谱 / 设定 / 计划 / 会话）保存在运行时 `data/` 目录，已被 `.gitignore` 完全排除
- 章节以 markdown 为权威存储（每项目独立目录），图谱 / 卡片双写同步
- 源码模式：用户数据位于仓库 `data/`
- **备份**：复制整个 `data/` 目录即可

---

## 反馈与社区

💬 **QQ 群：805461309（火花使用反馈群）** — 见页面顶部，扫码或搜索群号加入。

🤝 **商业合作**：如有意合作开发企业版或定制方案，欢迎邮件联系 [mikexujunrui@mail.ustc.edu.cn](mailto:mikexujunrui@mail.ustc.edu.cn)。

---

## 许可证

本项目采用 **双许可证** (Dual Licensing) 模式：

| 许可证 | 适用场景 |
|--------|---------|
| [AGPL-3.0](LICENSE) | 开源社区使用、个人创作、学术研究 |
| 商业许可证 | 闭源商用、SaaS 服务、企业部署 |

> **对个人写作者**：你可以自由使用、修改、自部署火花进行个人创作，**你写的小说、角色、设定完全归你所有**（AGPL-3.0 附加权限条款明确豁免创作内容）。
>
> **对商业使用**：如需将火花或其修改版本闭源商用（如 SaaS 服务），请联系版权持有者获取商业许可证。
>
> 🤝 **商业合作**：邮件联系 [mikexujunrui@mail.ustc.edu.cn](mailto:mikexujunrui@mail.ustc.edu.cn)
>
> 所有贡献（含代码/文档）的版权依据 [CLA.md](CLA.md) 转让归版权持有者所有。
>
> Copyright © 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.
