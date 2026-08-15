"""anyspark.server.routes_books — 书架路由（S79 壳移植，S80c 路由拆分后补回）。

S79 在 app.py 加的书架端点（GET/POST/DELETE /api/books）在并行路由拆分时丢失，
此处补回。依赖：deps.workspace（项目目录）+ deps.chapters（章节统计）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.schemas import BriefIn, ImportTxtBookIn


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

    @router.post("/api/books/import-txt", response_model=dict[str, Any])
    def import_txt_book(req: ImportTxtBookIn) -> dict[str, Any]:
        """S156：书架页"单个 txt 直接上传成书"——建项目 + 存上传区 + 消化 原子完成。

        mode 缺省 chapters（书籍文本直接拆章成书，不做摘要卡提取）；title 缺省取文件名。
        任一步失败回滚整个项目目录，不留空项目/孤儿上传物。
        """
        import base64
        import shutil
        from pathlib import Path

        from anyspark.server.agent_factory import model_for_task
        from anyspark.server.ingest import INGEST_ALLOWED_EXT, ingest_pipeline
        from anyspark.server.workspace import _safe_title

        title = (req.title or Path(req.filename).stem).strip()[:40]
        book_id = _safe_title(title)
        if not book_id:
            raise HTTPException(status_code=422, detail="书名不能为空")
        workspace = deps.workspace
        d = workspace.project_dir(book_id)
        if list(d.iterdir()):
            raise HTTPException(status_code=409, detail=f"项目已存在: {book_id}")
        workspace.write_brief(book_id, f"# {book_id}\n\n（从 txt 导入创建）")
        try:
            workspace.save_upload(book_id, req.filename, base64.b64decode(req.data_b64))
            result = ingest_pipeline(
                workspace,
                deps.chapters,
                deps.materials,
                model_for_task(deps, "extraction"),
                book_id,
                req.filename,
                mode=req.mode or "chapters",
                allowed_ext=INGEST_ALLOWED_EXT,
                skills=deps.skills,
            )
        except Exception:
            shutil.rmtree(d, ignore_errors=True)  # 回滚：不留半成品项目
            raise
        if not result.ok:
            shutil.rmtree(d, ignore_errors=True)
            if result.error_code == "bad_ext":
                raise HTTPException(
                    status_code=400, detail="仅支持 txt/md/docx/pdf 文本（图片放未来）"
                )
            if result.error_code == "empty":
                raise HTTPException(status_code=400, detail="无法提取文本（扫描件 OCR 放未来计划）")
            if result.error_code == "dup":
                raise HTTPException(status_code=409, detail=result.error)
            raise HTTPException(status_code=500, detail=result.error or "消化失败")
        chs = deps.chapters.list_by_book(book_id)
        return {
            "book": {
                "id": book_id,
                "title": book_id,
                "chapterCount": len(chs),
                "totalChars": sum(len(c.content or "") for c in chs),
            },
            "kind": result.kind,
            "count": len(result.chapters),
            "chapters": result.chapters,
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
