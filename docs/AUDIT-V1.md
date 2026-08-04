# AnySpark v4 — 设计实现审计报告（截至 25e7d54）

> 审计日期：2026-08-02（历次复核：S12 收尾 / S13 补全 / S14 T7 / S21 循环工程化） | 当前基准 commit：`25e7d54`（S21c 后台独立 worker） | 上一基准：`62246b1`（S7 知识图谱）
> 审计方式：逐项对照 `DESIGN.md` 全部规格 vs 实际代码（后端 7 包 + 前端 + 测试 78 + 门禁全绿）
> 用途：**给下一个接手 AI 的现状快照**——哪些实现、哪些缺失、缺口在哪、先补什么。
> 注意：本报告是"时点快照"，后续实现后需同步更新；这不是对 DESIGN.md 的修改。

---

## 0. 一页速览（先读这个）

**结论：七阶段主干全部通过 ✅，但 DESIGN 完整规格（机制硬编码/模型局限弥补）仍有实质缺口 ❌。**

| 维度 | 状态 |
|---|---|
| 七阶段验收（T6 0-6） | ✅ 全部通过，每阶段真实 DeepSeek 链路验证 |
| 门禁 | ✅ ruff + mypy + pytest(78) + tsc + eslint + vite build 全绿 |
| 包结构 | ✅ core/app/align/explore/check/template/graph/desktop 8 包，core 零依赖 |
| **知识图谱（实体/关系/时间线/FTS + 当前时空点注入）** | ✅ **S7 已实现**（`graph/` 包，见下 §1 表） |
| **token 预算/两阶段压缩** | ✅ **S8 已实现**（TokenBudget：tiktoken+prune/summarize） |
| **能动性协议（机制2，0-4级）** | ✅ **S9 已实现**（agency.py 五级协议+温度映射+反馈调节） |
| **SSE 流式传输** | ✅ **S8 已实现**（/api/chat/stream 事件→帧，前端打字机） |
| **AI 倾向档案** | ✅ **S9 已实现**（bias.py + /api/bias 注入） |
| **确定性校验**（时间线/设定冲突/伏笔） | 🟡 S7 已铺**图谱证据层**（graph_evidence）；完整规则（时间线顺序/伏笔匹配）按需后补 |
| **T2 写作交互**（方向声明/候选卡堆/渐变条/一章收尾） | ✅ **S10 已实现**（4 端点 + InteractionTools 面板） |
| 低摩擦交互组件（机制4） | ✅ **S9/S10 已实现**（AgencyPicker 圆点/候选卡/渐变条/插入总线） |
| 评审团/Autopilot/增强包 | ⏸ 设计明确降为可选、默认关闭——非缺口 |

---

## 1. 完整实现 ✅（可直接信任，不用重做）

