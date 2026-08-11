"""
anyspark.server.routes_workspace — 工作区 + 上传 + 角色卡/推演路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：工作区总览/章节导入同步 + 文件上传 +
角色卡读写 + 角色推演。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import UploadIn


def make_workspace_router(deps: AppDeps) -> APIRouter:
    """工作区路由（依赖：deps.workspace / deps.chapters / deps.model / deps.graph）。"""
    router = APIRouter()

    @router.get("/api/workspace", response_model=dict[str, Any])
    def workspace_overview() -> dict[str, Any]:
        """项目工作区结构总览：上传存档 / 章节文件 / 卡片。"""
        return deps.workspace.describe("main")

    @router.post("/api/workspace/import", response_model=dict[str, Any])
    def workspace_import_chapters() -> dict[str, Any]:
        """S48：扫描章节 md 文件 → 同步入库（人工直接编辑 md 后调用）。

        仅内容变化才 upsert（版本历史只在变化时记录）。
        权威始终在文件——import 是"文件 → 库镜像"的单向同步。
        """
        imported: list[dict[str, Any]] = []
        for item in deps.workspace.list_chapter_files("main"):
            content = deps.workspace.read_chapter("main", item["order"], item["title"])
            if content is None:
                continue
            existing = next(
                (c for c in deps.chapters.list_by_book("main") if c.title == item["title"]),
                None,
            )
            changed = existing is None or existing.content != content
            if changed:
                line = existing.narrative_line if existing else "main"
                deps.chapters.upsert("main", item["title"], content, item["order"], line)
            imported.append({"title": item["title"], "order": item["order"], "changed": changed})
        return {
            "ok": True,
            "files": len(imported),
            "changed": sum(1 for i in imported if i["changed"]),
            "imported": imported,
        }

    @router.post("/api/upload", response_model=dict[str, Any])
    def upload_to_workspace(req: UploadIn) -> dict[str, Any]:
        """S48：上传原始文件进上传区（存档，不参与操作；后续消化为格式化产物）。

        用 base64 JSON（零新依赖 python-multipart）；前端/agent 都可直接传。
        """
        import base64

        try:
            data = base64.b64decode(req.data_b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"base64 解码失败：{exc}") from exc
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
        dest = deps.workspace.save_upload(req.book_id, req.filename, data)
        logger.info("上传存档: %s -> %s", req.filename, dest.name)
        return {"ok": True, "name": dest.name, "path": str(dest), "size": len(data)}

    return router
