"""
anyspark.workflow.definition — 工作流定义数据模型。

设计（DESIGN.md §12.22，S59）：
- 结构化流程三结构：顺序（Sequence）+ 分支（gate）+ 循环（loop）。
- 节点类型：agent（调模型）/ script（确定性函数）/ approval（人工确认）/
  gate（条件分支）/ loop（循环）。
- 边带 condition（硬规则表达式或模型判断），挂在 gate 出边上表达分支。
- loop 节点 params 内声明 body（循环体节点 id 列表）+ max_iterations +
  continue_condition（为真继续循环）——不依赖回边，可证明终止。

哲学：机制（结构/校验/语法）硬编码；内容（节点指令/条件文本）自然语言。
算法结构借鉴 DeterminFlow（definition.py 的节点/边/变量模型与校验思路），
重写实现，不搬其运行时耦合。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# 节点类型（机制硬编码；类型集本期固定，扩展需改引擎——YAGNI）
NodeKind = Literal["agent", "script", "approval", "gate", "loop"]

# 节点状态（机制硬编码，状态机由 engine 驱动）
NodeStatus = Literal["pending", "running", "done", "failed", "skipped"]

# 任务状态
TaskStatus = Literal["queued", "running", "waiting_approval", "done", "failed", "cancelled"]

# 条件两种形态：
# - 硬规则：{"type": "rule", "expression": "{{hard_count}} > 0 AND {{ok}} == 'yes'"}
# - 模型判断：{"type": "model", "prompt": "本章是否已无硬伤？", "expect": "yes"}
Condition = dict[str, Any]


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _gen(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@dataclass
class FailPolicy:
    """节点失败策略（借鉴 DeterminFlow failure_policy，默认全关）。

    auto_retry_count: 首次失败后的自动重试次数（0=不自动重试）
    auto_retry_interval_seconds: 自动重试固定间隔（秒）
    fail_auto_skip: 重试耗尽后自动跳过继续下一节点（False=任务失败）
    """

    auto_retry_count: int = 0
    auto_retry_interval_seconds: int = 0
    fail_auto_skip: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FailPolicy:
        data = data or {}
        return cls(
            auto_retry_count=max(0, int(data.get("auto_retry_count", 0))),
            auto_retry_interval_seconds=max(0, int(data.get("auto_retry_interval_seconds", 0))),
            fail_auto_skip=bool(data.get("fail_auto_skip", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_retry_count": self.auto_retry_count,
            "auto_retry_interval_seconds": self.auto_retry_interval_seconds,
            "fail_auto_skip": self.fail_auto_skip,
        }


@dataclass
class WorkflowNode:
    """单个节点定义。"""

    id: str = field(default_factory=lambda: _gen("n"))
    kind: NodeKind = "agent"
    label: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    fail: FailPolicy = field(default_factory=FailPolicy)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        kind = str(data.get("kind") or data.get("type") or "agent")
        if kind not in ("agent", "script", "approval", "gate", "loop"):
            # S62：未知 kind 不再静默纠正为 agent（写错=白烧一次模型调用）——
            # 显式报错，让定义者/生成器修复
            raise ValueError(f"未知节点类型 {kind!r}（可选：agent/script/approval/gate/loop）")
        return cls(
            id=str(data.get("id") or _gen("n")),
            kind=kind,  # type: ignore[arg-type]
            label=str(data.get("label") or ""),
            params=dict(data.get("params") or {}),
            fail=FailPolicy.from_dict(data.get("fail")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "params": self.params,
            "fail": self.fail.to_dict(),
        }


@dataclass
class WorkflowEdge:
    """有向边。gate 出边携带 condition；普通边 condition 为空。

    condition 形态（DESIGN §12.22）：
      {"type": "rule", "expression": "{{var}} > 0"}
      {"type": "model", "prompt": "自然语言问题", "expect": "yes"}
    """

    source: str
    target: str
    id: str = field(default_factory=lambda: _gen("e"))
    condition: Condition | None = None
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEdge:
        return cls(
            source=str(data.get("source") or ""),
            target=str(data.get("target") or ""),
            id=str(data.get("id") or _gen("e")),
            condition=data.get("condition"),
            label=str(data.get("label") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
        }
        if self.condition is not None:
            d["condition"] = self.condition
        if self.label:
            d["label"] = self.label
        return d


@dataclass
class WorkflowDef:
    """工作流定义（模板级，与书解耦可迁移）。"""

    name: str
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    id: str = field(default_factory=lambda: _gen("wf"))
    created_at: str = field(default_factory=_now)
    # S76 画布布局（DESIGN §12.37）：node_id → {x, y}；空=全部自动布局
    layout: dict[str, dict[str, float]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 校验（机制硬编码：非法定义拒绝入库/执行）
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """返回错误列表（空=合法）。"""
        errors: list[str] = []
        if not self.name.strip():
            errors.append("name 不能为空")
        if not self.nodes:
            errors.append("nodes 不能为空")
        node_ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.source not in node_ids:
                errors.append(f"边 {e.id} 引用未知源节点 {e.source}")
            if e.target not in node_ids:
                errors.append(f"边 {e.id} 引用未知目标节点 {e.target}")
        # 每个节点最多一个出边（gate 可多出边，loop 单个出边=出口）
        out_degree: dict[str, int] = {}
        for e in self.edges:
            out_degree[e.source] = out_degree.get(e.source, 0) + 1
        for n in self.nodes:
            if n.kind != "gate" and out_degree.get(n.id, 0) > 1:
                errors.append(
                    f"节点 {n.id}({n.kind}) 有 {out_degree[n.id]} 条出边（仅 gate 允许多出边）"
                )
        # S62：有向环检测（DFS 三色法）——非 loop 语义的环会死循环（引擎互递归炸栈）
        # loop 节点按循环语义豁免（body 内部的环由 max_iterations 收敛）
        if self._has_cycle():
            errors.append("存在有向环（非 loop 语义的循环边，会死循环）")
        # gate 条件语法校验（S62 补：DESIGN §12.22 承诺的条件语法检查落地）
        for e in self.edges:
            cond = e.condition
            if not cond or cond.get("type") != "rule":
                continue  # model 型条件由 LLM 评估（无静态语法）；无 condition=默认分支
            expr = str(cond.get("expression") or "").strip()
            if not expr:
                continue
            from .condition import validate_rule_syntax as _vrs

            syntax_errors = _vrs(expr)
            if syntax_errors:
                errors.append(f"边 {e.id} 条件表达式语法错误: {'; '.join(syntax_errors)}")
        # gate 出边必须带 condition（无 condition 的边视为 default 分支）
        # loop 必须有 body + max_iterations（S129：collection_var 模式迭代数=集合长度，
        # max_iterations 仍作安全上限必填）
        for n in self.nodes:
            if n.kind == "loop":
                body = n.params.get("body")
                if not isinstance(body, list) or not body:
                    errors.append(f"loop 节点 {n.id} 缺 body（循环体节点 id 列表）")
                elif any(b not in node_ids for b in body):
                    errors.append(f"loop 节点 {n.id} 的 body 引用未知节点")
                if int(n.params.get("max_iterations", 0)) <= 0:
                    errors.append(f"loop 节点 {n.id} 缺 max_iterations（>0 防死循环）")
                # S129：collection_var 模式与 continue_condition 模式二选一
                cv = n.params.get("collection_var", "")
                cc = str(n.params.get("continue_condition") or "")
                if cv and cc:
                    errors.append(
                        f"loop 节点 {n.id} 同时声明 collection_var 与 continue_condition"
                        "（集合遍历与条件循环二选一）"
                    )
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def _has_cycle(self) -> bool:
        """有向环检测（DFS 三色）：0=未访问 1=访问中 2=已完。loop 节点豁免
        （其 body 内循环由 max_iterations 收敛，入口边本身不入环判定）。"""
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj.setdefault(e.source, []).append(e.target)
        color: dict[str, int] = {}
        loop_ids = {n.id for n in self.nodes if n.kind == "loop"}

        def dfs(node_id: str) -> bool:
            color[node_id] = 1
            for nxt in adj.get(node_id, []):
                if nxt in loop_ids:  # 进入 loop 节点不算环（body 内由 max 收敛）
                    continue
                c = color.get(nxt, 0)
                if c == 1:
                    return True
                if c == 0 and dfs(nxt):
                    return True
            color[node_id] = 2
            return False

        return any(dfs(n.id) for n in self.nodes if color.get(n.id, 0) == 0)

    def start_node(self) -> WorkflowNode | None:
        """起始节点：无入边的第一个节点（定义顺序）。"""
        targets = {e.target for e in self.edges}
        for n in self.nodes:
            if n.id not in targets:
                return n
        return self.nodes[0] if self.nodes else None

    def node(self, node_id: str) -> WorkflowNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def out_edges(self, node_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.source == node_id]

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDef:
        return cls(
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            nodes=[WorkflowNode.from_dict(n) for n in data.get("nodes") or []],
            edges=[WorkflowEdge.from_dict(e) for e in data.get("edges") or []],
            id=str(data.get("id") or _gen("wf")),
            created_at=str(data.get("created_at") or _now()),
            layout=dict(data.get("layout") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "layout": self.layout,
            "created_at": self.created_at,
        }
