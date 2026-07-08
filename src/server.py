# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import config
from core.errors import register_error_handlers
from core.headless_loop import init_task_runner
from core.scheduler import engine as sched_engine
from core.task_queue import task_queue
from core.workflow_engine import engine as wf_engine
from routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Configure centralized logging ──
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # File handler with rotation (10MB per file, keep 5 files)
    file_handler = RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)

    # Silence noisy loggers that drown out actionable signal in server.log.
    # neo4j.notifications spams "index already exists" on every schema init;
    # httpx logs every HTTP request as INFO. Demote them so real warnings /
    # errors (agent_loop, tool failures, exceptions) stay visible.
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Server starting up with centralized logging")

    # ── Startup ──
    sched_engine.start()

    # Initialize task runner
    task_runner = init_task_runner(task_queue)

    # Start supervisor (will be imported after task_runner is ready)
    supervisor = None
    try:
        from core.supervisor import supervisor as _sup
        _sup.set_runner(task_runner, task_queue)
        _sup.start()
        supervisor = _sup
        # Wire activity tracking: TASK_STEP_COMPLETED → supervisor.record_activity
        from core.event_bus import EventType, bus
        def _activity_listener(event):
            tid = event.data.get("task_id")
            if tid:
                _sup.record_activity(tid)
        bus.on(EventType.TASK_STEP_COMPLETED, _activity_listener)
        bus.on(EventType.HEADLESS_LOOP_PROGRESS, _activity_listener)
        # Wire narrative auto-check: chapter tools → constraint check
        import core.narrative_events  # noqa: F401 — side-effect import registers event listener
    except (ImportError, AttributeError) as e:
        logging.getLogger(__name__).warning("Supervisor not available: %s", e)

    # Recover interrupted tasks in background
    import asyncio
    asyncio.create_task(_recover_tasks(task_runner))

    # Background stale session cleanup
    asyncio.create_task(_cleanup_stale_sessions())

    yield

    # ── Shutdown ──
    if supervisor:
        supervisor.stop()

    # Cancel any running task runner tasks
    for _tid, atask in list(task_runner._running.items()):
        if not atask.done():
            atask.cancel()

    sched_engine.stop()
    from core.graph_store import close_shared_driver
    close_shared_driver()

    from core.thread_pools import shutdown_pools
    shutdown_pools()


async def _recover_tasks(task_runner):
    """Recover interrupted tasks after a short startup delay."""
    import asyncio
    await asyncio.sleep(3)  # Let server fully start first
    try:
        await task_runner.recover_pending_tasks()
    except Exception as e:
        logging.getLogger(__name__).warning("Task recovery failed: %s", e)


async def _cleanup_stale_sessions():
    """Periodically release sessions that have been stuck for too long."""
    import asyncio

    from core.session_state import run_state as ss
    await asyncio.sleep(10)
    while True:
        try:
            released = ss.release_stale()
            if released:
                logging.getLogger(__name__).info("Released %d stale sessions: %s", len(released), released)
        except Exception as e:
            logging.getLogger(__name__).warning("Stale session cleanup error: %s", e)
        await asyncio.sleep(60)


app = FastAPI(title="小说写作辅助 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def delete_confirmation_middleware(request: Request, call_next):
    """Require X-Confirm-Delete header for all DELETE requests.
    This prevents accidental deletion via REST API — the frontend
    must explicitly send 'X-Confirm-Delete: true' to confirm.
    Maps DELETE routes to the same permission checks used by Agent tools.
    """
    if request.method == "DELETE":
        confirm = request.headers.get("X-Confirm-Delete", "")
        if confirm.lower() != "true":
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "DELETE 操作需要确认。请发送 X-Confirm-Delete: true 请求头。",
                    "required_header": "X-Confirm-Delete: true",
                },
            )
    return await call_next(request)

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

register_error_handlers(app)
app.include_router(api_router)


# --- Workflow step handlers ---

def _mk_ctx(cfg, ctx):
    """Create shared execution context: (loop, book_id, kb)."""
    import asyncio

    from core.graph_store import GraphStore
    loop = asyncio.get_event_loop()
    book_id = ctx.get("book_id", "")
    kb = GraphStore(book_id)
    kb.init_schema()
    return loop, book_id, kb


async def _handle_extract(cfg, ctx, results):
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    text = ctx.get("text") or cfg.get("text", "")
    if not text:
        last_write = next((r for r in results if r.get("result") and isinstance(r["result"], dict)), None)
        if last_write:
            text = last_write["result"].get("text", "")
    result = await execute_tool(loop, "extract_knowledge", {"text": text}, kb, book_id, text)
    return {"message": result}


async def _handle_write(cfg, ctx, results):
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    instruction = ctx.get("instruction") or cfg.get("instruction", cfg.get("text", ""))
    chapter_title = ctx.get("chapter_title", cfg.get("chapter_title", ""))
    ref_chapters = ctx.get("ref_chapters", cfg.get("ref_chapters", []))
    tool_args = {"instruction": instruction}
    if chapter_title:
        tool_args["chapter_title"] = chapter_title
    if ref_chapters:
        tool_args["ref_chapters"] = ref_chapters
    result = await execute_tool(loop, "write_chapter", tool_args, kb, book_id, instruction)
    return {"message": result}


async def _handle_validate(cfg, ctx, results):
    last_write = next((r for r in results if r.get("step") == "AI写作"), None)
    text = cfg.get("text") or (last_write.get("result", {}).get("text", "") if last_write else "")
    return {"type": "validate", "text": text or "(无内容可校验)"}


