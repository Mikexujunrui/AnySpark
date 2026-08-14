# D1 复杂改造文档：`_wf_run_script` 拆分（500 行 if/elif → script 注册表）

> 对应 `docs/REPAIR-LIST.md` D1。本文件为**实施设计**——机制怎么拆、迁移怎么走、
> 风险怎么控。实施时按此执行，完成后把结果回写本文件"实施记录"。

## 一、现状（问题确认）

- `packages/app/src/anyspark/server/app.py:1002-1560`（~560 行）单函数
- 20 个 script 分支全 if/elif：`batch_prepare` `book_refine_accumulate`
  `book_refine_finish` `book_refine_prepare` `book_refine_refine_input`
  `book_refine_titles` `chapter_by_id` `chapter_extract` `chapter_title_by_id`
  `conversation_summarize` `enrich_stitch` `list_chapters` `noop` `query_reference`
  `read_chapter` `read_graph` `read_settings` `review_chapter` `signal_refine`
  `write_chapter`
- 膨胀史：S129 起每个 workflow 阶段往这里加分支（S129 +5、S133 +3、S134 +3、
  S137 +1、S135 引用）——**函数会持续长下去**
- 每个分支依赖闭包环境：`ctx`(RunContext) + 外部 store 变量（chapters/deps/workspace/
  model/tasks 等），需保持可见

## 二、目标架构

```python
# 每个 script 独立函数定义（模块级或同文件独立 def），签名统一：
def _wf_script_xxx(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    """docstring: 功能 + params 说明"""
    ...

# 注册表：name → 函数（集中一处，一眼看全所有 script）
WF_SCRIPTS: dict[str, Callable[[RunContext, WorkflowNode], NodeResult]] = {
    "noop": _wf_script_noop,
    "read_chapter": _wf_script_read_chapter,
    "write_chapter": _wf_script_write_chapter,
    ...  # 20 个
}

def _wf_run_script(ctx, node) -> NodeResult:
    """分发器：查表 + 统一错误/返回值处理（不再长 if/elif）。"""
    fn = str(node.params.get("function") or "")
    handler = WF_SCRIPTS.get(fn)
    if handler is None:
        return NodeResult(error=f"未知 script 函数: {fn}")
    return handler(ctx, node)
```

**收益**：
- 新 script = 新函数 + 一行注册（不再触碰分发器）
- 每个函数可独立单测（不用过完整 workflow）
- 分发器 15 行，一眼看全

## 三、闭包依赖处理（关键难点）

现状分支直接引用 build_app 闭包变量（chapters/workspace/model/deps/tasks 等）。
拆分后函数需拿到这些——两种方案：

| 方案 | 做法 | 取舍 |
|---|---|---|
| **A. 保留闭包，函数定义在 build_app 内** | 把 20 个 `def _wf_script_xxx` 定义在 build_app 内（替代现在 if/elif 块），注册表也建在 build_app 内 | 闭包照旧可用（改动最小）；函数仍在 app.py 内但各自独立、不再 500 行单函数 |
| **B. 函数提模块级 + 传参** | 签名加 `chapters/deps/...` 参数，调用时注入 | 更干净但 20 个函数签名都要改、调用点全改，风险高 |

**建议：方案 A（先拆函数，不搬文件）**——把 if/elif 分支机械改为 20 个独立
`def _wf_script_xxx(ctx, node)`（仍定义在 build_app 内，闭包天然可用），加注册表。
D2（搬文件）时再处理依赖注入，届时闭包方案改为显式传参或移到独立模块做
`make_script_dispatch(deps)` 工厂。

## 四、迁移步骤（小步 + 全量验证）

1. **基线**：先跑全量 pytest（594+）确认绿，记 commit
2. **机械拆分（一步）**：
   - 把 `_wf_run_script` 的 20 个 `if fn == "xxx": ...` 块，逐个改为
     `def _wf_script_xxx(ctx, node): ...`（缩进 -1 层，return 保留）
   - 建 `WF_SCRIPTS` 注册表
   - `_wf_run_script` 替换为查表分发器
   - **行为零变化**：每个分支逻辑逐字保留，只改包装
3. **验证**：全量 pytest（workflow 测试 20+ 全过 = 行为不变锚点）+ ruff + mypy
4. **独立单测补充**（可选强化）：`test_workflow_scripts.py` 直调 `_wf_script_xxx`
   单测（不需要完整 workflow 装配）
5. **提交**：D1 commit（行为零变化声明）

## 五、风险与回退

- **风险**：机械缩进/改名出错 → 用 git diff 逐函数对照（改动应只有缩进+def 包装，
  无逻辑变化）；全量 workflow 测试是行为锚点
- **回退**：单 commit 可 revert（拆分不混其他改动）
- **不动**：`_wf_run_agent`/`_wf_run_subagent`/`_wf_runner` 等（非本次范围）

## 六、实施记录

（实施后填写：commit hash、实际拆分结果、验证情况、发现的新问题）
