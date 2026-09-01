"""
anyspark.server.routes_library — 参考书库路由（S86）。

书库 CRUD（data/library/ 文件区）+ 项目-参考书关联（GET/PUT）。
参考书不注入任何信息；检索走 agent 工具 reference_lookup（只读）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    LibraryBookIn,
    LibraryImportIn,
    LibraryRefineIn,
    LibraryRefsIn,
    LibrarySearchIn,
)


def make_library_router(deps: AppDeps) -> APIRouter:
    """参考书库路由（依赖：deps.library / deps.workspace / deps.chapters）。"""
    router = APIRouter()

    # -- 书库 --
    @router.get("/api/library", response_model=list[dict[str, Any]])
    def list_library() -> list[dict[str, Any]]:
        """全部书库书（全局库）。"""
        return deps.library.list_books()

    @router.post("/api/library", response_model=dict[str, Any])
    def add_library_book(req: LibraryBookIn) -> dict[str, Any]:
        """新建书库书（空目录，待导入）。"""
        return deps.library.add_book(req.name)

    @router.post("/api/library/import", response_model=dict[str, Any])
    def import_library_text(req: LibraryImportIn) -> dict[str, Any]:
        """导入文本到书库书（按章节标题拆章，或整体一章）。"""
        from anyspark.server.pipeline import chapterize

        text = req.content.strip()
        if not text:
            raise HTTPException(status_code=400, detail="内容为空")
        book = deps.library.get_book(req.book_id)
        if book is None:
            raise HTTPException(status_code=404, detail=f"书库无此书: {req.book_id}")
        chaps = chapterize(text, fallback_title=req.title or book["name"])
        count = 0
        for i, ch in enumerate(chaps):
            deps.library.import_chapter(req.book_id, ch["title"], ch["content"], i)
            count += 1
        # S244：导入后尽力向量索引（embedding 未配/失败不阻塞导入）
        index_note = _try_index_book(req.book_id)
        return {"ok": True, "book_id": req.book_id, "chapters": count, "index": index_note}

    @router.delete("/api/library/{book_id}", response_model=dict[str, bool])
    def delete_library_book(book_id: str) -> dict[str, bool]:
        ok = deps.library.delete_book(book_id)
        if not ok:
            raise HTTPException(status_code=404, detail="书不存在")
        # S244：同步清向量残留
        if deps.library_vectors is not None:
            deps.library_vectors.drop_book(book_id)
        return {"ok": True}

    # -- S244 书库 RAG（语义检索 + 混合排序 + 索引管理） --

    def _try_index_book(book_id: str) -> dict[str, Any]:
        """尽力索引一本书（embedding 不可用/失败返回说明，不抛异常）。"""
        if deps.library_vectors is None or deps.embedder is None or not deps.embedder.available:
            return {"skipped": "embedding 未配置"}
        try:
            files = deps.library.iter_book_files(book_id)
            result: dict[str, Any] = deps.library_vectors.index_book_signed(
                book_id, files, deps.embedder.embed
            )
            return result
        except Exception as exc:  # 索引失败不影响导入主流程
            logger.warning("书库向量索引失败 book=%s: %s", book_id, exc)
            return {"error": str(exc)[:200]}

    @router.post("/api/library/{book_id}/reindex", response_model=dict[str, Any])
    def reindex_library_book(book_id: str) -> dict[str, Any]:
        """（重）索引一本书的向量（增量：未变更文件跳过）。"""
        if deps.library_vectors is None or deps.embedder is None or not deps.embedder.available:
            raise HTTPException(
                status_code=400,
                detail="向量索引不可用：未配置 EMBEDDING（可用 DEEPSEEK_* 兑底）",
            )
        book = deps.library.get_book(book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="书不存在")
        files = deps.library.iter_book_files(book_id)
        if not files:
            raise HTTPException(status_code=400, detail="书内无章节文件")
        result = deps.library_vectors.index_book_signed(book_id, files, deps.embedder.embed)
        return {"ok": True, "book_id": book_id, "book_name": book["name"], **result}

    @router.post("/api/library/search", response_model=dict[str, Any])
    def search_library_global(req: LibrarySearchIn) -> dict[str, Any]:
        """全局书库混合检索（S244）：语义（向量余弦）+ 关键词双通道。

        embedding 未配置时自动降级纯关键词（degraded=true 标记）。
        """
        from anyspark.library.search import search_library_hybrid

        result: dict[str, Any] = search_library_hybrid(
            deps.library,
            deps.library_vectors,
            deps.embedder,
            req.query,
            top_k=req.top_k,
        )
        return result

    @router.get("/api/library/index-status", response_model=dict[str, Any])
    def library_index_status() -> dict[str, Any]:
        """向量索引概况（书数/chunk 数/维度/可用性）。"""
        if deps.library_vectors is None:
            return {"available": False, "books": 0, "chunks": 0, "dim": None}
        st: dict[str, Any] = deps.library_vectors.stats()
        st["available"] = bool(deps.embedder and deps.embedder.available) and st["chunks"] > 0
        return st

    # -- 项目-参考书关联 --
    @router.get("/api/books/{book_id}/references", response_model=list[dict[str, Any]])
    def get_references(book_id: str) -> list[dict[str, Any]]:
        """项目的参考书（书库的书 + 工作区其他项目）。"""
        return deps.library.get_references(book_id)

    @router.put("/api/books/{book_id}/references", response_model=dict[str, Any])
    def set_references(book_id: str, req: LibraryRefsIn) -> dict[str, Any]:
        """设置项目参考书（全量替换）：refs=[{type: library|project, id: ...}]。"""
        deps.library.set_references(book_id, req.refs)
        return {"ok": True, "book_id": book_id, "refs": deps.library.get_references(book_id)}

    # -- S103 书库 → skill 提炼（拆书模式：多维拆解融合成「书名」skill 草稿） --
    @router.post("/api/library/{book_id}/refine-skill", response_model=dict[str, Any])
    def refine_skill_from_library(
        book_id: str, req: LibraryRefineIn | None = None
    ) -> dict[str, Any]:
        """书库 → skill 提炼：取书库原文，三层拆解（S114）——微观方法论
        （文风/节奏/结构/人设/对白/信息投放/钩子）+ 骨架扫描 + 定点精读架构技法，
        生成多条 skill 草稿（人工确认后转正生效）。
        """
        hint = (req.hint if req else "").strip()
        book = deps.library.get_book(book_id)
        if book is None:
            raise HTTPException(status_code=404, detail=f"书库无此书: {book_id}")
        # S106：拆书需全文（12MB 级整本书）——不截断，抽样归并由 generate_book 内部做
        # S114：拆书三层（微观方法论 + 骨架扫描 + 定点精读架构技法），book_name 注入
        source = deps.library.read_book(book_id, max_chars=None)
        if not source.strip():
            raise HTTPException(status_code=400, detail="书库无内容（先导入文本）")
        cands = deps.skill_generator.generate_book(source, hint, book_name=book["name"])
        if not cands:
            # S113：透出可读失败原因（此前静默“无有效候选”，用户不知真因）
            detail = "提炼失败（无有效候选）"
            err = getattr(deps.skill_generator, "last_error", "")
            if err:
                detail += f"：{err}"
            raise HTTPException(status_code=502, detail=detail)
        # S114：多候选存草稿（书名方法论 + 架构技法 + 剧情模式各自独立确认）
        # S130：同书名一包（pack_id=书名，整包引用路由按包分流）
        drafts: list[dict[str, Any]] = []
        for c in cands:
            draft = deps.skills.add_draft(
                name=str(c.get("name", book["name"]))[:120],
                description=str(c.get("description", ""))[:500],
                content=str(c.get("content", "")),
                example=str(c.get("example", ""))[:2000],
                tags=str(c.get("tags", "")),
                type=str(c.get("type", "writing")),
                ext=str(c.get("ext", "")),
                pack_id=book["name"],
                source="library",
            )
            if draft:
                drafts.append(draft)
        if not drafts:
            raise HTTPException(status_code=409, detail="已存在同名草稿或技能（先确认/删除旧的）")
        logger.info("书库→skill 提炼: book=%s drafts=%d", book["name"], len(drafts))
        return {"ok": True, "drafts": drafts, "draft": drafts[0]}

    return router
