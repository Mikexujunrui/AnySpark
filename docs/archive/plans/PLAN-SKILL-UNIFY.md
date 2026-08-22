# 待更新方案：统一 skill 容器（type 分流 + 书名包）——消除知识归属竞争

> 状态：**三阶段全部实施完成**（S127 阶段 1 + S128 阶段 2 + S130 阶段 3；主人 2026-08-13 拍板后实施）
> 关联：§12.17 skill 定义 · §12.18b 生成器 · §12.20 target 分流 · §12.21 类型 skill ·
>       §12.43 拆书三层 · S69 剧情模式模板 · S60 注入瘦身 · S114 拆书
> 性质：结构调整提案。本文档定方案与迁移路径；实施完成，历史决策保留作审计依据。

---

## 一、问题诊断：知识归属竞争

当前"知识"散在三处，同一结构内容（如"时间回环"）不知该放哪：

| 容器 | 内容 | 消费方 | 状态 |
|---|---|---|---|
| skills 表（WritingSkill，五段式）| 文笔技法 / 方法论 / 架构技法（target=writing/main/both）| 写作调用 + 主循环 | ✅ 有 |
| templates（ExternalLibrary，四要素）| 剧情模式模板（granularity/position/function/params）| 探索派生方向 | ✅ 有（与 skills 并列）|
| workflow_templates | 可执行流程（节点/边）| agent 跑任务 | ✅ 有（独立，正确）|

**竞争根源**：skills 与 templates 都是"知识"，边界靠人脑判断（架构技法算 skill 还是剧情模板？），
同结构可双写 → 漂移。且拆书产出被分散（方法论→skills、剧情模式需另跑 plot 提炼）。

## 二、方案目标

1. **一个知识容器**：所有"知识"（文笔/方法论/架构技法/剧情模式）统一为 skill，按 type 分流
2. **归属问题消失**：新增知识只有一个问题——"它是什么 type 的 skill"，不再有"该放哪个库"
3. **粒度可选**：书名级整包引用 + 单条独立引用
4. **生产统一**：拆书产出整包，独立生成产单条，同一容器

## 三、方案设计

### 3.1 统一 skill 容器 + type 分流

```
skill（统一知识容器）
├─ type=writing：文笔技法      → 注入写作调用（write_chapter 干净上下文）
├─ type=main：架构技法/方法论   → 注入主循环（规划决策）
└─ type=plot：剧情模式模板      → 探索派生方向（四要素元数据=扩展字段）
```

- 保留现有 target（writing/main/both）作为**注入路由**；type 新增/替代 target 语义
  （writing→writing、main→main、both→按包拆分、plot→探索）——迁移时统一为 type 一个字段
- plot 类的四要素（granularity/position/function/params）存 skill 的**扩展字段**（JSON 列），
  机制校验枚举回落默认（复用现有 _parse_templates 逻辑）

### 3.2 书名包（聚合 + 粒度引用）

```
《斗破苍穹》 skill = 聚合包：
  ├─ 书名方法论（type=main，整本书写法：文风/节奏/结构/人设/对白/信息投放/钩子）
  ├─ 文笔技法 ×N（type=writing，各维度拆解子条）
  └─ 剧情模式 ×M（type=plot，从骨架笔记派生）
```

- **引用粒度**：
  - 整包："按斗破风格写" → 注入包内索引（name+description，对齐 S60 注入瘦身）
    + skill_lookup 按需细看 + write_chapter 点名
  - 单条："要这种文笔" → 只引 type=writing 子条
- 包 = 逻辑聚合（book_skill 表或 skills 表加 pack_id），子条独立可编辑/删除

### 3.3 workflow 保持独立（关键分层）

```
知识容器（skill）≠ 执行容器（workflow）
- skill：怎么想/怎么写（知识，注入参考）
- workflow：跑什么流程（执行，agent 运行）
- "拆书流程"是 workflow 模板；拆书产出的"知识"是 skill 包——流程与知识分开，互不竞争
```

**不把 workflow 并入 skill**——否则"流程"混进"知识"，制造新的混（流程是机制，知识是内容）。

### 3.4 生产统一

| 生产路径 | 产出 |
|---|---|
| 拆书（generate_book）| 一个书名包（各 type 子条，含剧情模式从骨架笔记派生）——一次拆书，全部落同一容器 |
| 独立生成（generate writing/main）| 单条 skill（type=writing/main）|
| 独立提炼（generate_plot）| 单条 skill（type=plot，四要素扩展字段）|

### 3.5 消费延伸：workflow 节点导入 skill（与 PLAN-WORKFLOW-UNIFY 交汇）

统一容器是 workflow 节点类型化引用 skill 的前提：节点按 type 注入（writing→生成节点、
plot→探索节点）、书名包 = 整包风格参数（模板参数化换 skill 换风格）。
单向依赖（workflow→skill），不反向。详见 PLAN-WORKFLOW-UNIFY §六。