async def _handle_review(cfg, ctx, results):
    return {"type": "review", "message": cfg.get("message", "请确认是否继续"), "results_so_far": len(results)}


async def _handle_read(cfg, ctx, results):
    """Read chapter content (supports reference book chapters)."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {"chapter_id": cfg.get("chapter_id", "")}
    ref_book_id = cfg.get("ref_book_id", "")
    if ref_book_id:
        tool_args["ref_book_id"] = ref_book_id
    result = await execute_tool(loop, "read_chapter", tool_args, kb, book_id, tool_args["chapter_id"])
    ctx["_last_chapter_text"] = result
    ctx["_last_chapter_id"] = tool_args["chapter_id"]
    return {"text": result[:500] + ("..." if len(result) > 500 else ""), "chars": len(result)}


async def _handle_decompose(cfg, ctx, results):
    """Decompose chapter into plot chain."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {}
    chapter_id = cfg.get("chapter_id", ctx.get("_last_chapter_id", ""))
    ref_book_id = cfg.get("ref_book_id", "")
    if chapter_id:
        tool_args["chapter_id"] = chapter_id
    if ref_book_id:
        tool_args["ref_book_id"] = ref_book_id
    if "_last_chapter_text" in ctx and chapter_id:
        tool_args["chapter_text"] = ctx["_last_chapter_text"]
    result = await execute_tool(loop, "decompose_chapter", tool_args, kb, book_id, "")
    import re
    chain_match = re.search(r'chain_id["\s:]+([a-zA-Z0-9_-]+)', result)
    if chain_match:
        ctx["_last_chain_id"] = chain_match.group(1)
    return {"message": result[:500] + ("..." if len(result) > 500 else ""), "full": result}


async def _handle_annotate(cfg, ctx, results):
    """Annotate plot chain (preview or set edit modes)."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {}
    chain_id = cfg.get("chain_id", ctx.get("_last_chain_id", ""))
    if chain_id:
        tool_args["chain_id"] = chain_id
    preview = cfg.get("preview", False)
    if preview:
        tool_args["preview"] = True
    annotations = cfg.get("annotations", [])
    if annotations:
        tool_args["annotations"] = annotations
    result = await execute_tool(loop, "annotate_chain", tool_args, kb, book_id, "")
    return {"message": result[:800] + ("..." if len(result) > 800 else ""), "full": result}


async def _handle_rewrite(cfg, ctx, results):
    """Rewrite chapter by plot chain."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {}
    chain_id = cfg.get("chain_id", ctx.get("_last_chain_id", ""))
    if chain_id:
        tool_args["chain_id"] = chain_id
    chapter_title = cfg.get("chapter_title", "")
    if chapter_title:
        tool_args["chapter_title"] = chapter_title
    style_profile = cfg.get("style_profile", "")
    if style_profile:
        tool_args["style_profile"] = style_profile
    result = await execute_tool(loop, "rewrite_by_chain", tool_args, kb, book_id, "")
    return {"message": result[:500] + ("..." if len(result) > 500 else ""), "full": result}


async def _handle_ask_user(cfg, ctx, results):
    """Structured user confirmation with questions/options."""
    return {
        "type": "ask_user",
        "question": cfg.get("question", ""),
        "options": cfg.get("options", []),
        "questions": cfg.get("questions", []),
    }


async def _handle_search(cfg, ctx, results):
    """Search knowledge base."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    query = cfg.get("query", "")
    result = await execute_tool(loop, "search_knowledge", {"query": query}, kb, book_id, query)
    return {"message": result}


async def _handle_compare_plot(cfg, ctx, results):
    """Compare plot between two texts/chapters."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {"text_a": cfg.get("text_a", ""), "text_b": cfg.get("text_b", "")}
    result = await execute_tool(loop, "compare_plot", tool_args, kb, book_id, "")
    return {"message": result[:800] + ("..." if len(result) > 800 else "")}


async def _handle_diff(cfg, ctx, results):
    """Version diff between chapters."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    tool_args = {"chapter_a": cfg.get("chapter_a", ""), "chapter_b": cfg.get("chapter_b", "")}
    result = await execute_tool(loop, "diff_chapters", tool_args, kb, book_id, "")
    return {"message": result[:800] + ("..." if len(result) > 800 else "")}


async def _handle_generate_outline(cfg, ctx, results):
    """Generate chapter outline."""
    loop, book_id, kb = _mk_ctx(cfg, ctx)
    from tools.executor import execute_tool
    instruction = cfg.get("instruction", ctx.get("instruction", "生成大纲"))
    result = await execute_tool(loop, "generate_outline", {"instruction": instruction}, kb, book_id, instruction)
    return {"message": result[:500] + ("..." if len(result) > 500 else "")}


wf_engine.register("extract", _handle_extract)
wf_engine.register("write", _handle_write)
wf_engine.register("validate", _handle_validate)
wf_engine.register("review", _handle_review)
wf_engine.register("edit", _handle_validate)
wf_engine.register("plan", _handle_review)
# New step types for high-fidelity rewrite and other workflows
wf_engine.register("read", _handle_read)
wf_engine.register("decompose", _handle_decompose)
wf_engine.register("annotate", _handle_annotate)
wf_engine.register("rewrite", _handle_rewrite)
wf_engine.register("ask_user", _handle_ask_user)
wf_engine.register("search", _handle_search)
wf_engine.register("compare_plot", _handle_compare_plot)
wf_engine.register("diff", _handle_diff)
wf_engine.register("generate_outline", _handle_generate_outline)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.server.host, port=config.server.port, timeout_keep_alive=300, log_level="info")
