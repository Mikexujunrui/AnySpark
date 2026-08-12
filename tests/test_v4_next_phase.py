from __future__ import annotations

import asyncio
from types import SimpleNamespace


def _fact(value, evidence, confidence="high"):
    return {"value": value, "evidence": evidence, "confidence": confidence}


def test_continuity_audit_only_reports_two_sided_high_confidence():
    from core.continuity import audit_transition, format_continuity_cards

    previous = {
        "chapter_index": 1,
        "chapter_time": {"start": "早晨", "end": "黄昏", "elapsed": "十小时"},
        "end_state": {
            "characters": {
                "林岚": {
                    "location": _fact("山门", "她停在山门前"),
                    "physical_state": _fact("左臂受伤", "左臂的血浸透衣袖"),
                }
            }
        },
    }
    current = {
        "chapter_index": 2,
        "start_state": {
            "characters": {
                "林岚": {
                    "location": _fact("客栈", "林岚推开客栈房门"),
                    # A low-confidence disagreement must not become an alarm.
                    "physical_state": _fact("完好", "她抬起手", "low"),
                }
            }
        },
        "end_state": {"characters": {}},
    }

    audit = audit_transition(previous, current)
    assert audit["checked_fields"] == 1
    assert len(audit["confirmed_conflicts"]) == 1
    assert audit["confirmed_conflicts"][0]["field"] == "location"
    rendered = format_continuity_cards([previous, {**current, "transition_audit": audit}])
    assert "主时间范围" in rendered
    assert "已确认交接冲突" in rendered


def test_timeline_story_time_fields_survive_sqlite_roundtrip(tmp_path):
    from core.knowledge import TimelineEvent
    from core.sqlite_store import SQLiteStore

    store = SQLiteStore("timeline-book", db_path=tmp_path / "graph.db")
    try:
        store.add_timeline_event(
            TimelineEvent(
                id="evt-memory",
                time_point="第3章",
                label="五日前的争执",
                time_order=3.1,
                chapter_ref="#3",
                narrative_time="五日前",
                temporal_layer="flashback",
                absolute_start="",
                absolute_end="",
                relative_to="#3当前清晨",
                source_evidence="五日前，他曾在桥头争辩",
                confidence="high",
            )
        )
        event = store.list_timeline_events()[0]
        assert event.temporal_layer == "flashback"
        assert event.relative_to == "#3当前清晨"
        assert event.source_evidence.startswith("五日前")
        view = store.get_timeline_for_view()
        assert view["events"][0]["track_id"] == "time-flashback"
        assert view["events"][0]["confidence"] == "high"
    finally:
        store.close()


def test_plot_norms_are_crud_and_only_active_rules_enter_prompt(tmp_data_dir):
    from core.plot_norms import build_plot_norms_prompt
    from data.json_store import json_store

    book = json_store.create_book("规范测试")
    active = json_store.add_plot_norm(
        book["id"],
        {"name": "慢燃调查", "rules": ["本章只确认一条线索"], "avoid": ["突然自白"], "active": True},
    )
    disabled = json_store.add_plot_norm(
        book["id"],
        {"name": "停用模板", "rules": ["不应出现"], "active": False},
    )

    prompt = build_plot_norms_prompt(book["id"])
    assert "本章只确认一条线索" in prompt
    assert "突然自白" in prompt
    assert "不应出现" not in prompt

    json_store.update_plot_norm(book["id"], active["id"], {"active": False})
    assert build_plot_norms_prompt(book["id"]) == ""
    assert json_store.delete_plot_norm(book["id"], disabled["id"]) is True


def test_reference_job_checkpoints_chunks_and_completes(tmp_data_dir, monkeypatch):
    import core.reference_jobs as jobs
    from data.json_store import json_store

    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_data_dir / "analyses" / "reference_jobs.json")
    jobs._running.clear()
    ref = json_store.create_book("大参考书")
    owner = json_store.create_book("当前书")
    json_store.set_reference_books(owner["id"], [ref["id"]])
    for index in range(45):
        json_store.add_chapter(ref["id"], f"第{index + 1}章", "正文" * 120)

    monkeypatch.setattr(jobs, "_cached", lambda *_args: False)
    monkeypatch.setattr(jobs, "_run_step", lambda *_args: SimpleNamespace(chapter_count=45))
    job = jobs.create_job(owner["id"], ref["id"], steps=["structure", "style_fingerprint"], chunk_size=20)
    result = asyncio.run(jobs.run_job(job["id"]))

    assert result["status"] == "completed"
    assert result["progress"] == 100
    assert len(result["source_chunks"]) == 3
    assert [(chunk["chapter_start"], chunk["chapter_end"]) for chunk in result["source_chunks"]] == [
        (1, 20), (21, 40), (41, 45)
    ]
    assert all(step["status"] == "completed" for step in result["steps"])


def test_desktop_native_export_returns_exact_path(tmp_data_dir, tmp_path):
    from data.json_store import json_store
    from desktop_launcher import DesktopApi

    book = json_store.create_book("导出路径测试")
    json_store.add_chapter(book["id"], "第一章", "这是一段正文。")
    destination = tmp_path / "用户选择的位置.txt"

    class FakeWindow:
        def create_file_dialog(self, *_args, **_kwargs):
            return str(destination)

    api = DesktopApi(SimpleNamespace(window=FakeWindow()))
    result = api.export_book(book["id"], "txt")
    assert result == {"saved": True, "path": str(destination), "filename": destination.name}
    assert "这是一段正文" in destination.read_text(encoding="utf-8")


def test_spark_roundtrip_to_new_book_id_preserves_next_phase_data(tmp_data_dir, tmp_path, monkeypatch):
    from core.archive import export_spark, import_spark
    from core.graph_store import GraphStore
    from core.knowledge import Entity, TimelineEvent
    from core.sqlite_store import SQLiteStore
    from data.json_store import json_store

    monkeypatch.setattr(SQLiteStore, "_db_dir", tmp_data_dir)
    source = json_store.create_book("旧电脑长篇")
    target = json_store.create_book("新电脑长篇")
    json_store.add_chapter(source["id"], "第一章", "正文没有丢失。")
    json_store.save_continuity_cards(source["id"], {"chapters": {"1": {"chapter_index": 1}}})
    json_store.add_plot_norm(source["id"], {"name": "只推进一个节点", "active": True})

    source_graph = GraphStore(source["id"])
    source_graph.add_entity(Entity(id="person-lin", type="character", name="林岚"))
    source_graph.add_timeline_event(
        TimelineEvent(
            id="evt-letter",
            time_point="第1章",
            label="读到五日前的信",
            time_order=1,
            temporal_layer="letter",
            relative_to="当前时间前五日",
            source_evidence="信纸落款写着五日前",
            confidence="high",
        )
    )

    archive = tmp_path / "portable.spark"
    export_spark(source["id"], str(archive))
    stats = import_spark(target["id"], str(archive))

    assert stats["chapters"] == 1
    assert stats["entities"] == 1
    assert stats["timeline_events"] == 1
    assert json_store.load_continuity_cards(target["id"])["chapters"]["1"]["chapter_index"] == 1
    assert json_store.load_plot_norms(target["id"])[0]["name"] == "只推进一个节点"
    imported_event = GraphStore(target["id"]).list_timeline_events()[0]
    assert imported_event.temporal_layer == "letter"
    assert imported_event.source_evidence == "信纸落款写着五日前"
