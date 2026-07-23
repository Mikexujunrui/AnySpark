"""Workflow Engine — executes workflow steps sequentially/conditionally."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class WorkflowStep:
    id: str
    type: str
    config: dict = field(default_factory=dict)
    label: str = ""
    status: str = "pending"

@dataclass
class Workflow:
    id: str
    name: str
    steps: list[WorkflowStep]
    status: str = "pending"
    current_step: int = 0


class WorkflowEngine:
    def __init__(self):
        self.handlers: dict[str, Callable] = {}
        self._active: dict[str, Workflow] = {}
        self._results: dict[str, list] = {}

    def register(self, step_type: str, handler: Callable):
        self.handlers[step_type] = handler

    def build(self, workflow_id: str, definition: dict) -> Workflow:
        steps = []
        for i, s in enumerate(definition.get("steps", [])):
            steps.append(WorkflowStep(
                id=f"{workflow_id}_{i}",
                type=s.get("type", ""),
                config=s.get("config", {}),
                label=s.get("label", s.get("type", "")),
            ))
        wf = Workflow(id=workflow_id, name=definition.get("name", ""), steps=steps)
        self._active[workflow_id] = wf
        self._results[workflow_id] = []
        return wf

    async def execute(self, workflow_id: str, context: dict) -> list:
        wf = self._active.get(workflow_id)
        if not wf:
            return [{"error": "workflow not found"}]

        wf.status = "running"
        results = []

        for i, step in enumerate(wf.steps):
            wf.current_step = i
            step.status = "running"
            try:
                handler = self.handlers.get(step.type)
                if handler:
                    result = await handler(step.config, context, results)
                    step.status = "completed"
                    results.append({"step": step.label, "result": result, "id": step.id})
                else:
                    step.status = "failed"
                    results.append({"step": step.label, "error": f"no handler for {step.type}", "id": step.id})
            except Exception as e:
                step.status = "failed"
                results.append({"step": step.label, "error": str(e), "id": step.id})

        wf.status = "completed"
        self._results[workflow_id] = results
        return results

    def get_status(self, workflow_id: str) -> dict | None:
        wf = self._active.get(workflow_id)
        if not wf:
            return None
        return {
            "id": wf.id,
            "name": wf.name,
            "status": wf.status,
            "currentStep": wf.current_step,
            "steps": [{"id": s.id, "label": s.label, "type": s.type, "status": s.status} for s in wf.steps],
            "results": self._results.get(workflow_id, []),
        }


engine = WorkflowEngine()
