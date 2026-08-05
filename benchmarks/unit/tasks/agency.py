"""单元层任务组：能动性协议（T13-T14）。"""

from __future__ import annotations

from benchmarks.unit.core import ApiClient, similarity


# ---------------------------------------------------------------------------
# T13 档位真实生效（0 档只听写 ≈ 原文；4 档自由发挥 ≈ 偏离）
# ---------------------------------------------------------------------------
def t13_agency_levels(api: ApiClient) -> tuple[bool, dict, str]:
    original = "雨敲着窗玻璃。陈渡把信封放在桌上，拆开，里面只有一行字：别去找他。"

    def run_at(level: int, instruction: str) -> str:
        resp = api.post(
            "/api/chat",
            {
                "message": f"{instruction}：{original}",
                "agency_level": level,
                "skip_inject": ["manual", "graph", "bias", "mood"],
                "extract_graph": False,
            },
        )
        return str(resp.get("text", ""))

    # 0 档：逐字复制指令（只听写承诺）；4 档：自由发挥（参考值，不判定——单次采样噪声大）
    out_0 = run_at(0, "请逐字复制下面这段话，不要修改、不要添加任何字")
    out_4 = run_at(4, "请自由发挥，把下面这段话改写成更精彩的版本")
    sim_0 = similarity(original, out_0)
    sim_4 = similarity(original, out_4)
    # 只听写承诺：0 档输出应高度贴近原文（≥0.7）
    passed = sim_0 >= 0.7
    return (
        passed,
        {"sim_level0": round(sim_0, 3), "sim_level4_ref": round(sim_4, 3)},
        f"L0={out_0[:60]} | L4={out_4[:60]}",
    )


# ---------------------------------------------------------------------------
# T14 档位载体（五级协议 + 温度映射 + CRUD）
# ---------------------------------------------------------------------------
def t14_agency_crud(api: ApiClient) -> tuple[bool, dict, str]:
    get_resp = api.get("/api/agency")
    levels = get_resp.get("levels", [])
    names = [l.get("name") for l in levels] if isinstance(levels, list) else []
    ok_five = names == ["只听写", "执行+填肉", "补全标注", "建议扩展", "自主发挥"]
    # S35：POST 返回 current（档位记录），level 兼容=排序位
    set_resp = api.post("/api/agency", {"level": 2})
    cur = set_resp.get("current") or {}
    level_ok = cur.get("order") == 2 or cur.get("id") == "default-2"
    # 恢复默认
    api.post("/api/agency", {"level": 4})
    return (
        ok_five and level_ok,
        {"levels": names, "set_level": cur.get("order")},
        "",
    )
