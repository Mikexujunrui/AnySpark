# 后端待处理问题清单

**创建时间**：2026-08-10  
**来源**：F8-F9 前端测试中发现的后端问题  
**优先级**：P0 > P1 > P2  
**状态**：历史快照（2026-08-10）——S145 已复核标注各条修复状态；新问题请记入
PROGRESS.md 或本文件末尾追加新条目（勿改历史条目修复内容，保留审计痕迹）。

---

## 🔴 P0 阻塞性：SQLite 并发锁定（✅ 已修复：S75 补 commit + S79 core/db.py 收敛）

> S145 复核：本条目所列问题均已修复——`core/db.py`（S79）收敛连接配置
> （WAL + timeout=30 + check_same_thread=False），`sqlite.py:456`（S75）补 commit；
> `test_sqlite.py:76` 断言 WAL 生效。下方

### 现象

删除章节后立即发送聊天请求，后端返回 `500 Internal Server Error`，前端智能体"死机"。

### 错误栈

```
packages/app/src/anyspark/server/app.py:1679  chat → agent.store.create()
packages/app/src/anyspark/store/sqlite.py:94  create → self._conn.execute(INSERT)
sqlite3.OperationalError: database is locked
```

### 根因分析

1. **多 store 共用 `data/anyspark.db`**  
   `SqliteConversationStore`、`ChapterStore`、`ManualStore`、`SkillStore`、`StoryTreeStore` 等 15+ store 各自独立 `sqlite3.connect()` 到同一文件，形成多连接竞争。

2. **`ChapterStore.delete()` 缺失 `commit()`**  
   位置：`packages/app/src/anyspark/store/sqlite.py:368-373`
   ```python
   def delete(self, chapter_id: str) -> bool:
       with self._lock:
           cur = self._conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
           self._conn.execute("DELETE FROM chapter_versions WHERE chapter_id = ?", (chapter_id,))
           # ❌ 缺少 self._conn.commit()
       return cur.rowcount > 0
   ```
   DELETE 操作在 `with self._lock` 内执行但没有 commit，事务保持打开，锁持续持有。

3. **默认 `timeout=5`**  
   `sqlite3.connect()` 未指定 timeout，默认 5 秒，高并发下不够。

4. **非 WAL 模式**  
   默认 rollback journal 模式下读写互斥，无法支持并发读。

### 复现步骤

```bash
# 1. 启动后端
uv run uvicorn anyspark.server.app:app --host 127.0.0.1 --port 8002 --reload

# 2. 获取章节 ID
curl -s http://127.0.0.1:8002/api/chapters | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else 'empty')"

# 3. 删除章节
curl -X DELETE http://127.0.0.1:8002/api/chapters/<id>

# 4. 立即发送聊天请求
curl -X POST http://127.0.0.1:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
# → Internal Server Error
```

### 建议修复方向

#### 方案 A：最小修复（推荐先做）

1. **所有 store 的 `__init__` 添加 WAL + timeout**
   ```python
   self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
   self._conn.execute("PRAGMA journal_mode=WAL")
   ```

2. **所有写操作确保 `commit()`**
   - `ChapterStore.delete()` 添加 `self._conn.commit()`
   - 检查其他 store 的 `delete()`、`update()` 方法

#### 方案 B：架构优化（长期）

- **全局单一连接池**：引入 `_shared_conn` 注入各 store，避免多连接竞争
- **引入 busy_timeout 全局配置**：`.env` 中配置 `SQLITE_TIMEOUT=30`
- **考虑迁移到 PostgreSQL**：如果并发需求持续增长

#### 方案 C：前端防御（临时）

- 前端删除章节后延迟 1 秒再允许发送消息（治标不治本）

---

## 🟡 P1 体验问题：前端聊天错误处理（🟡 部分已修：S145 复核）

