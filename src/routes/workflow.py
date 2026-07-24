import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.graph_store import get_store
from core.workflow_agent import generate_workflow
from core.workflow_engine import engine as wf_engine
from data.json_store import json_store

router = APIRouter(tags=["workflow"])


class WorkflowGenerateRequest(BaseModel):
    intent: str = ""


class WorkflowExecuteRequest(BaseModel):
    params: dict = {}


@router.post("/books/{book_id}/workflow/generate")
def generate_wf(book_id: str, data: WorkflowGenerateRequest):
    intent = data.intent
    if not intent:
        raise HTTPException(400, "intent required")

    kb = get_store(book_id)
    entities = kb.list_entities()
    context = "\n".join([f"[{e.type}] {e.name}" for e in entities])

    definition = generate_workflow(intent, context)
    wf_id = str(int(datetime.now().timestamp() * 1000))
    wf = wf_engine.build(wf_id, definition)

    # Persist
    json_store.add_workflow(
        book_id, wf.name, [{"id": s.id, "type": s.type, "label": s.label, "config": s.config} for s in wf.steps]
    )

    return {
        "id": wf.id,
        "name": wf.name,
        "steps": [{"id": s.id, "type": s.type, "label": s.label, "config": s.config} for s in wf.steps],
    }


@router.get("/books/{book_id}/workflows")
def list_workflows(book_id: str):
    return json_store.load_workflows(book_id)


@router.get("/workflows")
def browse_workflows():
    """Browse all global workflows (for subscribing)."""
    return json_store.load_workflows_global()


@router.post("/books/{book_id}/workflow-subs")
def subscribe_workflow(book_id: str, data: dict):
    json_store.subscribe_workflow(book_id, data["workflow_id"])
    return {"ok": True}


@router.delete("/books/{book_id}/workflow-subs/{wf_id}")
def unsubscribe_workflow(book_id: str, wf_id: str):
    json_store.unsubscribe_workflow(book_id, wf_id)
    return {"ok": True}


@router.delete("/books/{book_id}/workflows/{wf_id}")
def delete_workflow(book_id: str, wf_id: str):
    json_store.delete_workflow(book_id, wf_id)
    return {"ok": True}


@router.delete("/workflows/{wf_id}")
def delete_global_workflow(wf_id: str):
    """Delete a workflow from the global pool and clean up all project subscriptions."""
    json_store.delete_workflow("_global", wf_id)
    # Clean up subscriptions across all books
    try:
        import glob as glob_mod
        import os

        data_dir = json_store.DATA_DIR if hasattr(json_store, "DATA_DIR") else None
        if data_dir and os.path.isdir(data_dir):
            for sub_file in glob_mod.glob(str(data_dir / "workflow_subs_*.json")):
                book_id = os.path.basename(sub_file).replace("workflow_subs_", "").replace(".json", "")
                try:
                    subs = json_store.load_workflow_subs(book_id)
                    if wf_id in subs:
                        subs = [s for s in subs if s != wf_id]
                        json_store.save_workflow_subs(book_id, subs)
                except Exception:
                    pass
    except Exception:
        pass
    return {"ok": True}


@router.post("/books/{book_id}/workflow/{wf_id}/execute")
async def execute_wf(book_id: str, wf_id: str, data: WorkflowExecuteRequest | None = None):
    async def event_generator():
        # Merge dynamic params into context
        dynamic_params = (data.params if data else {}) or {}
        context = {"book_id": book_id, **dynamic_params}

        wf = wf_engine._active.get(wf_id)
        if not wf:
            # Try to rebuild from storage
            try:
                wf_data = json_store.get_workflow(wf_id)
                wf = wf_engine.build(wf_id, {"name": wf_data.get("name", "工作流"), "steps": wf_data.get("steps", [])})
            except Exception:
                yield {"event": "error", "data": json.dumps({"message": "workflow not found"}, ensure_ascii=False)}
                return

        wf.status = "running"
        results = []
        for i, step in enumerate(wf.steps):
            wf.current_step = i
            step.status = "running"
            yield {
                "event": "step_start",
                "data": json.dumps({"step": step.label, "index": i, "type": step.type}, ensure_ascii=False),
            }
            try:
                handler = wf_engine.handlers.get(step.type)
                if handler:
                    result = await handler(step.config, context, results)
                    step.status = "completed"
                    results.append({"step": step.label, "result": result, "id": step.id})
                    yield {
                        "event": "step_done",
                        "data": json.dumps({"step": step.label, "result": result}, ensure_ascii=False),
                    }
                else:
                    step.status = "failed"
                    results.append({"step": step.label, "error": f"no handler for {step.type}", "id": step.id})
                    yield {
                        "event": "step_error",
                        "data": json.dumps(
                            {"step": step.label, "error": f"no handler: {step.type}"}, ensure_ascii=False
                        ),
                    }
            except Exception as e:
                step.status = "failed"
                results.append({"step": step.label, "error": str(e), "id": step.id})
                yield {
                    "event": "step_error",
                    "data": json.dumps({"step": step.label, "error": str(e)[:200]}, ensure_ascii=False),
                }

        wf.status = "completed"
        wf_engine._results[wf_id] = results
        yield {"event": "done", "data": json.dumps({"results": results}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.get("/books/{book_id}/workflow/{wf_id}")
def get_wf_status(book_id: str, wf_id: str):
    status = wf_engine.get_status(wf_id)
    if not status:
        raise HTTPException(404, "workflow not found")
    return status