| 规格项 | 规格出处 | 实现位置 |
|---|---|---|
| uv workspace 多包 / FastAPI / SQLite / React19+Vite+Tailwind4+TipTap+Zustand / 桌面壳 | §4 | `packages/*` + `frontend/` |
| core 零依赖 / 单向依赖 / 模型无关（namespace + py.typed） | §4 铁律 | `packages/core` |
| Agent 循环（读提示→调工具→回填→输出，结构化 ModelOutput） | §4 协议层 | `core/loop.py` |
| 工具调用协议（ToolSpec/schema/注册表/执行） | §4 协议层 | `core/protocol.py` |
| 事件协议 + 注册钩子（通用事件 text/done/error/tool_call） | §4 协议层 | `core/events.py` |
| 存储接口（会话/消息最小持久化，实现可换） | §4 协议层 | `core/storage.py` |
| 探索-判别双循环（意图→策略集→并行4探索者→方向卡→固化） | 机制1/机制7 | `explore/` |
| 多智能体探索 8 项约束（轻量/并行/隔离/三来源/不撞墙/顺序规避） | 机制7 | `explore/explorers.py` |
| 对齐系统：说明书分层/锁定/置信度/活跃度 + 信号采集 + 提炼 + 摘要 + 注入 | 机制3 + §6 | `align/` |
| 轻量规则编译器（禁用词/术语偏好/段落句数，中文支持） | 机制8 | `check/rules.py` |
| 检测网：7 类骨架 + AI 动态检测 + 多检测者并行 + hard/suggestion | 机制9 | `check/` |
| 模式库 L2 默认库（5 模板 + 四要素元数据） | 机制6 | `template/patterns.py` |
| 资料消化：摘要卡/原文保留/用途标注 | 机制10（部分） | `template/materials.py` |
| 对话→写作→修改闭环（真实 DeepSeek 原生工具调用 + 章节版本历史） | T2 阶段5（部分） | `app/server` + `store/sqlite.py` |
| 概念卡→方向卡→稿纸三对象 | §7 T2 | 前端 `ExplorePanel` + `Paper` |
| 日志机制（RotatingFileHandler 落盘 + 控制台） | 无规格项（工程补充） | `app/server/logging.py` |
| Windows 一键启动 start.bat + 按端口清理 kill_port.bat | 工程补充 | 根目录 |
| CI（GitHub Actions 全门禁） + 一键总闸 gate.py | §9 纪律 | `.github/` + `scripts/gate.py` |
| 纪律：显式 add / data 不入库 / 锁文件 / commit 标阶段 / 模型无关 | §11 | 全程遵守 |
| 对话降为纸边批注（机制 5 部分：稿纸为主角） | 机制5 | 前端 `ChatThread` + App 壳 |
| 知识图谱：实体/关系/事件 + FTS 检索 + 当前时空点注入 + 资料图谱关联 + 校验证据 | §8.3/§8.7 + 模型局限弥补 | `graph/` 包（S7） |
| token 预算 + prune/summarize 两阶段压缩（tiktoken 精确计数/降级链） | 模型局限弥补 + §4 上下文管道 | `app/server/context.py`（S8） |
| SSE 流式传输（core 事件协议→SSE 帧；前端 fetch+ReadableStream 打字机） | A 类硬编码 | `/api/chat/stream` + `frontend/api/chat.ts`（S8） |
| 能动性协议 0-4 级（温度映射/反馈调节/AI 声明解析）+ 前端选择器 | 机制 2 | `align/agency.py` + `AgencyPicker`（S9） |
| AI 倾向档案（自述+用户修正，注入系统提示） | §2 双向黑盒解法 | `align/bias.py` + `/api/bias`（S9） |
| 低摩擦交互：方向声明/候选卡堆/改写渐变条/一章收尾 + 拖入稿纸 | 机制 4 + T2 阶段 5/6 | `InteractionTools` + `insertBus`（S10） |
| 流程基建：指数退避重试/超时熔断（DeepSeekModel timeout+retry） | 模型局限弥补 | `app/server/retry.py`（S11） |
| 安全底线：未知工具兜底/落盘自校验/沙箱越界/超长上限/docx 解析 | A 类硬编码 | `tools_writing.py`（S11） |
| 多格式导出（txt/md，RFC5987 中文文件名） | 模型局限弥补工具执行 | `/api/chapters/{id}/export`（S11） |
| 智能体接入层 + 记录基础设施（pi-anyspark 4 工具 + data/dev/） | 工程补充 | `E:\Desktop\pi\pi-main\packages\pi-anyspark`（S7 补充） |
| T7 验证指标（修改率/提问率/完成率，纯 SQL 统计现有表零新表 + /api/stats） | §9 T7 | `app/server/stats.py`（S14） |
| 增强按需装配（enable_search 默认关 / extract_graph 可关 / skip_inject 细粒度） | §4 核心原则 + 机制7 | `app/server/app.py` ChatRequest（S15） |
| 重试可拼接组件（core.RetryingModel 组合包装，任何模型可套；DeepSeek 不再内嵌） | §1 A 类硬编码 | `core/retry.py`（S15） |
| 氛围滑块注入归属 align（mood.py，B 类载体与 agency/bias 同包） | 机制4 | `align/mood.py`（S15） |
| 前端抽屉按需加载（React.lazy + Suspense，独立 chunk） | 机制5 抽屉 | `frontend/src/app/App.tsx`（S15） |
| 伏笔闭环（注入写作/自动回收/关注度 care-ignore） | T2 阶段3 + 机制 | `template/plot.py` + `app.py`（S17） |
| 角色/地点状态演化（state 增量拼接 + 演化历史表 + 注入优先显示状态） | 老愿景内核 v4 轻量实现 | `graph/`（S20） |
| Agent 循环工程化（流式核心/截断防护/工具并行/协作式中断/已读缓存） | A 类过程控制 | `core/loop+retry` + `app`（S21） |
| 循环健壮性对齐 pi：异常上下文平衡（失败不毒化上下文）/ 重试覆盖 429·5xx·quota 分类 / 截断防护读 finish_reason（length 全拒）/ 取消补 assistant 消息 | 模型局限弥补 + A 类过程控制 | `core/loop+retry` + `models/deepseek.py`（S22） |
| 工具调用协议完整化：ToolCall.id + assistant 声明落库 + tool 结果 tool_call_id 配对（原生 OpenAI 格式，旧链路兼容） | §4 协议层 | `core/loop+types` + `models/deepseek.py`（S23） |
| 压缩对齐 pi：指纹先查 + 字符粗算省精算 / token 预算切割永不切 tool 结果 / 摘要全量输入 + 增量更新模式 | 模型局限弥补 + §4 上下文管道 | `server/context.py`（S24） |
| 运行中插话 steering / 排队追问 followUp / 工具执行事件（前端进度显示）/ 工具 sequential 串行模式 | 机制5 + A 类过程控制 | `core/loop+protocol` + `app.py` + 前端（S25） |
| 压缩持久化回写 store（pi compaction entry 语义，跨重启）/ 模型窗口感知预算 / max_tokens 8192 | 模型局限弥补 + §4 上下文管道 | `core/storage+loop` + `deepseek.py` + `app.py`（S26） |
| before/afterToolCall 钩子（拦截/改写）/ terminate 智能停止（整批终止）/ SSE 假 done 修复 / 流式重试防重复 delta | 机制5 + A 类过程控制 | `core/loop+retry+types` + `deepseek.py`（S27） |
| pi 行为对照测试（7 场景语义轨迹一致）/ 性能基线存档 / 长书压力测试（暴露修保留段阈值缩放 bug + steer 终答轮丢失） | 工程验证 | `benchmarks/parity/`（S28） |
| 信号→说明书提炼闭环修复（signals 后台入队提炼，PreferenceExtractor 首次接线）/ 分支剧本哲学指标验证（修改率↓/说明书累积/偏好遵从） | 机制 3 对齐系统 + §9 T7 | `app.py` + `store/sqlite.py` + `benchmarks/system/`（S21 系统层） |
| 多线叙事时间建模（Entity.lines + chapters.narrative_line + 时序校验按线比较） | 机制9 检测网补充 | `graph/schema+verify` + `tools_writing` + `app.py`（S29） |

