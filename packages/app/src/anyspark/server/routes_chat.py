"""
anyspark.server.routes_chat — 聊天主路由（S80c 从 app.py 搬移；S207 拆出 queue/stats/aux）。

chat / chat_stream（SSE）/ cancel / steer / records。
依赖最重：deps.model / store / chapters / models / recorder / active_* / bg_queue / db_path。
queue/stats/aux 已拆到 routes_chat_{queue,stats,aux}.py。
"""

from __future__ import annotations

import json
import queue
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from anyspark.align import parse_agency_declaration
from anyspark.core import Agent, CancellationToken
from anyspark.server.agent_factory import make_agent
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    DEFAULT_SYSTEM,
    CancelIn,
    ChatRequest,
    ChatResponse,
    SteerIn,
    ToolEvent,
    _now_iso_rec,
    _sse_frame,
)

# S99 第二步：单连接接力执行的最大轮数（防队列无限消费失控；超限剩余队列保留）
MAX_QUEUE_ROUNDS = 20


def make_chat_router(deps: AppDeps) -> APIRouter:
    """聊天路由（依赖：deps.model / deps.store / deps.models / deps.chapters /
    deps.recorder / deps.active_* / deps.bg_queue / deps.db_path）。"""
    router = APIRouter()

    @router.post("/api/chat/cancel")
    def cancel_chat(
        req: Annotated[CancelIn, Body()],
    ) -> dict[str, bool | str]:
        """协作式取消（S21）：中断正在跑的 Agent 循环（下个检查点生效）。

        conversation_id 为空时取消最近活跃的会话（新会话 id 由服务端生成，客户端未知）。
        """
        token = None
        if req.conversation_id:
            token = deps.active_tokens.get(req.conversation_id)
        elif deps.active_tokens:
            token = next(reversed(deps.active_tokens.values()), None)
        if token is not None:
            token.cancel()
            return {"ok": True}
        return {"ok": False, "reason": "会话未在运行"}

    @router.post("/api/chat/steer")
    def steer_chat(req: Annotated[SteerIn, Body()]) -> dict[str, bool | str]:
        """S25：运行中插话（对齐 pi Agent.steer）——消息在当前轮工具结果后、
        下一轮 LLM 前注入，写作时可中途说"别写太血腥"而不用取消重来。
        conversation_id 为空时取最近活跃会话（新会话 id 客户端可先于 turn_start 帧获得）。"""
        with deps.active_lock:
            if req.conversation_id:
                agent = deps.active_agents.get(req.conversation_id)
            elif deps.active_agents:
                agent = next(reversed(deps.active_agents.values()), None)
            else:
                agent = None
        if agent is None:
            return {"ok": False, "reason": "会话未在运行"}
        agent.steer(req.message)
        logger.info("steer 注入: msg=%s", req.message[:40])
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S116 会话运行记录查询（事件溯源：轮快照 + 系统事件回放）
    # -----------------------------------------------------------------------
    @router.get("/api/records/{conv_id}")
    def get_records(conv_id: str, limit: int = 500) -> dict[str, Any]:
        """S116：读取会话运行记录（data/records/<conv>/events.jsonl）。

        返回 {ok, meta, events: [...]}——轮快照（event=record）与系统事件
        （event=context_compressed/steering_injected/...）按时间顺序，
        供前端回放面板展示"模型当时看到了什么 + 谁改了什么"。
        """
        import json as _json

        meta: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        sdir = deps.recorder.session_dir(conv_id)
        mf = sdir / "meta.json"
        if mf.exists():
            try:
                meta = _json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        ef = sdir / "events.jsonl"
        if ef.exists():
            with ef.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(_json.loads(line))
                    except Exception:
                        continue
        return {"ok": True, "conv_id": conv_id, "meta": meta, "events": events[-limit:]}

    # -----------------------------------------------------------------------
    # S99 会话消息队列（排队接力第一步——排队/查看/删/转插入；自动消费=第二步）
    # -----------------------------------------------------------------------
    @router.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        # S47 请求级指定模型：不存在 → 400（不是 500）
        if req.model_id and deps.models.get(req.model_id) is None:
            raise HTTPException(status_code=400, detail=f"模型配置不存在: {req.model_id}")
        # steering 防护（S21）：会话正在处理中时拒绝并发新消息，提示等待/取消
        if req.conversation_id and req.conversation_id in deps.active_tokens:
            raise HTTPException(
                status_code=409,
                detail="该会话正在处理中（可 POST /api/chat/cancel 中断后再发）",
            )
        logger.info("chat 请求: conv=%s len=%d", req.conversation_id or "(新)", len(req.message))
        events: list[ToolEvent] = []
        agent = make_agent(
            deps,
            req.system_prompt or DEFAULT_SYSTEM,
            req.temperature,
            book_id=req.book_id,
            agency_level=req.agency_level,
            enable_search=req.enable_search,
            enable_extras=req.enable_extras,
            enable_domain=req.enable_domain,
            enable_codex=req.enable_codex,
            enable_workflow=req.enable_workflow,
            enable_play=req.enable_play,
            skip_inject=set(req.skip_inject),
            context_mode=req.context_mode,
            model_id=req.model_id,
            thinking=req.thinking,
            # S61：本轮用户消息作为心智披露的上下文（按相关动态选取）
            context=req.message,
        )
        agent.events.on(
            "tool_call", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        agent.events.on(
            "tool_result", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        # 工具调用/结果写日志（排查用）
        agent.events.on("tool_call", lambda e: logger.info("工具调用: %s", e.payload.get("name")))
        agent.events.on(
            "tool_result",
            lambda e: logger.info(
                "工具结果: %s ok=%s content=%s",
                e.payload.get("name"),
                e.payload.get("ok"),
                (e.payload.get("content") or "")[:200],
            ),
        )

        # 无会话时显式创建，保证 conversation_id 可回传（多轮续写）
        conv_id = req.conversation_id
        if not conv_id:
            conv = agent.store.create(book_id=req.book_id)  # S80：会话绑定项目
            conv_id = conv.id

        # S49 运行记录：完整上下文+思维链落 data/records/<conv>/（修 bug/训练素材）
        deps.recorder.attach(
            agent,
            conv_id,
            {
                "ts": _now_iso_rec(),
                "endpoint": "chat",
                "model": getattr(deps.model, "model_name", "?"),
                "temperature": req.temperature,
                "agency_level": req.agency_level,
                "enable_domain": req.enable_domain,
                "enable_codex": req.enable_codex,
                "enable_workflow": req.enable_workflow,
                "enable_play": req.enable_play,
                "thinking": req.thinking,
                "model_id": req.model_id,
            },
        )
        # 协作式取消（S21 移植 pi 的 AbortSignal）：注册 token，/api/chat/cancel 可中断
        token = CancellationToken()
        deps.active_tokens[conv_id] = token
        with deps.active_lock:
            deps.active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
        try:
            turn = agent.run(req.message, conv_id, token)
        except Exception as exc:  # 记录并返回 500
            logger.exception("chat 执行异常: %s", exc)
            raise HTTPException(status_code=500, detail=f"执行失败: {exc}") from exc
        finally:
            deps.active_tokens.pop(conv_id, None)
            with deps.active_lock:
                deps.active_agents.pop(conv_id, None)
        if turn.error is not None:  # S22：模型调用失败/迭代上限（不再字符串匹配）
            logger.warning("chat 非正常结束: conv=%s error=%s", conv_id, turn.error)
            raise HTTPException(status_code=500, detail=turn.error)

        logger.info(
            "chat 完成: conv=%s 输出%d字 工具%d次",
            conv_id,
            len(turn.text),
            len(turn.tool_calls),
        )
        # S53c ② 归档后分析：会话结束后台摘要成场景记忆（不阻塞响应）
        deps.bg_queue.put(BgTask(kind="summarize", conv_id=conv_id))
        # 会话结束：信号 → 偏好提炼（增量游标，后台；无信号时零成本返回）
        deps.bg_queue.put(BgTask(kind="refine"))
        # 图谱抽取：写入章节后自动抽取入库（后台任务，不阻塞响应；失败不影响写作）
        # extract_graph 开关（S15）：默认开保持现状，可关省 token（手动 /api/graph/extract 兜底）
        if req.extract_graph:
            for wc in turn.tool_calls:
                if wc.name == "write_chapter":
                    title = str(wc.arguments.get("title", "")).strip()
                    content = str(wc.arguments.get("content", ""))
                    # S216：意图模式（C 架构）content 为空——正文由写作引擎生成后落盘，
                    # 从已落盘章节读取（否则意图模式 write_chapter 不触发图谱抽取）
                    if title and not content:
                        ch = next(
                            (
                                c
                                for c in deps.chapters.list_by_book(req.book_id)
                                if c.title == title
                            ),
                            None,
                        )
                        if ch:
                            content = ch.content
                    if title and content:
                        chs = deps.chapters.list_by_book(req.book_id)
                        order = next((c.order_index for c in chs if c.title == title), len(chs))
                        logger.info("后台图谱抽取挂载: 《%s》", title)
                        line = str(wc.arguments.get("line", "main")).strip() or "main"
                        deps.bg_queue.put(
                            BgTask(
                                kind="chapter",
                                title=title,
                                content=content,
                                order=order,
                                line=line,
                                book_id=req.book_id,
                            )
                        )
        turns_payload = [{"text": turn.text, "tool_calls": [c.name for c in turn.tool_calls]}]
        # AI 档位声明解析（机制 2：AI 可声明，用户点选确认）
        declared = parse_agency_declaration(turn.text)
        return ChatResponse(
            conversation_id=conv_id,
            text=turn.text,
            turns=turns_payload,
            events=events,
            agency_declared=declared,
        )

    @router.post("/api/chat/stream")
    def chat_stream(req: ChatRequest) -> StreamingResponse:
        """SSE 流式：turn_start / text_delta / tool_call / tool_result / done / error。

        S8（模型局限弥补 + A 类硬编码 SSE 传输）：长文生成逐字流式，用户不等全量。
        事件帧格式：event: <type>\ndata: <json>\n\n（core 事件协议 → 传输层）。
        """
        events_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        # S82：本轮 parts 累积（tool_call 卡片 + reasoning 思考过程）——done 帧附带给前端 attach
        parts_acc: list[dict[str, Any]] = []
        # S99：token 消耗累积（每轮 record 的 usage 相加）——done 帧带给前端展示
        usage_acc: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        def run_agent(agent: Agent, first_msg: str, conv_id: str) -> None:
            """S99 第二步：SSE 循环化接力——单连接跑完整条队列，队列空才发 stream_end。

            cancel 只停当前轮（token 中断后不消费队列 → 队列保留）；
            每轮结束照常挂后台摘要 + 图谱抽取（接力轮同样挂载）。
            """
            try:
                token = CancellationToken()
                deps.active_tokens[conv_id] = token
                with deps.active_lock:
                    deps.active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
                rounds = 0
                try:
                    msg = first_msg
                    while True:
                        if rounds >= MAX_QUEUE_ROUNDS:
                            logger.warning(
                                "queue 接力达上限 %d 轮，剩余队列保留: conv=%s",
                                MAX_QUEUE_ROUNDS,
                                conv_id,
                            )
                            break
                        rounds += 1
                        turn = agent.run(msg, conv_id, token)
                        # S53c ② 归档后分析：每轮结束后台摘要成场景记忆（不阻塞 SSE）
                        deps.bg_queue.put(BgTask(kind="summarize", conv_id=conv_id))
                        # 每轮结束：信号 → 偏好提炼（增量游标，后台；无信号零成本）
                        deps.bg_queue.put(BgTask(kind="refine"))
                        # 图谱抽取：与 /api/chat 行为一致（write_chapter 落盘后自动抽取）
                        # extract_graph 开关（S15）：默认开保持现状，可关省 token
                        if req.extract_graph:
                            for wc in turn.tool_calls:
                                if wc.name == "write_chapter":
                                    title = str(wc.arguments.get("title", "")).strip()
                                    content = str(wc.arguments.get("content", ""))
                                    # S216：意图模式 content 为空→从落盘章节读取
                                    if title and not content:
                                        ch = next(
                                            (
                                                c
                                                for c in deps.chapters.list_by_book(req.book_id)
                                                if c.title == title
                                            ),
                                            None,
                                        )
                                        if ch:
                                            content = ch.content
                                    if title and content:
                                        chs = deps.chapters.list_by_book(req.book_id)
                                        order = next(
                                            (c.order_index for c in chs if c.title == title),
                                            len(chs),
                                        )
                                        # 后台队列处理（不阻塞 SSE 的 done 帧）
                                        line = (
                                            str(wc.arguments.get("line", "main")).strip() or "main"
                                        )
                                        deps.bg_queue.put(
                                            BgTask(
                                                kind="chapter",
                                                title=title,
                                                content=content,
                                                order=order,
                                                line=line,
                                                book_id=req.book_id,
                                            )
                                        )
                                        logger.info(
                                            "SSE debug: 已挂抽取 title=%r order=%d",
                                            title,
                                            order,
                                        )
                        # 取消只停当前轮：不消费队列（队列保留，前端队列条仍可见）
                        if token.is_cancelled():
                            logger.info("queue 接力被取消: conv=%s 已跑%d轮", conv_id, rounds)
                            break
                        # 消费队列下一条（FIFO；队列空则结束本轮连接）
                        with deps.queue_lock:
                            items = deps.conv_queues.get(conv_id, [])
                            if items:
                                nxt = items.pop(0)
                                if items:
                                    deps.conv_queues[conv_id] = items
                                else:
                                    deps.conv_queues.pop(conv_id, None)
                            else:
                                nxt = None
                        if nxt is None:
                            break
                        msg = nxt["text"]
                        remaining = len(items) if items else 0
                        events_queue.put(("queue_consume", {"text": msg, "remaining": remaining}))
                finally:
                    deps.active_tokens.pop(conv_id, None)
                    with deps.active_lock:
                        deps.active_agents.pop(conv_id, None)
                events_queue.put(("stream_end", {"rounds": rounds}))
            except Exception as exc:  # 异常转 error 帧（不中断连接）
                logger.exception("chat/stream 执行异常: %s", exc)
                events_queue.put(("error", {"message": f"执行失败: {exc}"}))

        def gen() -> Any:
            # S47 请求级指定模型：不存在 → 400（SSE 里转 error 帧）
            if req.model_id and deps.models.get(req.model_id) is None:
                events_queue.put(("error", {"message": f"模型配置不存在: {req.model_id}"}))
                yield (
                    "event: error\n"
                    + f"data: {json.dumps({'message': f'模型配置不存在: {req.model_id}'})}\n\n"
                )
                return
            agent = make_agent(
                deps,
                req.system_prompt or DEFAULT_SYSTEM,
                req.temperature,
                book_id=req.book_id,
                agency_level=req.agency_level,
                enable_search=req.enable_search,
                enable_extras=req.enable_extras,
                enable_domain=req.enable_domain,
                enable_codex=req.enable_codex,
                enable_workflow=req.enable_workflow,
                enable_play=req.enable_play,
                skip_inject=set(req.skip_inject),
                context_mode=req.context_mode,
                model_id=req.model_id,
                thinking=req.thinking,
                # S61：本轮用户消息作为心智披露的上下文
                context=req.message,
            )
            conv_id = req.conversation_id
            if not conv_id:
                conv = agent.store.create(book_id=req.book_id)  # S80：会话绑定项目
                conv_id = conv.id

            # S49 运行记录（流式）
            deps.recorder.attach(
                agent,
                conv_id,
                {
                    "ts": _now_iso_rec(),
                    "endpoint": "chat_stream",
                    "model": getattr(deps.model, "model_name", "?"),
                    "temperature": req.temperature,
                    "agency_level": req.agency_level,
                    "enable_domain": req.enable_domain,
                    "enable_codex": req.enable_codex,
                    "enable_workflow": req.enable_workflow,
                    "enable_play": req.enable_play,
                    "thinking": req.thinking,
                    "model_id": req.model_id,
                },
            )

            def on_event(e: Any) -> None:
                payload = e.payload
                # S25：turn_start 帧带 conversation_id——客户端尽早知道会话 id，运行中可 steer
                if e.type == "turn_start":
                    payload = {**payload, "conversation_id": conv_id}
                elif e.type == "record":
                    # S82：S49 record 帧不进 SSE（含完整 prompt 过大），只提取 reasoning 入 parts
                    out = payload.get("output") or {}
                    reasoning = str(out.get("reasoning") or "").strip()
                    if reasoning:
                        parts_acc.append({"type": "reasoning", "text": reasoning})
                    # S99：累积 token 消耗（模型适配器上报的 usage）
                    usage = out.get("usage")
                    if isinstance(usage, dict):
                        for k in usage_acc:
                            v = usage.get(k)
                            if isinstance(v, (int, float)):
                                usage_acc[k] += int(v)
                    return
                elif e.type == "done":
                    # S99：agent 层单轮完成不转发——连接结束由 stream_end 帧决定
                    return
                elif e.type == "tool_call":
                    # S82：带 arguments 的工具调用卡片（name[] + arguments[] zip）
                    names = payload.get("name") or []
                    args = payload.get("arguments") or []
                    for i, n in enumerate(names):
                        parts_acc.append(
                            {
                                "type": "tool_call",
                                "name": n,
                                "arguments": args[i] if i < len(args) else {},
                            }
                        )
                events_queue.put((e.type, payload))

            # S21 流式核心：Agent 内部流式（model.respond_stream），
            # text_delta/reasoning_delta 事件转 SSE 帧
            agent.events.on("text_delta", lambda e: events_queue.put(("text_delta", e.payload)))
            # S213：思考增量实时转发 SSE——避免思考期静默致前端 idle 超时误杀
            # （对齐 pi thinking_delta）
            agent.events.on(
                "reasoning_delta",
                lambda e: events_queue.put(("reasoning_delta", e.payload)),
            )
            for t in (
                "turn_start",
                "text",
                "tool_call",
                "tool_execution_start",  # S25：前端显示"正在执行…"
                "tool_execution_end",  # S25：前端显示耗时/结果
                "tool_result",
                "record",  # S82：仅供内部提取 reasoning（on_event 内 return，不转发 SSE）
                "done",
                "error",
            ):
                agent.events.on(t, on_event)
            # Agent 循环在线程跑，事件经 queue 转 SSE 帧（同步生成器流式输出）
            threading.Thread(
                target=run_agent, args=(agent, req.message, conv_id), daemon=True
            ).start()
            while True:
                try:
                    # S214：活动感知 idle 超时——思考期现在有 reasoning_delta 持续流，
                    # get 不断被重置；仅真正无任何事件 180s 才报错（对齐 pi bodyTimeout：
                    # 不因思考时长杀流，只对真卡死兑底。与前端 IDLE_STREAM_TIMEOUT_MS 对齐）
                    etype, payload = events_queue.get(timeout=180)
                except queue.Empty:
                    yield _sse_frame("error", {"message": "流式超时（180s 无事件，模型可能卡死）"})
                    break
                if etype == "stream_end":
                    # S99 第二步：整条队列跑完（或取消/超限）才发最终 done 帧
                    done_payload: dict[str, Any] = {
                        "conversation_id": conv_id,
                        "rounds": int(payload.get("rounds", 1)),
                        # S100：模型名——前端按模型定价估算成本（pro 3/6 元，
                        # flash 1/2 元每百万 token）
                        "model": getattr(deps.model, "model_name", "?"),
                    }
                    if parts_acc:
                        done_payload["parts"] = parts_acc
                    # S99：token 消耗汇总（前端 RunLedger 展示）
                    if any(usage_acc.values()):
                        done_payload["token_usage"] = usage_acc
                    yield _sse_frame("done", done_payload)
                    break
                if etype == "error":
                    yield _sse_frame("error", payload)
                    break
                yield _sse_frame(etype, payload)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