> S145 复核：文中引用的 `chatStore.ts:338-348` 已不存在（S75 前端重构后聊天状态
> 收归 ChatPanel.tsx + hooks/useSSE.ts，无独立 chatStore）。错误重置逻辑已在
> useSSE.ts 的 error 分支 + ChatPanel 处理（onError 回调重置 streaming）；
> “重试/超时”增强仍为候选（未实现）。下方

### 现象

后端 500 时，前端 `streamChat` 触发 error 事件，但 `streaming` 状态可能未完全重置，导致后续消息无法发送。

### 位置

`frontend/src/stores/chatStore.ts:338-348`

```typescript
case "error":
  set((state) => ({
    messages: [
      ...state.messages,
      { role: "assistant", content: `[错误: ${data.message || "未知错误"}]` },
    ],
    streaming: false,
    streamingText: "",
    abortController: null,
  }));
  break;
```

### 建议修复

1. **error 事件后强制重置状态**
   ```typescript
   case "error":
     set({
       streaming: false,
       streamingText: "",
       abortController: null,
     });
     // 添加错误消息
     set((state) => ({
       messages: [
         ...state.messages,
         { role: "assistant", content: `[错误: ${data.message || "未知错误"}]` },
       ],
     }));
     break;
   ```

2. **显示可操作的错误提示**
   - 添加"重试"按钮
   - 添加"新建会话"按钮
   - 错误消息可折叠/关闭

3. **添加超时处理**
   - 流式请求超过 60 秒无响应 → 自动中断并提示

---

## 🟢 P2 数据一致性

### 现象

`/api/uncensored` 返回 `{book_id, enabled}`，无 `level` 字段。

### 当前状态

前端已对齐（移除 `level` 字段依赖）。

### 未来扩展

若需支持分级破限（标准/激进/自定义），需后端先加 `level` 字段：

```python
# 建议的数据结构
{
    "book_id": "main",
    "enabled": true,
    "level": "standard" | "aggressive" | "custom",
    "custom_prompt": "...",  # level=custom 时使用
}
```

---

## 附录：受影响的 Store 列表

以下 store 共用 `data/anyspark.db`，需统一修复：

| Store | 文件路径 | 主要职责 |
|-------|---------|---------|
| `SqliteConversationStore` | `packages/app/src/anyspark/store/sqlite.py` | 会话/消息 |
| `ChapterStore` | `packages/app/src/anyspark/store/sqlite.py` | 章节/版本历史 |
| `ManualStore` | `packages/align/src/anyspark/align/manual.py` | 心智条目 |
| `WritingSkillStore` | `packages/align/src/anyspark/align/skills.py` | 叙事技巧 |
| `StoryTreeStore` | `packages/align/src/anyspark/align/storytree.py` | 叙事树节点 |
| `StoryThreadStore` | `packages/align/src/anyspark/align/storytree.py` | 线进度 |
| `AgencyStore` | `packages/align/src/anyspark/align/agency.py` | 档位状态 |
| `WorldSettingStore` | `packages/align/src/anyspark/align/worldsettings.py` | 世界设定 |
| `DimensionStore` | `packages/explore/src/anyspark/explore/direction.py` | 探索维度 |
| `PlotStore` | `packages/template/src/anyspark/template/plot.py` | 伏笔/剧情点 |
| `MaterialStore` | `packages/template/src/anyspark/template/materials.py` | 素材库 |
| `GraphStore` | `packages/graph/src/anyspark/graph/schema.py` | 图谱实体/关系 |
| `PlayTreeStore` | `packages/play/src/anyspark/play/tree.py` | 推演树 |
| `WorkflowStore` | `packages/workflow/src/anyspark/workflow/store.py` | 工作流 |
| `ModelRegistry` | `packages/app/src/anyspark/models/registry.py` | 模型配置 |
| `ExtensionToolStore` | `packages/app/src/anyspark/server/tools_extensions.py` | 扩展工具 |

---

**交接说明**：  
- P0 问题阻塞前端核心流程（聊天），建议优先修复  
- 修复后需运行 `scripts/gate.py` 确保测试通过  
- 前端已做临时防御（删除章节后自动选中其他章节），但后端并发锁定仍需根治