**已完成的真实链路验证**（均有冒烟脚本 `scripts/*_smoke.py`）：
- `real_smoke.py`：DeepSeek 原生工具调用 12345+6789=19134
- `align_smoke.py`：信号→提炼"避免血腥/克制内敛"→说明书→注入→写作遵守
- `explore_smoke.py`：种子→意图确认（noir/潮湿阴郁+3关键问题）→4卡真多样→固化
- `check_smoke.py`：孤儿→母亲矛盾被 6-7 检测者发现（硬伤标红+建议）
- `template_smoke.py`：雾城设定 171 字→摘要卡→注入 ~200 字省 token

---

## 2. 部分实现 🟡

| 规格项 | 已做 | 缺什么 |
|---|---|---|
| 机制 10 资料消化 | 摘要卡/原文/用途 | **图谱关联**（DESIGN 明示"摘要卡关联图谱实体"，但无图谱） |
| 机制 6 模式库 | L1（模型内存，天然）+ L2 | **L3 外部库接口**（DESIGN 标注按需后补，YAGNI 合理） |
| T2 阶段 5 写作 | 稿纸+对话+探索 | **方向声明 / 候选卡堆 / 改写渐变条 / 建议卡拖入稿纸** |
| T2 阶段 6 一章收尾 | — | **更新图谱 / 一致性摘要卡 / 下一章衔接提示**（随图谱一起做） |

