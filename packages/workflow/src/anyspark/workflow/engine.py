"""
anyspark.workflow.engine — 工作流执行引擎（顺序 + 分支 + 循环 + 断点恢复）。

设计（DESIGN §12.22，S59）：
- 结构化三结构：顺序（沿边推进）/ gate（出边条件分支）/ loop（body 循环，
  continue_condition 为真继续，max_iterations 防死循环）。
- 断点恢复：每节点状态落盘（store.update_node_state）；恢复时 done 节点跳过，
  loop 从记录的迭代数续跑（body 内 done 节点跳过）。
- 失败策略：节点 fail 配置（auto_retry_count / interval / fail_auto_skip），
  借鉴 DeterminFlow failure_policy 设计，重写实现。
- 记账：每节点 token_usage 累加（由 runner 报告）。
- 节点执行解耦：agent/script/approval 的具体执行由调用方注入 NodeRunner
  （组合根装配；本包只依赖 core，不 import app）。

哲学：机制（调度/状态机/条件评估/重试）硬编码；内容（节点指令/条件文本）自然语言。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .condition import evaluate_rule
from .definition import WorkflowDef, WorkflowNode
from .store import WorkflowStore

logger = logging.getLogger(__name__)


@dataclass
class NodeResult:
    """节点执行结果（runner 返回，引擎落盘 + 记账）。"""

    output: str = ""
    token_usage: int = 0
    error: str = ""
    # 分支/循环的变量写入由引擎统一经 set_var 处理（runner 通过 ctx 写入）

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class RunContext:
    """节点运行上下文（runner 只读；写变量用 set_var）。"""

    task_id: str
    book_id: str
    definition: WorkflowDef
    results: dict[str, Any] = field(default_factory=dict)

    def var(self, key: str) -> Any:
        return self.results.get(key, "")


class NodeRunner(Protocol):
    """节点执行器协议（agent/script/approval 由组合根注入实现）。

    gate/loop 是引擎级控制原语，不由 runner 处理。
    组合根通常注入闭包函数（ctx, node）-> NodeResult；对象方法也可（忽略 self）。
    """

    def __call__(self, ctx: RunContext, node: WorkflowNode) -> NodeResult: ...


class WorkflowEngine:
    """工作流执行引擎。

    model_judge: 可选的模型判断回调 judge(prompt: str, ctx) -> bool，
      用于 gate/loop 的 model 型条件（缺省 None → 无 model 条件时走默认分支）。
    """

    def __init__(
        self,
        store: WorkflowStore,
        runner: NodeRunner,
        *,
        model_judge: Callable[[str, RunContext], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._store = store
        self._runner = runner
        self._model_judge = model_judge
        self._sleep = sleep
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def clear_stop(self) -> None:
        self._stop.clear()

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------
    def run_task(self, task_id: str) -> dict[str, Any]:
        """从 start 节点执行到完成/失败/等待审批。

        幂等可恢复：已 done 节点跳过；loop 从记录迭代数续跑。
        """
        self._stop.clear()
        task = self._store.get_task(task_id)
        if task is None:
            raise KeyError(f"任务不存在: {task_id}")
        definition: WorkflowDef = task["definition"]
        self._store.update_task_status(task_id, "running")
        try:
            start = self._pick_start(definition)
            if start is None:
                raise ValueError("定义无起始节点")
            results = dict(task["results"])
            ctx = RunContext(
                task_id=task_id,
                book_id=str(task["book_id"]),
                definition=definition,
                results=results,
            )
            self._execute_node(ctx, start)
            self._store.update_task_status(task_id, "done")
            final = self._store.get_task(task_id)
            return dict(final) if final else {}
        except _WaitApproval:
            # 保留当前节点 id（approve() 需要知道等的是哪个 approval 节点）
            cur = self._store.get_task(task_id)
            cur_id = str(cur["current_node_id"]) if cur else ""
            self._store.update_task_status(task_id, "waiting_approval", current_node_id=cur_id)
            final = self._store.get_task(task_id)
            return dict(final) if final else {}
        except _StopRequested:
            self._store.update_task_status(task_id, "cancelled", error="用户取消")
            final = self._store.get_task(task_id)
            return dict(final) if final else {}
        except Exception as exc:
            logger.exception("工作流任务 %s 失败", task_id)
            self._store.update_task_status(task_id, "failed", error=str(exc)[:500])
            final = self._store.get_task(task_id)
            return dict(final) if final else {}

    def approve(self, task_id: str, *, decision: str = "ok") -> dict[str, Any]:
        """approval 节点人工确认：ok 继续 / reject 失败。"""
        task = self._store.get_task(task_id)
        if task is None:
            raise KeyError(f"任务不存在: {task_id}")
        definition: WorkflowDef = task["definition"]
        cur_id = str(task["current_node_id"])
        cur = definition.node(cur_id)
        if cur is None or cur.kind != "approval":
            raise ValueError(f"当前节点 {cur_id} 不是 approval 节点")
        if decision == "reject":
            self._store.update_node_state(task_id, cur, "failed", error="人工驳回")
            self._store.update_task_status(
                task_id, "failed", error="approval 驳回", current_node_id=cur_id
            )
        else:
            self._store.update_node_state(task_id, cur, "done", output=decision)
            self._store.update_task_status(task_id, "running", current_node_id=cur_id)
            # 续跑（approval 之后的下游；done 节点自动跳过）
            result = self.run_task(task_id)
            return result
        final = self._store.get_task(task_id)
        return dict(final) if final else {}

    # ------------------------------------------------------------------
    # 内部调度
    # ------------------------------------------------------------------
    def _pick_start(self, definition: WorkflowDef) -> WorkflowNode | None:
        """起始节点。断点恢复由 _execute_node 的 done 跳过 + loop 迭代记录实现。"""
        return definition.start_node()

    def _execute_node(self, ctx: RunContext, node: WorkflowNode, *, force: bool = False) -> None:
        """执行单个节点（含 loop 展开）。幂等：done 跳过（force=True 强制重跑）。"""
        task_id = ctx.task_id
        if self._stop.is_set():
            raise _StopRequested()
        # 断点恢复：done 节点跳过但沿已记录去向推进（gate 用记录的 target）
        if not force and self._store.node_status(task_id, node.id) == "done":
            logger.info("[%s] 节点 %s 已 done，跳过（断点恢复）", task_id, node.id)
            if node.kind == "gate":
                recorded = self._store.node_output(task_id, node.id)
                if recorded and ctx.definition.node(recorded):
                    self._advance_to(ctx, recorded)
                    return
            self._advance(ctx, node)
            return

        if node.kind == "gate":
            self._run_gate(ctx, node)
            return
        if node.kind == "loop":
            self._run_loop(ctx, node)
            return

        # agent/script/approval：交给 runner（含失败重试）
        self._store.update_task_status(task_id, "running", current_node_id=node.id)
        self._store.update_node_state(task_id, node, "running")
        attempts = self._store.increment_attempts(task_id, node.id)
        try:
            result = self._runner(ctx, node)
        except _WaitApproval:
            raise
        except Exception as exc:
            logger.warning("[%s] 节点 %s 第 %d 次失败: %s", task_id, node.id, attempts, exc)
            result = NodeResult(error=str(exc)[:500])

        if result.ok:
            self._store.append_result(task_id, node.id, result.output)
            # 节点 label 或 params.output_key 作为变量名（默认节点 id）
            var_key = str(node.params.get("output_key") or node.id)
            self._store.append_result(task_id, var_key, result.output)
            # 同步内存变量表（gate/loop 条件评估依赖 ctx.results）
            ctx.results[node.id] = result.output
            ctx.results[var_key] = result.output
            self._store.update_node_state(
                task_id,
                node,
                "done",
                output=result.output,
                token_usage=result.token_usage,
                attempts=attempts,
            )
            self._advance(ctx, node)
            return

        # 失败策略：重试 / 跳过 / 失败
        if self._should_retry(node, attempts):
            interval = max(0, node.fail.auto_retry_interval_seconds)
            if interval:
                self._sleep(interval)
            self._store.update_node_state(
                task_id, node, "failed", error=result.error, attempts=attempts
            )
            self._execute_node(ctx, node)  # 递归重试
            return
        if node.fail.fail_auto_skip:
            logger.info("[%s] 节点 %s 失败自动跳过: %s", task_id, node.id, result.error)
            self._store.update_node_state(
                task_id, node, "skipped", error=result.error, attempts=attempts
            )
            self._advance(ctx, node)
            return
        raise RuntimeError(f"节点 {node.id} 失败（已重试 {attempts} 次）: {result.error}")

    def _should_retry(self, node: WorkflowNode, attempts: int) -> bool:
        return node.fail.auto_retry_count > 0 and attempts <= node.fail.auto_retry_count

    def _run_gate(self, ctx: RunContext, node: WorkflowNode) -> None:
        """条件分支：评估出边条件，取第一个为真；否则走默认（无 condition）边。"""
        task_id = ctx.task_id
        self._store.update_node_state(task_id, node, "running")
        edges = ctx.definition.out_edges(node.id)
        default_edge = None
        for e in edges:
            if not e.condition:
                default_edge = e
                continue
            if self._eval_condition(e.condition, ctx):
                logger.info("[%s] gate %s → %s（条件命中）", task_id, node.id, e.target)
                self._store.update_node_state(task_id, node, "done", output=e.target)
                self._store.append_result(task_id, node.id, e.target)
                self._advance_to(ctx, e.target)
                return
        if default_edge is not None:
            self._store.update_node_state(task_id, node, "done", output=default_edge.target)
            self._store.append_result(task_id, node.id, default_edge.target)
            self._advance_to(ctx, default_edge.target)
            return
        # 无任何出边命中 → 视为终止（无默认分支）
        self._store.update_node_state(task_id, node, "done", output="(end)")

    def _run_loop(self, ctx: RunContext, node: WorkflowNode) -> None:
        """循环：按 body 顺序执行；continue_condition 为真继续，max_iterations 封顶。"""
        task_id = ctx.task_id
        params = node.params
        body_ids: list[str] = list(params.get("body") or [])
        max_iter = int(params.get("max_iterations") or 1)
        cond = str(params.get("continue_condition") or "")
        # 断点恢复：从 output 记录的迭代数续跑
        try:
            prev = json.loads(self._store.node_output(task_id, node.id) or "{}")
        except Exception:
            prev = {}
        start_iter = int(prev.get("iterations", 0))
        self._store.update_node_state(task_id, node, "running")

        iteration = start_iter
        while iteration < max_iter:
            if self._stop.is_set():
                raise _StopRequested()
            iteration += 1
            for nid in body_ids:
                body_node = ctx.definition.node(nid)
                if body_node is None:
                    continue
                # force：循环体内节点每轮强制重跑（done 跳过是跨迭代语义，不适用于循环体）
                self._execute_node(ctx, body_node, force=True)
                if self._store.node_status(task_id, nid) == "failed":
                    raise RuntimeError(f"loop 体节点 {nid} 失败")
            # 出口条件评估：cond 为空 → 跑满 max_iterations
            if cond:
                continue_loop = self._eval_condition({"type": "rule", "expression": cond}, ctx)
                if not continue_loop:
                    break
            # 记录进度（崩溃恢复用）
            self._store.update_node_state(
                task_id,
                node,
                "running",
                output=json.dumps({"iterations": iteration}, ensure_ascii=False),
            )
        self._store.update_node_state(
            task_id,
            node,
            "done",
            output=json.dumps({"iterations": iteration}, ensure_ascii=False),
        )
        self._advance(ctx, node)

    # ------------------------------------------------------------------
    # 条件评估
    # ------------------------------------------------------------------
    def _eval_condition(self, condition: dict[str, Any], ctx: RunContext) -> bool:
        ctype = str(condition.get("type") or "rule")
        if ctype == "rule":
            return evaluate_rule(str(condition.get("expression") or ""), ctx.results)
        if ctype == "model":
            if self._model_judge is None:
                logger.warning("model 条件无 judge 回调，按 False 处理")
                return False
            prompt = str(condition.get("prompt") or "")
            return bool(self._model_judge(prompt, ctx))
        logger.warning("未知条件类型 %s，按 False 处理", ctype)
        return False

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------
    def _advance(self, ctx: RunContext, node: WorkflowNode) -> None:
        """沿出边推进（普通节点单出边）。"""
        edges = ctx.definition.out_edges(node.id)
        if not edges:
            return
        if len(edges) > 1:
            # 非 gate 多出边（校验应已拦截）——保守取第一条
            logger.warning("节点 %s 多出边（应为 gate）", node.id)
        self._advance_to(ctx, edges[0].target)

    def _advance_to(self, ctx: RunContext, target_id: str) -> None:
        target = ctx.definition.node(target_id)
        if target is None:
            raise RuntimeError(f"边指向未知节点 {target_id}")
        self._execute_node(ctx, target)


class _WaitApproval(Exception):  # noqa: N818 - 内部控制信号（非错误），approval 节点等待人工
    """approval 节点等待人工确认（内部信号）。"""


class _StopRequested(Exception):  # noqa: N818 - 内部控制信号（非错误），用户取消
    """引擎停止（用户取消）。"""


def wait_approval() -> None:
    """runner 内调用：标记当前节点为等待审批。"""
    raise _WaitApproval()
