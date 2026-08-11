"""
anyspark.server.routes_chat — 聊天路由（S80c 拆分，从 app.py 搬移）。

chat / chat_stream（SSE）/ cancel / steer / stats / direction / candidates / rewrite。
依赖最重：deps.model / store / chapters / models / recorder / active_* / bg_queue / db_path。
"""

from __future__ import annotations

import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse

from anyspark.align import parse_agency_declaration
from anyspark.core import Agent, CancellationToken, Message
from anyspark.models import DeepSeekModel
from anyspark.server.agent_factory import make_agent
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    DEFAULT_SYSTEM,
    CancelIn,
    CandidatesIn,
    ChatRequest,
    ChatResponse,
    DirectionIn,
    RewriteIn,
    SteerIn,
    ToolEvent,
    _now_iso_rec,
    _sse_frame,
)
from anyspark.server.stats import compute_stats


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

    @router.get("/api/stats")
    def stats() -> dict[str, Any]:
        """T7 验证指标（代理指标，纯 SQL 统计现有表，零新表）：修改率/提问率/完成率。"""
        return compute_stats(deps.db_path)

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
            lambda e: logger.info("工具结果: %s ok=%s", e.payload.get("name"), e.payload.get("ok")),
        )

        # 无会话时显式创建，保证 conversation_id 可回传（多轮续写）
        conv_id = req.conversation_id
        if not conv_id:
            conv = agent.store.create()
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
        # 图谱抽取：写入章节后自动抽取入库（后台任务，不阻塞响应；失败不影响写作）
        # extract_graph 开关（S15）：默认开保持现状，可关省 token（手动 /api/graph/extract 兜底）
        if req.extract_graph:
            for wc in turn.tool_calls:
                if wc.name == "write_chapter":
                    title = str(wc.arguments.get("title", "")).strip()
                    content = str(wc.arguments.get("content", ""))
                    if title and content:
                        chs = deps.chapters.list_by_book("main")
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

        def run_agent(agent: Agent, msg: str, conv_id: str) -> None:
            try:
                token = CancellationToken()
                deps.active_tokens[conv_id] = token
                with deps.active_lock:
                    deps.active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
                try:
                    turn = agent.run(msg, conv_id, token)
                finally:
                    deps.active_tokens.pop(conv_id, None)
                    with deps.active_lock:
                        deps.active_agents.pop(conv_id, None)
                # S53c ② 归档后分析：会话结束后台摘要成场景记忆（不阻塞 SSE done 帧）
                deps.bg_queue.put(BgTask(kind="summarize", conv_id=conv_id))
                # 图谱抽取：与 /api/chat 行为一致（write_chapter 落盘后自动抽取）
                # extract_graph 开关（S15）：默认开保持现状，可关省 token
                if req.extract_graph:
                    for wc in turn.tool_calls:
                        if wc.name == "write_chapter":
                            title = str(wc.arguments.get("title", "")).strip()
                            content = str(wc.arguments.get("content", ""))
                            if title and content:
                                chs = deps.chapters.list_by_book("main")
                                order = next(
                                    (c.order_index for c in chs if c.title == title),
                                    len(chs),
                                )
                                # 后台队列处理（不阻塞 SSE 的 done 帧）
                                line = str(wc.arguments.get("line", "main")).strip() or "main"
                                deps.bg_queue.put(
                                    BgTask(
                                        kind="chapter",
                                        title=title,
                                        content=content,
                                        order=order,
                                        line=line,
                                    )
                                )
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
                conv = agent.store.create()
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
                events_queue.put((e.type, payload))

            # S21 流式核心：Agent 内部流式（model.respond_stream），text_delta 事件转 SSE 帧
            agent.events.on("text_delta", lambda e: events_queue.put(("text_delta", e.payload)))
            for t in (
                "turn_start",
                "text",
                "tool_call",
                "tool_execution_start",  # S25：前端显示"正在执行…"
                "tool_execution_end",  # S25：前端显示耗时/结果
                "tool_result",
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
                    etype, payload = events_queue.get(timeout=120)
                except queue.Empty:
                    yield _sse_frame("error", {"message": "流式超时（120s 无事件）"})
                    break
                if etype == "done":
                    yield _sse_frame("done", {"conversation_id": conv_id})
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

    @router.post("/api/chat/direction", response_model=dict[str, str])
    def chat_direction(req: DirectionIn) -> dict[str, str]:
        """阶段 5 方向声明：AI 只声明"我准备写：…"不写正文（摩擦前置，用户 0.5s 确认）。"""
        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        prompt = (
            "你是小说写作智能体。用户将让你写一段内容。"
            "在动笔前，先输出【方向声明】——一句话说明你准备写什么、怎么切入"
            "（像'我准备写：主角推开钟表铺的门，雨声里老周欲言又止'）。"
            "只输出声明，不要写正文。\n\n"
            f"用户要求：{req.prompt}{ctx}"
        )
        out = deps.model.respond([Message(role="system", content=prompt)], [])
        direction = out.text.strip()
        if not direction.startswith("【方向声明】"):
            direction = f"【方向声明】{direction}"
        return {"direction": direction}

    @router.post("/api/chat/candidates", response_model=dict[str, object])
    def chat_candidates(req: CandidatesIn) -> dict[str, object]:
        """候选卡堆：并行生成 N 个差异化候选（上下文隔离→真多样性，机制 1/4）。"""
        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        n = max(2, min(4, req.n))
        styles = ["平实叙事", "强画面感", "悬念张力", "细腻心理"]

        def _one(i: int) -> str:
            prompt = (
                f"你是小说写作智能体。按风格「{styles[i % len(styles)]}」写下面要求的一段正文"
                f"（约 150-250 字，直接输出正文，不要解释）。\n\n用户要求：{req.prompt}{ctx}"
            )
            out = deps.model.respond([Message(role="system", content=prompt)], [])
            return out.text.strip()

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(_one, range(n)))
        candidates = [
            {"id": f"c{i + 1}", "style": styles[i % len(styles)], "text": results[i]}
            for i in range(n)
        ]
        return {"candidates": candidates}

    @router.post("/api/chat/rewrite", response_model=dict[str, str])
    def chat_rewrite(req: RewriteIn) -> dict[str, str]:
        """改写渐变条（机制 4）：保原味↔大幅改，温度+指令差异化。"""
        mode = req.mode if req.mode in ("subtle", "balanced", "bold") else "balanced"
        temp_map = {"subtle": 0.3, "balanced": 0.7, "bold": 1.1}
        instruct_map = {
            "subtle": "尽量保留原文结构与表达，只做轻微润色",
            "balanced": "在保留原意的基础上改写，语言更生动",
            "bold": "大胆重构：换切入角度、换句式节奏、大幅改变表达",
        }
        prompt = (
            "你是小说写作智能体。改写下面这段正文。"
            f"要求：{instruct_map[mode]}。直接输出改写后的正文，不要解释。\n\n原文：\n{req.text[:3000]}"
        )
        # 渐变条温度映射：保原味=低温，大幅改=高温（仅真实模型生效）
        rewrite_model: Any = deps.model
        if isinstance(deps.model, DeepSeekModel):
            rewrite_model = DeepSeekModel(temperature=temp_map[mode])
        out = rewrite_model.respond(
            [Message(role="system", content=prompt)],
            [],
        )
        return {"rewritten": out.text.strip(), "mode": mode}

    return router