---

## 3. 未实现 ❌（按优先级排序，含规格出处）

### ✅ 已全部补齐（S7-S11）：
- ~~P0 知识图谱~~ → S7（`62246b1`）：实体/关系/事件 + FTS trigram + 当前时空点注入 + 资料图谱关联 + 检测证据
- ~~P1 token 预算+两阶段压缩~~ → S8（`8235caa`）：TokenBudget（tiktoken + prune/summarize，降级链）
- ~~P1 能动性协议~~ → S9（`d47df60`）：五级协议 + 温度映射 + 反馈调节 + 声明解析 + 前端选择器
- ~~P2 SSE 流式~~ → S8（`8235caa`）：/api/chat/stream 事件→帧，前端打字机
- ~~P2 AI 倾向档案~~ → S9（`d47df60`）：bias.py + /api/bias 注入
- ~~P3 流程基建~~ → S11（`866dd66`）：指数退避重试 + DeepSeekModel 超时
- ~~P3 安全底线~~ → S11：未知工具兜底 / 落盘自校验 / 沙箱越界 / 超长上限
- ~~P3 工具扩展~~ → S11：沙箱文件工具（txt/md/docx）+ 多格式导出（网络搜索按需后补）
- ~~P3 低摩擦组件~~ → S9/S10：能动性圆点 / 候选卡堆 / 渐变条 / 方向声明 / 一章收尾 / 拖入稿纸

### 剩余（设计明确降权/后补，勿当缺失补）：
- ~~确定性校验完整规则~~ → **S13 时序校验已实现**（check_temporal：时空倒置检测）；**S29 多线叙事按线比较**（narrative_line，跨线首现不误报）；伏笔匹配按需
- ~~关键点图谱~~ → **S13 已实现**（PlotStore/PlotGenerator + /api/plot）
- ~~网络搜索工具~~ → **S13 已实现**（search_web：360+Bing 降级，参考 pi 搜索包）
- ~~L3 外部模式库~~ → **S13 已实现**（ExternalLibrary + /api/templates/import）
- ~~氛围滑块组~~ → **S13 已实现**（mood 注入 + 前端 MoodSliders）
- ~~T7 验证指标（修改率/提问率/完成率）~~ → **S14 已实现**（stats.py 纯 SQL 统计现有表 + /api/stats；零新表零埋点——信号本身就是埋点）
- 场景拼图板（画布级拖拽）——仍按设计降权，按需后补
- 评审团/Autopilot 增强包——设计明确降为可选、默认关闭

---

## 4. 非缺口（设计明确排除或降权，勿当缺失补）

| 项 | 说明 |
|---|---|
| 评审团/Autopilot/工作流/Skill/创作宪法/叙事约束 | 去留清单：🔻 降为可选增强包，默认关闭 |
| 叙事统计/AI 味扫描/记忆表单面板 | 🔴 删（勿实现） |
| 时间线/地图/灵感盒/推演 | 🟡 降权，不进主导航（部分类型刚需，可后补） |
| L3 外部模式库 / 商业分层 | 机制6：明确按需后补（YAGNI） |
| 旧数据一次性导入 | 主人 2026-08-02 决策：全新项目，不做导入（见 PROGRESS.md 决策A） |
| 美学 | 明确"美学暂缓" |

---

## 5. 接手 AI 行动建议

1. **先读**：`docs/DESIGN.md`（唯一主规格）→ 本文档（现状快照）→ `docs/PROGRESS.md`（推进台账+踩坑）
2. **补缺优先级**：P0 知识图谱（含"当前时空点检索注入"）→ P1 token 压缩 → P1 能动性协议 → P2 SSE → 其余按需
3. **每条缺口开工前**：先向主人确认（AGENTS.md 纪律：对设计的偏离/新增必须先确认），再更新本报告对应条目状态
4. **完成后**：更新本文档"✅ 完整实现"表 + 删除对应 ❌ 条目 + 更新 PROGRESS.md

---

*本报告为工程交接文档，任何与 DESIGN.md 冲突处以 DESIGN.md 为准；对 DESIGN.md 的修改需主人确认。*
