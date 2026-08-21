"""
anyspark.server.routes_chat_aux — 聊天辅助路由（从 routes_chat 拆分，S207）。

direction（方向声明）/ candidates（候选卡堆）/ rewrite（改写渐变条）。
机制 1/4 低摩擦交互：摩擦前置（方向声明）+ 多样性候选 + 渐变改写。
依赖：deps.model / deps.models（model_for_task）。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter

from anyspark.core import Message
from anyspark.models import DeepSeekModel
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.schemas import CandidatesIn, DirectionIn, RewriteIn


def make_chat_aux_router(deps: AppDeps) -> APIRouter:
    """辅助路由（依赖：deps.model / deps.models）。"""
    router = APIRouter()

    @router.post("/api/chat/direction", response_model=dict[str, str])
    def chat_direction(req: DirectionIn) -> dict[str, str]:
        """阶段 5 方向声明：AI 只声明"我准备写：…"不写正文（摩擦前置，用户 0.5s 确认）。"""
        # S109：已知设定阈值 2000→4000；超限告知边界（直调无工具，模型不臆测）
        ctx = f"\n已知设定：{req.context[:4000]}" if req.context else ""
        if req.context and len(req.context) > 4000:
            ctx += f"\n【注意：设定全文 {len(req.context)} 字，以上仅前 4000 字】"
        prompt = (
            "你是小说写作智能体。用户将让你写一段内容。"
            "在动笔前，先输出【方向声明】——一句话说明你准备写什么、怎么切入"
            "（像'我准备写：主角推开钟表铺的门，雨声里老周欲言又止'）。"
            "只输出声明，不要写正文。\n\n"
            f"用户要求：{req.prompt}{ctx}"
        )
        out = model_for_task(deps, "writing").respond([Message(role="system", content=prompt)], [])
        direction = out.text.strip()
        if not direction.startswith("【方向声明】"):
            direction = f"【方向声明】{direction}"
        return {"direction": direction}

    @router.post("/api/chat/candidates", response_model=dict[str, object])
    def chat_candidates(req: CandidatesIn) -> dict[str, object]:
        """候选卡堆：并行生成 N 个差异化候选（上下文隔离→真多样性，机制 1/4）。"""
        # S109：已知设定阈值 2000→4000；超限告知边界
        ctx = f"\n已知设定：{req.context[:4000]}" if req.context else ""
        if req.context and len(req.context) > 4000:
            ctx += f"\n【注意：设定全文 {len(req.context)} 字，以上仅前 4000 字】"
        n = max(2, min(4, req.n))
        styles = ["平实叙事", "强画面感", "悬念张力", "细腻心理"]

        def _one(i: int) -> str:
            prompt = (
                f"你是小说写作智能体。按风格「{styles[i % len(styles)]}」写下面要求的一段正文"
                f"（约 150-250 字，直接输出正文，不要解释）。\n\n用户要求：{req.prompt}{ctx}"
            )
            out = model_for_task(deps, "planning").respond(
                [Message(role="system", content=prompt)], []
            )
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
        # S109：改写原文阈值 3000→8000（用户选中长段落不丢后半）；超限告知边界
        src = req.text[:8000]
        if len(req.text) > 8000:
            src = f"【注意：原文全文 {len(req.text)} 字，以下仅前 8000 字】\n{src}"
        prompt = (
            "你是小说写作智能体。改写下面这段正文。"
            f"要求：{instruct_map[mode]}。直接输出改写后的正文，不要解释。\n\n原文：\n{src}"
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
