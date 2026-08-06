# FRONTEND-HANDOFF.md — 前端重开交接（给前端开发智能体的完整上下文）

> 创建：2026-08-06（主人决定重开前端，本文件由后端侧智能体准备，节省前端开发时间）
> 状态：**前端设计/交互/美学完全交给前端开发智能体**；本文件只给事实（现状/契约/设计意图），不给方案。
> 纪律：前端开发期间如需后端配合/新增 API，先与主人确认，再更新 `docs/DESIGN.md`。

---

## 〇、一句话定位

**后端已到 S58（成熟稳定），前端只有 S10 水平（阶段1占位）**——重开前端的本质是**功能面补全 + 视觉升级**，不是修 bug。后端能力远超前端可见面，这是"前端太差"的真正含义。

后端关键架构（前端必须适配，详见 PROGRESS S53-S58）：
- **C 架构**（S56）：`write_chapter` 意图模式（intent+references）→ 干净写作调用；直写=轻量写作
- **心智=会话规划器**（S50/S53b）：manual 分类 collab/style/habit
- **skill 体系**（S54/S57/S58）：五段式 + target 分流 + 生成器 + 草稿闸门
- **内容化**（S53）：mood/explore/graph/settings 维度与类别全可增删改

---

## 一、前端现状盘点（2026-08-06）

### 现有结构（35 文件，2268 行）
```
frontend/src/
├── api/           # API 客户端（9 文件）——【建议保留复用】
│   ├── client.ts      # apiFetch<T> 唯一网络出入口（fetch 封装 + ApiError）
│   ├── chat.ts        # /api/chat/stream SSE 流式解析
│   ├── chapters.ts / check.ts / explore.ts / manual.ts / mood.ts / signals.ts / template.ts
├── app/App.tsx    # 应用壳：三层布局（左章节栏+中稿纸+右上下文）+ 3 抽屉
├── components/
│   ├── paper/Paper.tsx       # TipTap 编辑器（稿纸）【建议保留：编辑器集成已跑通】
│   ├── chat/                 # ChapterSidebar / ChatInput / ChatThread
│   ├── context/              # AgencyPicker / MoodSliders / ModelPicker / ExplorePanel / InteractionTools / WritingContext
│   └── drawers/              # ManualPanel / CheckPanel / MaterialsPanel / ToolsDrawer
├── stores/        # zustand（insertBus / useChapterStore / useChatStore / useCheckStore / useExploreStore / useManualStore / useMaterialStore）
└── types/         # chapter.ts / chat.ts
```

