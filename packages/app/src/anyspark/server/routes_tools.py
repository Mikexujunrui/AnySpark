"""
anyspark.server.routes_tools — 扩展工具 + 代码扩展 + 输入消化 + 导出路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：扩展工具注册表（人工批准生效）、
codex 沙箱、上传消化管线、全书导出。闭包引用 → deps.xxx。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import CodexIn, IngestIn, ToolRegisterIn, ToolUpdateIn


def make_tools_router(deps: AppDeps) -> APIRouter:
    """扩展工具/代码/消化/导出路由（依赖：deps.ext_tools / workspace / chapters / materials）。"""
    router = APIRouter()

    # -----------------------------------------------------------------------
    # S48-P4/B 扩展工具注册表：Agent 写的工具，人工批准才生效
    # -----------------------------------------------------------------------
    @router.get("/api/tools", response_model=list[dict[str, Any]])
    def list_ext_tools() -> list[dict[str, Any]]:
        return [t.to_dict() for t in deps.ext_tools.list_all()]

    @router.post("/api/tools/register", response_model=dict[str, Any])
    def register_ext_tool(req: ToolRegisterIn) -> dict[str, Any]:
        """登记扩展工具（status=draft；人工批准后才注入 Agent 工具集）。"""
        try:
            params = json.loads(req.params_json) if req.params_json else []
            if not isinstance(params, list):
                raise ValueError("params 必须是 JSON 数组")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        if not req.code.strip() or "def run(" not in req.code:
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 run(args: dict) -> str 函数"
            )
        t = deps.ext_tools.add(req.name, req.description, params, req.code)
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": "draft",
            "note": "已登记待审——人工批准后才生效",
        }

    @router.post("/api/tools/{tool_id}/approve", response_model=dict[str, Any])
    def approve_ext_tool(tool_id: str) -> dict[str, Any]:
        """人工批准：工具进入 active，后续请求注入 Agent 工具集（无需重启）。"""
        t = deps.ext_tools.set_status(tool_id, "active")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        logger.info("扩展工具已批准生效: %s", t.name)
        return {"ok": True, "id": t.id, "name": t.name, "status": "active"}

    @router.patch("/api/tools/{tool_id}", response_model=dict[str, Any])
    def update_ext_tool(tool_id: str, req: ToolUpdateIn) -> dict[str, Any]:
        """更新扩展工具（S49：改代码/描述/参数）。安全：改后自动回 draft 重新批准。"""
        if req.params_json is not None:
            try:
                params = json.loads(req.params_json)
                if not isinstance(params, list):
                    raise ValueError("params 必须是 JSON 数组")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        else:
            params = None
        if req.code is not None and ("def run(" not in req.code):
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 def run(args: dict) -> str 函数"
            )
        t = deps.ext_tools.update(tool_id, req.name, req.description, params, req.code)
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "note": "已更新，需重新人工批准后才生效",
        }

    @router.post("/api/tools/{tool_id}/disable", response_model=dict[str, Any])
    def disable_ext_tool(tool_id: str) -> dict[str, Any]:
        t = deps.ext_tools.set_status(tool_id, "draft")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True, "id": t.id, "name": t.name, "status": "draft"}

    @router.delete("/api/tools/{tool_id}", response_model=dict[str, Any])
    def delete_ext_tool(tool_id: str) -> dict[str, Any]:
        if not deps.ext_tools.delete(tool_id):
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S48-P5 代码扩展（anyspark-codex）：沙箱执行，固定工具做不了时用
    # -----------------------------------------------------------------------
    @router.post("/api/codex/run", response_model=dict[str, Any])
    def codex_run(req: CodexIn) -> dict[str, Any]:
        """沙箱执行 Python 代码（白名单安全 + 只读数据环境 ws_*：真实统计/自定义分析）。"""
        from anyspark.server.codex import make_data_env, run_code

        return run_code(
            req.code,
            req.timeout,
            data_env=make_data_env(deps.workspace, deps.chapters, deps.graph),
        )

    # -----------------------------------------------------------------------
    # S48-P3 输入消化管线：上传区原始文件 → 格式化区（章节 md / 摘要卡）
    # -----------------------------------------------------------------------
    @router.post("/api/ingest", response_model=dict[str, Any])
    def ingest_upload(req: IngestIn) -> dict[str, Any]:
        """消化上传区文件：长文（多章）拆成章节 md；资料/短文本生成摘要卡。

        原始文件原地不动（存档）；产物进格式化区（章节/ 或 卡片/）。
        多模态（扫描件 OCR/图片理解）明确不做，放未来计划。
        """
        # S83 R2：消化编排收敛到 ingest_pipeline（原内联实现零变化搬移）
        from anyspark.server.ingest import INGEST_ALLOWED_EXT, ingest_pipeline

        result = ingest_pipeline(
            deps.workspace,
            deps.chapters,
            deps.materials,
            model_for_task(deps, "extraction"),
            req.book_id,
            req.filename,
            mode=req.mode,
            allowed_ext=INGEST_ALLOWED_EXT,
            skills=deps.skills,
        )
        if not result.ok:
            if result.error_code == "not_found":
                raise HTTPException(status_code=404, detail=f"上传区无此文件：{req.filename}")
            if result.error_code == "bad_ext":
                raise HTTPException(
                    status_code=400, detail="仅支持 txt/md/docx/pdf 文本消化（图片放未来）"
                )
            if result.error_code == "empty":
                raise HTTPException(status_code=400, detail="无法提取文本（扫描件 OCR 放未来计划）")
            # unknown：原实现无 try/except，异常直接抛（FastAPI 全局 500）——恢复原行为
            if result.exception is not None:
                raise result.exception
            raise HTTPException(status_code=500, detail=result.error)
        if result.kind == "card":
            return {
                "ok": True,
                "kind": "card",
                "title": result.title,
                "card_file": result.card_file,
                "material_id": result.material_id,
            }
        if result.kind == "skill":
            # S118 提案 D：上传文件识别为 skill → 草稿待确认（前端刷新草稿区）
            return {
                "ok": True,
                "kind": "skill",
                "title": result.title,
                "draft_id": result.material_id,
            }
        written = result.chapters
        logger.info("消化: %s → %d 章", req.filename, len(written))
        return {"ok": True, "kind": "chapters", "count": len(written), "chapters": written}

    @router.get("/api/export/book", response_model=None)
    def export_book(format: str = "md") -> Response:
        """全书导出（S48-P3）：txt/md/epub（epub 携带 md 引用的图片）。"""
        from anyspark.server.export import export_epub, export_md, export_txt

        items = deps.chapters.list_by_book("main")
        chs = [{"title": c.title, "content": c.content} for c in items]
        fmt = format if format in ("txt", "md", "epub") else "md"
        if fmt == "epub":
            data = export_epub(
                "AnySpark 作品",
                "AnySpark",
                chs,
                image_dir=deps.workspace.chapters_dir("main"),  # md 引用相对章节目录
            )
            from urllib.parse import quote

            safe = quote("anyspark-book.epub")
            return Response(
                content=data,
                media_type="application/epub+zip",
                headers={
                    "Content-Disposition": (
                        f"attachment; filename=book.epub; filename*=UTF-8''{safe}"
                    )
                },
            )
        body = export_txt(chs) if fmt == "txt" else export_md(chs)
        media = "text/plain; charset=utf-8" if fmt == "txt" else "text/markdown; charset=utf-8"
        from urllib.parse import quote

        safe = quote(f"anyspark-book.{fmt}")
        return Response(
            content=body,
            media_type=media,
            headers={
                "Content-Disposition": (f"attachment; filename=book.{fmt}; filename*=UTF-8''{safe}")
            },
        )

    return router
