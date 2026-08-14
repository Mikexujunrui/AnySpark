"""
anyspark.server.routes_agency — 能动性档位路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：agency 档位 CRUD/生成/重置。
S140（PLAN-SCALE-SAFETY 阶段 D）：批量改写/审读路由移除——已收编为预置
workflow 模板（「批量改写」「批量审读」），前端 BatchPanel 工作流模式执行
（S133 归一不降级；断点/续跑/回滚由 workflow 提供）。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from anyspark.align import build_agency_gen_prompt, parse_agency_gen_result
from anyspark.core import Message
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import AgencyGenerateIn, AgencyIn, AgencyLevelIn


def make_agency_router(deps: AppDeps) -> APIRouter:
    """能动性档位路由（依赖：deps.agency / model）。"""
    router = APIRouter()

    @router.get("/api/agency", response_model=dict[str, object])
    def get_agency() -> dict[str, object]:
        """能动档位（机制 2 + S35 记录集）：当前档位 + 全部档位（含自定义）。"""
        return {
            "current": deps.agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in deps.agency.list_levels()],
        }

    @router.post("/api/agency", response_model=dict[str, object])
    def set_agency(req: AgencyIn) -> dict[str, object]:
        """用户点选档位（level_id 优先；兼容旧 level 数字=排序位）。"""
        if req.level_id:
            lv = deps.agency.set_current(req.level_id)
        elif req.level is not None:
            levels = deps.agency.list_levels()
            target = next((x for x in levels if x.order == req.level), None)
            lv = deps.agency.set_current(target.id) if target else None
        else:
            lv = None
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {
            "current": lv.to_dict(),
            "levels": [x.to_dict() for x in deps.agency.list_levels()],
        }

    @router.post("/api/agency/add", response_model=dict[str, object])
    def add_agency_level(req: AgencyLevelIn) -> dict[str, object]:
        """S35：新增自定义档位（全局，追加到末尾）。"""
        lv = deps.agency.add_level(req.name, req.description, req.temperature)
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in deps.agency.list_levels()]}

    @router.post("/api/agency/generate", response_model=dict[str, object])
    def generate_agency(req: AgencyGenerateIn) -> dict[str, object]:
        """S61 L3：自然语言描述 → 档位候选（真实 LLM，人工确认后 add 生效）。

        对齐 S54 skillgen"候选→确认闸门"哲学：候选不进表，返回给用户/前端确认。
        """
        assert deps.model is not None
        if not req.description.strip():
            raise HTTPException(status_code=400, detail="description 不能为空")
        if not 1 <= req.n <= 5:
            raise HTTPException(status_code=400, detail="n 需在 1-5 之间")
        prompt = build_agency_gen_prompt(req.description, req.n)
        try:
            out = model_for_task(deps, "planning").respond(
                [Message(role="system", content=prompt)], []
            )
            candidates = parse_agency_gen_result(out.text)
            return {
                "candidates": candidates[: req.n],
                "description": req.description,
                "note": "确认后 POST /api/agency/add 生效（人工确认闸门）",
            }
        except Exception as exc:
            logger.warning("档位生成失败: %s", exc)
            return {"candidates": [], "description": req.description, "note": f"生成失败: {exc}"}

    @router.patch("/api/agency/{level_id}", response_model=dict[str, object])
    def patch_agency_level(level_id: str, req: AgencyLevelIn) -> dict[str, object]:
        """S35：修改档位名称/描述/温度。"""
        lv = deps.agency.update_level(level_id, req.name, req.description, req.temperature)
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in deps.agency.list_levels()]}

    @router.delete("/api/agency/{level_id}", response_model=dict[str, object])
    def delete_agency_level(level_id: str) -> dict[str, object]:
        """S35：删除档位（至少保留一条；删当前则回落默认）。"""
        ok = deps.agency.delete_level(level_id)
        if not ok:
            raise HTTPException(status_code=400, detail="无法删除（至少保留一条或不存在）")
        return {"levels": [x.to_dict() for x in deps.agency.list_levels()]}

    @router.post("/api/agency/reset", response_model=dict[str, object])
    def reset_agency() -> dict[str, object]:
        """S35：恢复默认五级档位（不重置心智模型——manual 在不同表，天然保留）。"""
        levels = deps.agency.reset_defaults()
        return {
            "current": deps.agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in levels],
        }

    return router
