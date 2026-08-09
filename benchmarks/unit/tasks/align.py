"""单元层任务组：对齐系统载体（T8-T9）。"""

from __future__ import annotations

from benchmarks.unit.core import ApiClient


# ---------------------------------------------------------------------------
# T8 说明书载体（CRUD/锁定/元数据）
# ---------------------------------------------------------------------------
def t8_manual_crud(api: ApiClient) -> tuple[bool, dict, str]:
    # 新增
    added = api.post(
        "/api/manual", {"content": "叙事克制，少用感叹号", "scope": "project", "confidence": 0.5}
    )
    eid = added.get("id", "")
    if not eid:
        return False, {}, "新增失败（无 id）"
    # 列表可查 + 元数据字段
    entries = api.get("/api/manual?scope=project")
    if not isinstance(entries, list):
        return False, {}, "列表不是数组"
    found = next((e for e in entries if e.get("id") == eid), None)
    meta_ok = found is not None and all(
        k in found for k in ("content", "source", "confidence", "activity", "locked", "scope")
    )
    # 锁定后修改被拒
    api.patch(f"/api/manual/{eid}", {"locked": True})
    locked_update = api.patch(f"/api/manual/{eid}", {"content": "被篡改的内容"})
    lock_ok = locked_update.get("content", "") != "被篡改的内容"
    # 删除
    api.delete(f"/api/manual/{eid}")
    entries_after = api.get("/api/manual?scope=project")
    deleted = all(e.get("id") != eid for e in entries_after)
    return (
        meta_ok and lock_ok and deleted,
        {"meta_ok": meta_ok, "lock_ok": lock_ok, "deleted": deleted},
        f"entry_id={eid}",
    )


# ---------------------------------------------------------------------------
# T9 信号采集（操作→信号落库；兼测能动性反馈调节副作用）
# ---------------------------------------------------------------------------
def t9_signals(api: ApiClient) -> tuple[bool, dict, str]:
    a = api.post("/api/signals", {"kind": "accepted", "content": "这段很好", "context": "chat"})
    m = api.post(
        "/api/signals",
        {"kind": "modified", "content": "原文", "new_content": "改后", "context": "chat"},
    )
    d = api.post("/api/signals", {"kind": "deleted", "content": "删掉这段", "context": "chat"})
    ok = all(x.get("kind") in ("accepted", "modified", "deleted") for x in (a, m, d))
    # 接受=升级 → 能动档位应存在（S35：current.order）
    agency = api.get("/api/agency")
    level = (agency.get("current") or {}).get("order")
    return (
        ok and level is not None,
        {
            "accepted": a.get("kind"),
            "modified": m.get("kind"),
            "deleted": d.get("kind"),
            "agency_level_after": level,
        },
        "",
    )
