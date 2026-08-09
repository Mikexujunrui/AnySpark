# DEV-AGENT.md — 智能体接入说明（全量测试通道）

> 目的：让智能体（pi）无需前端即可驱动 AnySpark 做**全量测试与回归**。
> 通道：`pi-anyspark` pi package（已注册 ~/.pi/agent/settings.json）→ 后端 HTTP API。
> 记录：所有链路测试落盘 `data/dev/`（gitignored，不入库）。

## 1. 工具清单（pi 会话内可用）

| 工具 | 作用 | 典型用法 |
|------|------|---------|
| `anyspark_server` | 后端生命周期 | `{action:"start"}` → 健康检查；`{action:"status"}`；`{action:"stop"}` |
| `anyspark_api` | 调任意端点 + 链路记录 | `{path:"/api/chat", body:{message:"..."}, record_label:"chat_flow"}` |
| `anyspark_gate` | 总闸门禁（ruff+mypy+pytest；前端 tsc/eslint/build 仅当 frontend/ 存在） | `{}`（数分钟，落盘 data/dev/gate/） |
| `anyspark_state` | 系统状态快照 | `{}`（章节/图谱/说明书/资料统计） |

工具源码：`E:\Desktop\pi\pi-main\packages\pi-anyspark\`（含 README）。

## 2. 记录基础设施（data/dev/）

```
data/dev/
├── runs/<时间戳>_<标签>/  每次 API 链路测试：request.json / response.json / summary.md
├── gate/<时间戳>.txt      总闸历史（last.txt 指最新）
├── state/<时间戳>.json    状态快照
└── server.pid             后端进程 pid
```

- `anyspark_api` 默认 record=true；`record_label` 自定义标签
- 后端运行时日志另有 `data/logs/anyspark.log`（RotatingFileHandler）

## 3. 工作区结构（S48：每项目一路径）

```
data/workspace/main/          # 项目 = book_id（默认 main）
├── 上传/                     # 原始存档（任何格式，只读不碰，不复制不转换）
├── 章节/                     # md 正文（权威）：001-第一章-雨夜.md（文件名承载序号）
├── 卡片/                     # 可读产物：角色卡-陈渡.md、摘要卡-xxx.md
└── (anyspark.db 在 data/ 全局单库，book_id 区分项目)
```

- **章节双写**：write_chapter 写 md 文件（权威）+ SQLite 镜像（图谱抽取/检测/伏笔等既有管线读镜像，零改动）
- 人工编辑 md 后 → `POST /api/workspace/import` 同步入库（内容变化才记版本历史）
- 上传用 `POST /api/upload`（base64 JSON，零新依赖；原始文件原地存档）

## 4. Agent 工具集（enable_* 开关）

写作 Agent 每请求装配（`_make_agent`），按需开关：

| 开关 | 默认 | 工具 |
|------|------|------|
| （常驻） | — | list_chapters / read_chapter / write_chapter / patch_chapter / read_file / write_file / explore_direction |
| `enable_domain` | **开** | graph_query（图谱查证）/ plot_register / plot_list（伏笔）/ plan_list / plan_mark_done（计划）/ read_setting（设定）/ role_play（角色推演）/ search_chapters（正文检索）/ read_context（上下文段落）/ ingest_document（上传消化）/ register_tool（登记扩展工具） |
| `enable_extras` | 关 | read_material（资料摘要卡）/ check_text（检测网自查） |
| `enable_search` | 关 | search_web（网络考据） |
| `enable_codex` | 关 | run_code（沙箱 Python 执行） |
| （扩展工具） | active 才注入 | 用户批准过的扩展工具（见 §6） |

ChatRequest 其他字段：`model_id`/`thinking`（S47 模型选择）、`mood`（氛围滑块）、`agency_level`（档位）、`skip_inject`（跳过 manual/graph/agency/bias/plot/mood/settings/skills/plan 任意子集）、`extract_graph`。

## 5. 推荐测试链路（端到端回归）

1. `anyspark_server` start → status 确认健康
2. **写作闭环**：`POST /api/chat {message:"写第一章…"}` → 拿 `conversation_id` 续聊 → `GET /api/chapters` 验证落盘
3. **图谱自动抽取**（写章后后台异步，**LLM 调用需 15-30s**，查 entities 前先等或轮询）：`GET /api/graph/entities` → `GET /api/graph/context`（注入块）
4. **对齐**：`POST /api/manual {content:"…"}` → chat 验证注入
5. **探索**：`POST /api/explore/intent {seed}` → `POST /api/explore/cards`
6. **检测**：`POST /api/check {text}`（响应含 `graph_evidence` 图谱证据）→ `POST /api/check/rule`
7. **资料**：`POST /api/materials {text}`（摘要卡 + 图谱关联）→ `GET /api/materials`
8. **模型配置（S47）**：`GET /api/models` → `POST /api/models {name, model}` 新增 → `POST /api/models/{id}/activate` 切换（health 跟随）→ chat 带 `model_id`/`thinking`
9. **工作区（S48）**：`POST /api/upload {filename, data_b64}` → chat 写章 → `find data/workspace/main/章节` 验证 md 落盘 → 人工改 md 后 `POST /api/workspace/import`
10. **消化管线（S48c）**：上传 docx/txt → `POST /api/ingest {filename}`（多章→章节 md / 短文本→摘要卡）→ `GET /api/export/book?format=epub`（EPUB 携 md 引用图片）
11. **角色推演（S48e）**：`POST /api/role/card {name, content}` → `POST /api/role/play {role, scenario}`（4 路并行 + 判别选优）
12. **正文检索（S48g/h）**：chat 让 agent 用 `search_chapters`（关键词/exclude/fragment/regex）→ `read_context`（锚点看段落）
13. **codex（S48d/f）**：`POST /api/codex/run {code}`（沙箱 + ws_* 只读数据环境：ws_chapters/ws_entities/ws_read…）
14. **扩展工具（S48g）**：`POST /api/tools/register {name, code}`（draft）→ `POST /api/tools/{id}/approve`（人工批准）→ chat 验证注入 → disable/delete
15. `anyspark_state` 核对产物 → 改动后 `anyspark_gate` 回归
16. **心智=会话规划器（S53b）**：`POST /api/manual {content:"喜欢白话文风", category:"style"}` + `{content:"先给方案再动笔", category:"collab"}` → chat 验证：心智指导块（文风偏好/习惯）+ 协作约定注入，档位随 collab 推断
17. **skill 生成（S54）**：`POST /api/skills/generate {source_text:"…原文…"}`（mode 默认 writing）→ 候选（负面约束+真实案例）→ `POST /api/skills` 人工确认入库 → chat 写作验证注入；`mode:"main"` 产类型/结构指导（S58）
18. **意图模式写作（S56 C 架构）**：chat 让 agent 用 `write_chapter {title, intent, references}` → 验证干净写作调用（正文生成+落盘）；直写=轻量写作（兜底）
19. **内容化 API（S53/S57）**：`GET /api/mood/dims`（维度可增删改，数值语义化）→ `GET /api/explore/dims` → `GET /api/graph/types` → `GET /api/settings/categories` → `GET /api/skills/drafts`（草稿闸门）→ `POST /api/skills/drafts/{id}/promote`
20. **笔记约定（S57）**：chat 让 agent `write_file {path:"笔记/灵感.md", content}` → 验证落 `data/sandbox/笔记/` 且不触发图谱/学习审查

## 6. 扩展工具注册表（S48g，人工批准）

- 工具=数据（SQLite `tools_extensions`）：name/description/params/code（Python `def run(args: dict) -> str`）
- 生命周期：draft（不生效）→ **approve 人工批准** → active（注入工具集，无需重启）
- 执行**仍在沙箱**（复用 codex：白名单 + ws_* 数据环境 + 超时 20s）——双保险
- 不做全自动：工具进工具集后模型每轮可见，错误代码污染主链路（S32 实证）

## 7. 已知要点（踩坑）

- **图谱抽取是后台任务**（独立 worker 线程）：响应先返回，抽取后置执行，真实 LLM 15-30s——查 `graph/entities` 前必须等或轮询
- **模型默认开思考**（deepseek-v4 系列）：`thinking` 可 off/low/medium/high/xhigh/max（S47）；reasoning_effort 是标准参数顶层直传，off 走 extra_body enable_thinking=False
- **token 预算窗口按启动时激活模型计算**：切到不同窗口模型需重启生效（activate 时日志提示）
- **沙箱 codex 不能读写文件/网络**：数据只能经 ws_* 只读函数（工作区/图谱快照）；ws_read 限项目内 200KB
- **heredoc 转义坑**：bash heredoc 写 Python 代码时 `\n` 会变真实换行（语法错误）——用 edit 工具或文件写入
- 后端默认 `127.0.0.1:8000` 无认证，仅本机；`ANYSPARK_BASE` 可覆盖
- 端口被占时：`anyspark_server stop` 按端口 netstat+taskkill /F /T 清理
- 数据在 `data/anyspark.db`（SQLite 单文件），测试可另传 `db_path`；测试用临时库更干净

## 8. 对话 CLI（S49）

```bash
uv run anyspark-chat                 # 交互式 REPL（连 127.0.0.1:8000）
uv run anyspark-chat -m "写第一章"   # 单条消息（非交互）
uv run anyspark-chat --reset         # 清会话
```

- 流式输出（SSE 打字机）+ 工具执行状态（✓/✗）+ Ctrl+C 取消当前轮（可续"继续"）
- conversation_id 延续多轮（存 ~/.anyspark_cli.json）；/quit /reset /tools 命令
- 默认 enable_domain=True（领域工具全开）；--base 覆盖后端地址
- 独立入口（不经过 pi/前端）——真实使用会撞出真实 bug，是修复闭环的最佳素材

## 9. 边界

- 前端（创作台）不在本通道覆盖范围；前端回归走 `anyspark_gate`（tsc/eslint/build）
- 冒烟脚本 `scripts/*_smoke.py` 仍可用（直连包级，不走 HTTP）
- 多模态（图片理解/OCR）明确未做，放未来计划；图片只支持上传存档 + md 引用 + EPUB 导出携带