### 复用 vs 重写判断（供参考，最终前端智能体定）
| 部分 | 判断 | 理由 |
|---|---|---|
| `api/client.ts` + 各 api/*.ts | **保留** | 封装干净（唯一出入口 + ApiError），重写无收益 |
| `Paper.tsx`（TipTap）| **保留** | 编辑器集成（StarterKit+Placeholder+insertBus 插入总线）已跑通 |
| zustand stores | **保留或重写** | 结构清晰，但可能想换状态管理模式 |
| App.tsx 布局 | **重写** | "阶段1占位"（注释自述），功能面远落后 |
| 各 Panel/Drawer | **重写或扩展** | 后端 S53-S58 新能力前端全没有（skill/推演/类型管理/档位管理）|

### 现有前端已实现的功能面（S10 水平）
- 对话→写作→落盘→稿纸显示 主流程 ✅
- 章节列表/选中/编辑 ✅
- 说明书/审读/资料 三个抽屉 ✅
- 氛围滑块（MoodSliders，已从后端 /api/mood/dims 动态渲染 S57）✅
- 模型选择（ModelPicker）/ 档位选择（AgencyPicker）✅
- insertBus 插入总线（候选卡/渐变条拖入稿纸）✅

### 后端有但前端【没有】的功能面（重开的重点补全对象）
1. **skill 面板**：列表/增删改/target 编辑/生成器（/api/skills/generate，mode writing|main）/草稿确认（/api/skills/drafts）
2. **角色推演**：角色卡 + 推演（/api/role/card + /api/role/play）
3. **内容化管理**：探索维度/图谱类型/设定类别（/api/explore/dims、/api/graph/types、/api/settings/categories）
4. **档位管理**：增删改/恢复默认（/api/agency/add、/api/agency/reset）
5. **模型管理**：增删/切换/API key（/api/models CRUD + activate）
6. **心智条目管理**：分类 collab/style/habit 编辑、锁定（/api/manual 已支持 category）
7. **AI 倾向档案**：bias 查看/增删（/api/bias）
8. **导出**：全书导出 txt/md/epub（/api/export/book）、单章导出
9. **上传/消化**：上传存档 + 拆章/摘要卡（/api/upload + /api/ingest）
10. **批量改写/审读**（/api/batch/*）
11. **影响分析**（/api/impact）
12. **统计面板**（/api/stats）
13. **伏笔/计划面板**：plot 登记/列表、plan 推进（Agent 能调，前端无可视化）

---

## 二、后端 API 全契约（新前端对接依据——免读源码）

> 完整 Pydantic 定义在 `packages/app/src/anyspark/server/app.py`（请求模型）与各端点的 response_model。
> 以下按功能域列出**请求结构**（重点），响应结构标注 response_model。

### 2.1 对话（核心）
| 端点 | 请求 | 说明 |
|---|---|---|
| `POST /api/chat` | `{message, conversation_id?, system_prompt?, temperature?, agency_level?, mood?, enable_search?, enable_extras?, enable_domain?, enable_codex?, extract_graph?, skip_inject?, model_id?, thinking?}` | 非流式；响应 ChatResponse |
| `POST /api/chat/stream` | 同上 | SSE：turn_start/text_delta/tool_call/tool_execution_start/tool_execution_end/tool_result/done/error |
| `POST /api/chat/cancel` | `{conversation_id}` | 中断 |
| `POST /api/chat/steer` | `{conversation_id, message}` | 运行中插话 |
| `POST /api/chat/direction` | `{prompt, context?}` | 方向声明 |
| `POST /api/chat/candidates` | `{prompt, context?, n?}` | 候选卡堆 |
| `POST /api/chat/rewrite` | `{text, mode: subtle\|balanced\|bold}` | 改写渐变条 |

**ChatResponse**：`{conversation_id, text, turns[], events[], agency_declared?}`
**ChatRequest 关键字段**：
- `mood: dict<dim, 0-100>`（维度键来自 /api/mood/dims，后端语义化后注入）
- `agency_level: int`（档位，0-4，缺省用心智规划建议）
- `model_id` / `thinking`（模型选择）
- `skip_inject: ["manual","graph","agency","bias","mood","settings","skills","plan"]`

### 2.2 章节
| 端点 | 请求 | 说明 |
|---|---|---|
| `GET /api/chapters` | — | list[ChapterOut] |
| `GET /api/chapters/{id}` | — | ChapterOut |
| `GET /api/chapters/{id}/export` | `format?` | 单章导出 |
| `POST /api/chapters/{id}/patch` | `{title?, content?, operations?}` | 更新/定点编辑 |
| `POST /api/chapters/{id}/wrapup` | — | 一章收尾（摘要+下章衔接）|

**ChapterOut**：`{id, book_id, title, content, order_index, updated_at}`

### 2.3 心智（S53b）
| 端点 | 请求 | 说明 |
|---|---|---|
| `GET /api/manual` | `scope=project\|global` | list |
| `POST /api/manual` | `{content, confidence?, scope?, category: collab\|style\|habit}` | 新增 |
| `PATCH /api/manual/{id}` | `{content?, locked?, category?}` | 改/锁 |
| `DELETE /api/manual/{id}` | — | 删 |
| `POST /api/signals` | `{kind, content, new_content?, context?}` | 操作信号 |
| `POST /api/mind/reconcile` | `{book_id?}` | 跨会话对账 |
| `GET /api/bias` / `POST /api/bias` / `DELETE /api/bias/{id}` | `{content, source?}` | AI 倾向档案 |

### 2.4 skill（S54/S57/S58）
| 端点 | 请求 | 说明 |
|---|---|---|
| `GET /api/skills` | — | list（含 target）|
| `POST /api/skills` | `{name, description, content, example?, tags?, target: writing\|main\|both, enabled?}` | 新增 |
| `PATCH /api/skills/{id}` | 同上各字段 | 改 |
| `DELETE /api/skills/{id}` | — | 删 |
| `POST /api/skills/generate` | `{source_text, hint?, max_items?, mode: writing\|main}` | 生成候选 |
| `GET /api/skills/drafts` | — | 草稿列表 |
| `POST /api/skills/drafts/{id}/promote` | — | 转正 |
| `DELETE /api/skills/drafts/{id}` | — | 拒绝 |

### 2.5 内容化维度管理（S53/S57）
| 端点 | 说明 |
|---|---|
| `GET/POST/PATCH/DELETE /api/mood/dims` | 氛围维度（key/label/description/example）|
| `GET/POST/PATCH/DELETE /api/explore/dims` | 探索维度（name/enabled）|
| `GET/POST/PATCH/DELETE /api/graph/types` | 图谱实体类型（name/enabled）|
| `GET/POST/PATCH/DELETE /api/settings/categories` | 设定档类别（name/enabled）|

### 2.6 图谱 / 伏笔 / 计划
| 端点 | 说明 |
|---|---|
| `GET /api/graph/entities?q=&entity_type=` / `GET /api/graph/relations` / `GET /api/graph/events` | 图谱查询 |
| `GET /api/graph/context` | 注入块预览 |
| `POST /api/graph/extract` | `{chapter_ref, text}` 手动抽取 |
| `GET/POST /api/plot` + `PATCH /{id}` + `DELETE /{id}` | 伏笔：POST 生成（PlotIn: {settings, priority?}）/ PATCH 更新状态 / 列表 |
| `POST /api/plot/item` | 伏笔登记（PlotItemIn: {content, priority: must\|soft, category?}）|
| `GET/POST /api/plan*` / `PATCH` | 计划 CRUD（ChapterPlanIn: {chapter_order, title?, content?}）|

### 2.7 探索 / 推演 / 检测
| 端点 | 请求 | 说明 |
|---|---|---|
| `POST /api/explore/intent` | `{seed}` | 意图理解 → 概念卡+歧义点 |
| `POST /api/explore/cards` | `{seed, intent_confirmed}` | 方向卡×4 |
| `POST /api/explore/archive` / `GET` | `{card}` | 固化方向 |
| `POST /api/role/card` | `{name, content}` | 角色卡 |
| `POST /api/role/play` | `{role, scenario, n?}` | 推演（4路+选优）|
| `POST /api/check` | `{text, target?, chapter_order?, line?}` | 审读（含图谱证据+时序校验）|
| `POST /api/check/rule` | `{rule, text}` | 自定义规则检测 |

### 2.8 管理 / 配置
| 端点 | 请求 | 说明 |
|---|---|---|
| `GET/POST /api/models` + `DELETE/{id}` + `POST/{id}/activate` | `{name, model, base_url?, api_key?, context_window?, max_tokens?, temperature?, thinking?}` | 模型管理 |
| `GET/POST /api/agency` + `/add` + `/reset` + `PATCH/{id}` + `DELETE/{id}` | AgencyIn: {name?, description?, temperature?} | 档位管理 |
| `GET/POST /api/settings` + `POST /api/settings/extract` | `{content, category?, name?}` | 设定档 |
| `GET/POST /api/materials` + `GET /{id}` | MaterialIn | 资料摘要卡 |
| `POST /api/upload` | `{filename, data_b64}` | 上传存档 |
| `POST /api/ingest` | `{filename, mode: auto\|chapters\|card}` | 消化 |
| `GET /api/export/book` | `format=txt\|md\|epub` | 全书导出 |
| `POST /api/impact` | `{chapter_id?}` | 影响分析 |
| `POST /api/batch/rewrite` | `{chapter_ids, instruction}` | 批量改写 |
| `POST /api/batch/review` | `{chapter_ids}` | 批量审读 |
| `GET /api/stats` | — | 统计 |
| `GET /api/templates` + `POST /api/templates/import` + `DELETE/{name}` | `{name, description, granularity?, position?, function?, params?}` | 模式库 |
| `GET/POST /api/tools` + `PATCH/{id}` + `POST/{id}/approve\|disable` | ToolRegisterIn: {name, description, params_json, code} | 扩展工具 |
| `POST /api/codex/run` | `{code, timeout?}` | 沙箱代码 |

---

## 三、DESIGN 前端设计意图（§机制4/5 摘录，设计依据）

### 机制 5：前端空间设计（创作台）
- 核心：把"并列的控制台"变成"**有主角的创作台**"——稿纸为主角，功能全保留
- 三层空间：
  - 第一层：**稿纸**（视觉主体，TipTap 编辑器）
  - 第二层：**写作上下文**（候选卡/氛围滑块/能动性圆点，轻量浮现）
  - 第三层：**设定工具抽屉**（知识/角色/时间线等，按需呼出，Ctrl+数字快捷键）
- 对话从聊天窗口降为**纸边批注**；视觉收敛（荧光色→1 主色 + 3 语义色；字号层级重建；质感动效）
- 美学暂缓（DESIGN 原话）——但主人决定重开前端，视觉可由前端智能体按自己审美发挥

### 机制 4：低摩擦交互（前端重点）
- 操作即表达：滑块/圆点/渐变条/候选卡——**拖动即语义**，不强制打字
- 候选卡堆（方向声明/候选）：并行差异化生成，用户 0.5s 点选
- 改写渐变条：保原味↔大幅改（后端 /api/chat/rewrite）
- 能动性选择器：AI 声明档位 → 用户点选修正
- 氛围滑块组：紧张/温暖/舒缓/压抑（维度可增删，来自 /api/mood/dims）
- **摩擦前置且递减**：前期花小成本对齐，后期零返工——好交互 = 早期小成本对齐

### 核心循环（DESIGN §T2）
> **概念卡（理解）→ 方向卡（选择）→ 稿纸（产出）**——其余都是变形
> 用户到哪层探索到哪层，不为未写的部分付探索成本

---

## 四、给前端开发智能体的建议流程

1. **读文档**（30 分钟）：本文件 → README → DESIGN §机制4/5 → PROGRESS S53-S58
2. **起后端**：`uv run anyspark-server`（或 anyspark_server start）→ `anyspark_state` 看现状
3. **拉真实 API**：用 `anyspark_api` 工具逐个调端点看响应结构（比读源码快）
4. **定范围**（与主人确认）：
   - 核心闭环升级（稿纸+对话+上下文+章节）先做，还是全功能（含 skill/推演/管理面板）
   - 视觉风格（重做 vs 保留朴素）
5. **复用评估**：api/client.ts、Paper.tsx、zustand stores 大概率保留；布局/面板重做
6. **开发 + 回归**：`anyspark_gate`（tsc/eslint/build）+ 真机链路验证（anyspark_state 核对产物）

## 五、关键提醒（踩坑预置）

- **C 架构**：前端的主要交互是**对话驱动写作**（聊天框是主角之一）——设计重心是对话体验+稿纸协作，不是堆管理面板
- **SSE 流式**：/api/chat/stream 的事件序列（turn_start→text_delta→tool_*→done）是前端打字机的基础，现有 chat.ts 已解析，保留
- **mood 是语义化**：前端传 0-100 数值，后端转程度词注入（S57）——前端只发数值即可
- **skill target**：写 skill 时 target 决定注入位置（writing→写作调用 / main→主循环 / both）——前端编辑时需让用户理解这个语义
- **心智分类**：manual 的 category（collab/style/habit）决定心智怎么用（collab→档位+协作约定 / style→文风偏好+skill匹配 / habit→习惯块）——编辑面板要体现分类
- **预存脏文件勿动**：`.env.example`/`.gitignore`/`benchmarks/compare/tasks.py`/`manual.py` 是历史遗留，非前端范围
- **禁 git add -A**：显式路径提交；data/ 不入库
