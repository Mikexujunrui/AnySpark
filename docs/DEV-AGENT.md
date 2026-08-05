# DEV-AGENT.md — 智能体接入说明（全量测试通道）

> 目的：让智能体（pi）无需前端即可驱动 AnySpark 做**全量测试与回归**。
> 通道：`pi-anyspark` pi package（已注册 ~/.pi/agent/settings.json）→ 后端 HTTP API。
> 记录：所有链路测试落盘 `data/dev/`（gitignored，不入库）。

## 1. 工具清单（pi 会话内可用）

| 工具 | 作用 | 典型用法 |
|------|------|---------|
| `anyspark_server` | 后端生命周期 | `{action:"start"}` → 健康检查；`{action:"status"}`；`{action:"stop"}` |
| `anyspark_api` | 调任意端点 + 链路记录 | `{path:"/api/chat", body:{message:"..."}, record_label:"chat_flow"}` |
| `anyspark_gate` | 总闸门禁（ruff+mypy+pytest+tsc+eslint+build） | `{}`（数分钟，落盘 data/dev/gate/） |
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

## 3. 推荐测试链路（端到端回归）

1. `anyspark_server` start → status 确认健康
2. **写作闭环**：`POST /api/chat {message:"写第一章…"}` → 拿 `conversation_id` 续聊 → `GET /api/chapters` 验证落盘
3. **图谱自动抽取**（写章后后台异步，**LLM 调用需 15-30s**，查 entities 前先等或轮询）：`GET /api/graph/entities` → `GET /api/graph/context`（注入块）
4. **对齐**：`POST /api/manual {content:"…"}` → chat 验证注入
5. **探索**：`POST /api/explore/intent {seed}` → `POST /api/explore/cards`
6. **检测**：`POST /api/check {text}`（响应含 `graph_evidence` 图谱证据）→ `POST /api/check/rule`
7. **资料**：`POST /api/materials {text}`（摘要卡 + 图谱关联）→ `GET /api/materials`
8. **工作区（S48）**：`POST /api/upload {filename, data_b64}`（原始存档）→ chat 写章 → `find data/workspace/main/章节` 验证 md 落盘 → 人工改 md 后 `POST /api/workspace/import` 同步入库
9. `anyspark_state` 核对产物 → 改动后 `anyspark_gate` 回归

## 4. 已知要点（踩坑）

- **图谱抽取是后台任务**（FastAPI BackgroundTasks）：响应先返回，抽取后置执行，真实 LLM 15-30s——查 `graph/entities` 前必须等
- 后端默认 `127.0.0.1:8000` 无认证，仅本机；`ANYSPARK_BASE` 可覆盖
- 端口被占时：`anyspark_server stop` 按端口 netstat+taskkill /F /T 清理
- 数据在 `data/anyspark.db`（SQLite 单文件），测试可另传 `db_path`
- 测试用临时库更干净；真实链路测试会写真实数据（章节/图谱/说明书）

## 5. 边界

- 前端（创作台）不在本通道覆盖范围；前端回归走 `anyspark_gate`（tsc/eslint/build）
- 冒烟脚本 `scripts/*_smoke.py` 仍可用（直连包级，不走 HTTP）