## 四、与现状的迁移映射

| 现状 | 统一后 |
|---|---|
| skills 表（target 字段）| skill 表 type 字段（writing/main/plot；target 语义并入）|
| templates 表（ExternalLibrary，四要素）| **并入 skill 表**（type=plot，四要素存扩展 JSON）|
| 探索读 templates | 探索读 skill 表 type=plot 条目 |
| 拆书产出：方法论→skills + 另跑 plot 提炼 | 拆书一次产出整包（含 plot 子条，骨架笔记派生）|
| workflow_templates | **保持独立**（不动）|

## 五、迁移步骤（分阶段，每步可回退）

```
阶段 1：skills 表加 type 字段（writing/main/plot），target 语义并入；
        拆书产出补 plot 子条（骨架笔记 → 剧情模式，双落打通） ✅ S127
阶段 2：templates（ExternalLibrary）并入 skill 表（type=plot 迁移数据 + 扩展字段）；
        探索消费方改读 skill 表 plot 类 ✅ S128
阶段 3：书名包（pack_id 聚合 + 整包/单条引用路由）；
        前端书架技能面板展示类型分组 + 包视图 ✅ S130
每阶段：全量 gate + 消费方对拍（写作注入/主循环/探索派生结果一致）——S127/S128/S130 各批全绿
```

## 六、影响面

- **消费方**：写作调用（type=writing 注入）、主循环（type=main）、探索（type=plot）、
  skill_lookup/write_chapter 点名（按 type 过滤）
- **存储**：skills 表 + 扩展列；templates 表数据迁移（或兼容读）
- **前端**：书架技能 tab 按 type 分组；书名包视图（整包/子条）
- **文档**：DESIGN §12.17/12.18b/12.20/12.21/12.43 回写统一语义；BACKEND-MAP 更新

### 6.1 消费方等价性保障（固定消费不受影响，2026-08-13 主人确认时提出）

现有固定消费方（写作循环文笔注入 / 主循环 / 探索）在统一后**路由语义等价保留**：

| 消费方 | 现状读取 | 统一后 |
|---|---|---|
| 写作循环文笔注入 | `_target_matches(target,"writing")` 过滤（skills.py:469）| `type=="writing"` 等价替换 |
| 主循环 | `_target_matches(target,"main")` | `type=="main"` 等价替换 |
| 探索 | `templates_external.all()[:12]`（独立表）| S4 兼容读过渡不动；物理并入后只读 type=plot |

**三条实施纪律（必须写死）**：
1. target→type 是**等价替换不漏消费点**：所有 `_target_matches` 调用点同步换 + 对拍
2. 探索在兼容读期间**零改动**；物理并入那一步只读 type=plot（防其他 type 污染）
3. **书名包引用 ≠ 整包全注入**：写作循环引用包只注入包内 writing 子条，main/plot 子条
   绝不进写作上下文——包内按 type 分流到各自消费方

**保留语义**：书名方法论当前 target=both（写作+主循环都要）——统一后处理为多 type
或拆子条，两个消费方都可达，不能丢。

## 七、风险与回退

| 风险 | 缓解 |
|---|---|
| 迁移破坏现有注入/探索（skills 已稳定）| 分阶段 + 每步对拍 + 可回退（templates 兼容读保留）|
| type 与现有 target 语义冲突 | 明确映射表（target→type），迁移期双字段兼容 |
| 书名包复杂化（引用路由）| 阶段 3 最后做，包=逻辑聚合不物理复制 |
| plot 四要素丢失 | 扩展 JSON 字段 + 枚举校验复用 |

## 八、待主人拍板的决策点

> ✅ **已拍板（2026-08-13 主人全部确认）**：S1（三分类够，方法论用 tags 区分）/ S2（type
> 并入，单一字段即路由）/ S3（逻辑聚合 pack_id）/ S4（兼容读过渡）/ S5（阶段 1 拆书双落先行）

1. **type 命名**：writing/main/plot 三分类够吗？是否需要"方法论"独立 type（拆书方法论 vs 架构技法区分）？
2. **target 与 type**：保留 target（注入路由）还是并入 type（type 即路由）？——建议并入，单一字段
3. **书名包粒度**：包=逻辑聚合（pack_id）即可，还是要"包=可整体导出的单元"？
4. **迁移深度**：templates 并入（数据迁移）vs 兼容读（两表并存、skill 侧统一写入）？
5. **优先级**：先做拆书双落（阶段 1，低成本高价值），还是先做容器统一（阶段 2，结构性）？

## 九、一句话总结

> 知识统一进 skill 容器（type 分流：writing/main/plot），书名成包（整包/单条引用），
> 拆书一次产出整包——归属竞争消失；workflow（执行）保持独立，不混入知识；
> 分三阶段迁移（加 type → 并 templates → 书名包），每步对拍可回退。
