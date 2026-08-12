"""
anyspark.server.routes_chapters — 章节路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：章节 CRUD + 定点编辑 patch + 导出 + 一章收尾 wrapup。
闭包引用 → deps.xxx。
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from anyspark.core import Message
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import logger
from anyspark.server.schemas import ChapterCreate, ChapterOut, ChapterPatchIn, ChapterUpdate


def make_chapters_router(deps: AppDeps) -> APIRouter:
    """章节路由（deps.chapters / workspace / model / graph_verifier / plots）。"""
    router = APIRouter()

    @router.post("/api/chapters/{chapter_id}/wrapup", response_model=dict[str, object])
    def chapter_wrapup(chapter_id: str) -> dict[str, object]:
        """阶段 6 一章收尾：一致性摘要卡 + 下一章衔接提示（不自动评审，轻量）。"""
        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        prompt = (
            "你是小说写作智能体。读下面这章正文，输出两句：\n"
            "1. 一致性摘要（一句话概括本章发生了什么、推进了什么）\n"
            "2. 下一章衔接提示（建议下一章推进什么，如'推进角色弧/揭开伏笔'，给一个具体方向）\n"
            '格式（严格 JSON）：{"summary": "…", "next_hint": "…"}\n\n'
            f"章节《{ch.title}》正文：\n{ch.content[:4000]}"
        )
        out = model_for_task(deps, "extraction").respond(
            [Message(role="system", content=prompt)], []
        )
        cleaned = out.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        summary, hint = "", ""
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                if isinstance(data, dict):
                    summary = str(data.get("summary", ""))
                    hint = str(data.get("next_hint", ""))
            except json.JSONDecodeError:
                pass
        # 图谱统计（本章涉及的实体）
        involved = deps.graph_verifier.facts_for("main", ch.content[:2000])
        # S31：主线钩子检查——作者承诺的剧情钩子仍未回收的（轻量提示，建议非门禁）
        # 老龄化：带开放时长（中性事实，不设阈值不评判）
        open_hooks = deps.plots.open_must("main", current_order=ch.order_index) or []
        hook_check = (
            [
                {
                    "content": h.content[:60],
                    "chapter_ref": h.chapter_ref,
                    "category": h.category,
                    "open_since": (
                        ch.order_index - h.planted_order if h.planted_order > 0 else None
                    ),
                }
                for h in open_hooks
            ][:8]
            if open_hooks
            else []
        )
        return {
            "chapter_id": chapter_id,
            "title": ch.title,
            "summary": summary or out.text.strip()[:100],
            "next_hint": hint,
            "graph_entities": [f.entity.name for f in involved][:10],
            "open_hooks": hook_check,  # S31：仍未回收的主线钩子（提醒，不阻断）
        }

    @router.get("/api/chapters", response_model=list[ChapterOut])
    def list_chapters(book_id: str = "main") -> list[ChapterOut]:
        items = deps.chapters.list_by_book(book_id)
        return [
            ChapterOut(
                id=c.id,
                book_id=c.book_id,
                title=c.title,
                content=c.content,
                order_index=c.order_index,
                updated_at=c.updated_at,
            )
            for c in items
        ]

    @router.post("/api/chapters", response_model=ChapterOut)
    def create_chapter(req: ChapterCreate) -> ChapterOut:
        """F1：手动新建章节（空正文，order_index=末尾+1；库+md 双写）。"""
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="标题不能为空")
        chs = deps.chapters.list_by_book(req.book_id)
        order = max((c.order_index for c in chs), default=-1) + 1
        ch = deps.chapters.upsert(req.book_id, title, req.content, order)
        deps.workspace.write_chapter(req.book_id, order, ch.title, ch.content)
        return ChapterOut(
            id=ch.id,
            book_id=ch.book_id,
            title=ch.title,
            content=ch.content,
            order_index=ch.order_index,
            updated_at=ch.updated_at,
        )

    @router.get("/api/chapters/{chapter_id}", response_model=ChapterOut)
    def get_chapter(chapter_id: str) -> ChapterOut:
        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        return ChapterOut(
            id=ch.id,
            book_id=ch.book_id,
            title=ch.title,
            content=ch.content,
            order_index=ch.order_index,
            updated_at=ch.updated_at,
            versions=ch.versions or [],
        )

    @router.put("/api/chapters/{chapter_id}", response_model=ChapterOut)
    def update_chapter(chapter_id: str, req: ChapterUpdate) -> ChapterOut:
        """F2a：稿纸编辑器保存章节内容。"""
        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        deps.chapters.upsert(ch.book_id, ch.title, req.content, ch.order_index, ch.narrative_line)
        updated = deps.chapters.get(chapter_id)
        if updated is None:
            raise HTTPException(status_code=500, detail="保存后章节读取失败")
        # S85：手动保存也触发图谱抽取/伏笔回收（对齐 write_chapter 后台链路，防图谱漂移）
        deps.bg_queue.put(
            BgTask(
                kind="chapter",
                title=ch.title,
                content=req.content,
                order=ch.order_index,
                line=ch.narrative_line,
                book_id=ch.book_id,
            )
        )
        return ChapterOut(
            id=updated.id,
            book_id=updated.book_id,
            title=updated.title,
            content=updated.content,
            order_index=updated.order_index,
            updated_at=updated.updated_at,
        )

    @router.delete("/api/chapters/{chapter_id}", response_model=dict[str, object])
    def delete_chapter(chapter_id: str) -> dict[str, object]:
        """F1：删除章节（库 + md 双写删除）。前端章节树管理需要，属章节 CRUD 补全。"""
        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        # 双写：先删 md 权威文件，再删库镜像（幂等，文件不存在不影响）
        deps.workspace.delete_chapter_file(ch.book_id, ch.order_index, ch.title)
        removed = deps.chapters.delete(chapter_id)
        if not removed:
            raise HTTPException(status_code=500, detail="删除失败")
        logger.info("章节删除: %s《%s》", ch.book_id, ch.title)
        return {"ok": True, "id": chapter_id, "title": ch.title}

    @router.post("/api/chapters/{chapter_id}/patch", response_model=dict[str, object])
    def patch_chapter_route(chapter_id: str, req: ChapterPatchIn) -> dict[str, object]:
        """S44：定点编辑（锚点定位段落的插入/删除/替换，不重写整章）。"""
        from anyspark.server.tools_writing import apply_patch

        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        new_content, results = apply_patch(ch.content, req.operations)
        ok_all = all(r.get("ok") for r in results)
        deps.chapters.upsert("main", ch.title, new_content, ch.order_index, ch.narrative_line)
        # S85：定点编辑也触发图谱抽取（防图谱漂移）
        if ok_all and new_content != ch.content:
            deps.bg_queue.put(
                BgTask(
                    kind="chapter",
                    title=ch.title,
                    content=new_content,
                    order=ch.order_index,
                    line=ch.narrative_line,
                    book_id="main",
                )
            )
        return {
            "title": ch.title,
            "ok": ok_all,
            "results": results,
            "chars": len(new_content),
        }

    @router.get("/api/chapters/{chapter_id}/export")
    def export_chapter(chapter_id: str, format: str = "txt") -> Response:
        """多格式导出（S11 工具扩展：txt/md）。"""
        ch = deps.chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        fmt = format if format in ("txt", "md") else "txt"
        body = f"# {ch.title}\n\n{ch.content}\n" if fmt == "md" else f"{ch.title}\n{ch.content}\n"
        media = "text/markdown; charset=utf-8" if fmt == "md" else "text/plain; charset=utf-8"
        # 中文文件名用 RFC 5987 filename*（latin-1 无法直接编码中文）
        from urllib.parse import quote

        safe_name = quote(f"{ch.title}.{fmt}")
        disposition = f"attachment; filename=chapter.{fmt}; filename*=UTF-8''{safe_name}"
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": disposition},
        )

    return router
