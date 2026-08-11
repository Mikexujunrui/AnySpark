"""anyspark.server.routes_books — 书架路由（S79 壳移植，S80c 路由拆分后补回）。

S79 在 app.py 加的书架端点（GET/POST/DELETE /api/books）在并行路由拆分时丢失，
此处补回。依赖：deps.workspace（项目目录）+ deps.chapters（章节统计）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.schemas import BriefIn


def make_books_router(deps: AppDeps) -> APIRouter:
    """书架路由（项目枚举/创建/删除，book_id=项目名）。"""
    router = APIRouter()

    @router.get("/api/books", response_model=list[dict[str, Any]])
    def list_books() -> list[dict[str, Any]]:
        """枚举全部项目（书架）：工作区子目录 + 章节统计 + 简介摘要。"""
        workspace = deps.workspace
        root = workspace.root
        books: list[dict[str, Any]] = []
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith(".") or d.name == "__pycache__":
                continue
            book_id = d.name
            chs = deps.chapters.list_by_book(book_id)
            total_chars = sum(len(c.content or "") for c in chs)
            brief = workspace.read_brief(book_id)
            books.append(
                {
                    "id": book_id,
                    "title": book_id,
                    "chapterCount": len(chs),
                    "totalChars": total_chars,
                    "brief": brief[:200] if brief else "",
                    "updatedAt": max((c.updated_at for c in chs), default=""),
                }
            )
        return books

    @router.post("/api/books", response_model=dict[str, Any])
    def create_book(req: BriefIn) -> dict[str, Any]:
        """创建项目：book_id 即项目目录（防穿越消毒）；重复返回已存在。"""
        from anyspark.server.workspace import _safe_title

        workspace = deps.workspace
        book_id = _safe_title(req.content.strip() or req.book_id)
        if not book_id:
            raise HTTPException(status_code=422, detail="项目名不能为空")
        d = workspace.project_dir(book_id)
        if list(d.iterdir()):
            raise HTTPException(status_code=409, detail=f"项目已存在: {book_id}")
        # 初始化 brief 占位（用户后续可在简介面板编辑）
        workspace.write_brief(book_id, f"# {book_id}\n\n（新建项目——请填写项目简介）")
        return {
            "id": book_id,
            "title": book_id,
            "chapterCount": 0,
            "totalChars": 0,
            "brief": f"# {book_id}",
            "updatedAt": "",
        }

    @router.delete("/api/books/{book_id}", response_model=dict[str, Any])
    def delete_book(book_id: str) -> dict[str, Any]:
        """删除项目：仅删工作区目录（库数据保留，防误删——重建同名项目可找回）。"""
        import shutil

        from anyspark.server.workspace import _safe_title

        safe = _safe_title(book_id)
        d = deps.workspace.project_dir(safe)
        if not d.exists():
            raise HTTPException(status_code=404, detail=f"项目不存在: {book_id}")
        shutil.rmtree(d, ignore_errors=True)
        return {"ok": True, "deleted": safe}

    return router
