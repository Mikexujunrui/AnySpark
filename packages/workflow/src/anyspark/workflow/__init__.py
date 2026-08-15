# AnySpark v4 — anyspark-workflow 工作流扩展包
# 结构化流程三结构（顺序/分支/循环）+ 断点恢复 + AI 生成（草稿+人工确认闸门）
# 设计规格：DESIGN.md §12.22（S59）。依赖 core（单向）。
#
__version__ = "0.0.1"

from .condition import evaluate_rule, validate_rule_syntax
from .definition import (
    FailPolicy,
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
)
from .engine import (
    NodeResult,
    NodeRunner,
    RunContext,
    WorkflowEngine,
    wait_approval,
)
from .generator import NODE_CATALOG, WorkflowGenerator
from .store import WorkflowStore

__all__ = [
    "NODE_CATALOG",
    "FailPolicy",
    "NodeResult",
    "NodeRunner",
    "RunContext",
    "WorkflowDef",
    "WorkflowEdge",
    "WorkflowEngine",
    "WorkflowGenerator",
    "WorkflowNode",
    "WorkflowStore",
    "evaluate_rule",
    "validate_rule_syntax",
    "wait_approval",
]
