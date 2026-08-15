"""
AnySpark v4 — 端到端全流程冒烟（模拟智能体测试链路，S7-S12 全部能力回归）。

链路：写作闭环 → 图谱抽取注入 → 说明书/信号/能动性 → 探索 → 检测 → 资料 →
      方向声明/候选卡/改写/收尾 → SSE 流式 → 沙箱文件 → 导出 → 状态快照。
运行：uv run python scripts/e2e_smoke.py（需后端已启动：uv run anyspark-server）
"""

from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
# 禁用系统代理（本机后端不走代理）
_NO_PROXY = urllib.request.ProxyHandler({})
_opener = urllib.request.build_opener(_NO_PROXY)


def api(
    path: str,
    body: object | None = None,
    timeout: int = 180,
    method: str | None = None,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method or ("POST" if data else "GET"),
    )
    with _opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  ✅ {name}")
        else:
            fail += 1
            print(f"  ❌ {name} {detail}")

    print("== 1. 健康检查 ==")
    h = api("/api/health")
    check("health ok", h.get("status") == "ok", str(h))

    print("\n== 2. 写作闭环（chat 写一章）==")
    r = api("/api/chat", {"message": "写第二章：陈渡在雾城码头遇到一个戴白手套的神秘人，约150字。"})
    conv = r.get("conversation_id", "")
    check("返回 conversation_id", bool(conv))
    check("正文非空", len(r.get("text", "")) > 50)
    # 多轮续写
    r2 = api("/api/chat", {"message": "继续写神秘人递给他一张泛黄的照片", "conversation_id": conv})
    check("续写同会话", r2.get("conversation_id") == conv and len(r2.get("text", "")) > 20)

    print("\n== 3. 图谱自动抽取（后台异步，等待）==")
    chapters = api("/api/chapters")
    check("章节落盘", len(chapters) >= 1, str(len(chapters)))
    for _ in range(12):  # 最多等 60s（后台 LLM 抽取 15-30s）
        ents = api("/api/graph/entities")
        if len(ents) >= 3:
            break
        time.sleep(5)
    check("图谱实体≥3", len(ents) >= 3, f"实际 {len(ents)}")
    ctx = api("/api/graph/context")
    check("注入块非空", len(ctx.get("block", "")) > 50)

    print("\n== 4. 对齐系统 ==")
    api("/api/manual", {"content": "叙事克制，少用感叹号"})
    manual = api("/api/manual")
    check("说明书条目", len(manual) >= 1)
    api("/api/signals", {"kind": "accepted", "content": "这段很好"})
    agency = api("/api/agency")
    check("能动性档位存在", "current" in agency and len(agency.get("levels", [])) == 5)

    print("\n== 5. 探索引擎 ==")
    intent = api("/api/explore/intent", {"seed": "码头雾夜，白手套神秘人递照片"})
    check("意图理解", len(intent.get("concept", "")) > 10 or len(intent) > 1, str(intent)[:80])
    cards = api("/api/explore/cards", {"seed": "码头雾夜", "intent_confirmed": {}})
    check("方向卡×4", len(cards) >= 2, f"实际 {len(cards)}")

    print("\n== 6. 检测网 + 图谱证据 ==")
    chk = api(
        "/api/check",
        {"text": "陈渡在码头遇到神秘人，递给他一张泛黄的照片。", "target": "第二章"},
    )
    check("检测报告", "findings" in chk)
    check("图谱证据", len(chk.get("graph_evidence", "")) > 20)
    rule = api("/api/check/rule", {"rule": "不要感叹号", "text": "太棒了！他笑了。"})
    check("规则检测命中", rule.get("ok") is True and rule.get("hits"))

    print("\n== 7. 资料消化 + 图谱关联 ==")
    mat = api(
        "/api/materials",
        {
            "text": "雾城设定：海边港口城市，终年多雾，港区有一家钟表铺，店主老周。",
            "title": "雾城设定",
        },
    )
    check("摘要卡入库", "id" in mat)
    mats = api("/api/materials")
    check("资料列表", len(mats) >= 1)

    print("\n== 8. S10 交互端点 ==")
    d = api("/api/chat/direction", {"prompt": "写第三章：神秘人的来历", "context": "陈渡是侦探"})
    check("方向声明", "方向声明" in d.get("direction", ""))
    c = api("/api/chat/candidates", {"prompt": "写白手套神秘人揭面的瞬间", "n": 2})
    check("候选卡×2", len(c.get("candidates", [])) == 2)
    rw = api("/api/chat/rewrite", {"text": "他接过照片。", "mode": "bold"})
    check("改写", len(rw.get("rewritten", "")) > 10)
    if chapters:
        wu = api(f"/api/chapters/{chapters[0]['id']}/wrapup", method="POST")
        check("一章收尾", bool(wu.get("summary") or wu.get("next_hint")))

    print("\n== 9. SSE 流式 ==")
    body = json.dumps({"message": "写一句雾城夜景，不要调用工具"}).encode()
    req = urllib.request.Request(
        BASE + "/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with _opener.open(req, timeout=180) as resp:
        text = resp.read().decode()
    has_delta = "event: text_delta" in text and "event: done" in text
    check("SSE 帧（text_delta+done）", has_delta)

    print("\n== 10. 沙箱文件 + 导出 ==")

    (api("/api/chat", {"message": "写一句话到沙箱文件 notes/e2e.md：全流程自测通过。"}))
    time.sleep(3)
    import pathlib

    sb = pathlib.Path(__file__).resolve().parents[1] / "data" / "sandbox" / "notes" / "e2e.md"
    check("沙箱落盘", sb.exists(), str(sb))
    if chapters:
        export = _opener.open(
            f"{BASE}/api/chapters/{chapters[0]['id']}/export?format=md", timeout=30
        )
        md = export.read().decode()
        check("导出 md", md.startswith("# "))

    # S147d：批量审读全流程（真实模型 1 章）——启动→执行→loop 迭代明细保留
    try:
        wfs = api("/api/workflows")
        wf_id = next(w["id"] for w in wfs if w["name"] == "批量审读")
        run = api(
            f"/api/workflows/{wf_id}/run",
            {"book_id": "main", "params": {"chapter_ids": json.dumps([chapters[0]["id"]])}},
        )
        tid = run["task_id"]
        t = None
        for _ in range(120):  # 真实模型审读最长 ~4 分钟
            t = api(f"/api/workflows/tasks/{tid}")
            if t.get("status") in ("done", "failed"):
                break
            time.sleep(2)
        check("批量审读完成", t is not None and t.get("status") == "done", str(t)[:200])
        if t and t.get("status") == "done":
            loop = next(
                (s for s in (t.get("node_states") or []) if s.get("node_id") == "loop"),
                None,
            )
            items = json.loads(loop["output"] or "{}").get("items", []) if loop else []
            check(
                "批量审读 loop 迭代明细（每章结果保留）",
                len(items) >= 1 and any("review" in it for it in items),
                f"items={len(items)}",
            )
    except Exception as e:
        check("批量审读链路", False, str(e)[:200])

    print(f"\n================ 结果: {ok} 通过 / {fail} 失败 ================")
    raise SystemExit(1 if fail else 0)


if __name__ == "__main__":
    main()
