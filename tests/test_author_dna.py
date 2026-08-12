from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def dna_env(monkeypatch, tmp_path):
    from core import author_dna

    monkeypatch.setattr(author_dna, "DNA_DIR", tmp_path)
    chapters = [
        {
            "id": "chapter-1",
            "title": "第一章",
            "content": "甲乙相处。" * 1600,
        }
    ]
    monkeypatch.setattr(author_dna.json_store, "get_reference_books", lambda _book_id: ["reference-1"])
    monkeypatch.setattr(
        author_dna.json_store,
        "get_reference_profiles",
        lambda _book_id: {"reference-1": "style"},
    )
    monkeypatch.setattr(
        author_dna.json_store,
        "get_book",
        lambda ref_id: (
            {"id": ref_id, "title": "当前续写", "projectType": "continuation"}
            if ref_id == "project"
            else {"id": ref_id, "title": "作者样本一", "projectType": "original"}
        ),
    )
    monkeypatch.setattr(
        author_dna,
        "get_settings",
        lambda: SimpleNamespace(experimental_features={"author_dna_lab": True}),
    )
    monkeypatch.setattr(author_dna.json_store, "load_chapters", lambda _ref_id: chapters)
    monkeypatch.setattr(author_dna.json_store, "_chapter_view", lambda chapter: chapter)
    return author_dna


def test_author_dna_requires_global_opt_in_and_continuation_project(dna_env, monkeypatch):
    monkeypatch.setattr(
        dna_env,
        "get_settings",
        lambda: SimpleNamespace(experimental_features={"author_dna_lab": False}),
    )
    availability = dna_env.get_author_dna_availability("project")
    assert availability["available"] is False
    assert "实验性功能" in availability["reason"]

    monkeypatch.setattr(
        dna_env,
        "get_settings",
        lambda: SimpleNamespace(experimental_features={"author_dna_lab": True}),
    )
    monkeypatch.setattr(
        dna_env.json_store,
        "get_book",
        lambda book_id: {"id": book_id, "projectType": "original"},
    )
    availability = dna_env.get_author_dna_availability("project")
    assert availability["available"] is False
    assert "只对标记为续写" in availability["reason"]

    monkeypatch.setattr(
        dna_env.json_store,
        "get_book",
        lambda book_id: {"id": book_id, "projectType": "continuation"},
    )
    assert dna_env.get_author_dna_availability("project")["available"] is True


def test_author_dna_experiment_is_disabled_after_legacy_settings_upgrade():
    from core.settings import AppSettings

    settings = AppSettings.from_dict({"providers": []})
    assert settings.experimental_features["author_dna_lab"] is False
    settings.experimental_features["author_dna_lab"] = True
    assert AppSettings.from_dict(settings.to_dict(mask_keys=False)).experimental_features["author_dna_lab"] is True


def test_author_dna_api_is_blocked_when_experiment_is_unavailable(monkeypatch):
    from fastapi import HTTPException

    from routes import author_dna as author_dna_routes

    monkeypatch.setattr(
        author_dna_routes,
        "get_author_dna_availability",
        lambda _book_id: {"available": False, "reason": "实验功能未开启"},
    )
    with pytest.raises(HTTPException) as exc_info:
        author_dna_routes.get_author_dna("original-project")
    assert exc_info.value.status_code == 403
    assert "实验功能未开启" in str(exc_info.value.detail)


def test_corpus_map_has_stable_evidence_ids_and_quartile_coverage(dna_env):
    state = dna_env.build_corpus_map("project", chunk_chars=2000, batch_size=2)

    corpus = state["corpus"]
    assert corpus["status"] == "ready"
    assert corpus["total_chunks"] == 4
    assert corpus["estimated_calls"] == 2 + 6 + 1
    ids = [chunk["id"] for chunk in corpus["chunks"]]
    assert len(set(ids)) == 4
    assert ids[0].startswith("R-") and ids[0].endswith("-C0001-B001")
    assert ids[-1].endswith("-C0001-B004")
    assert corpus["coverage"][0]["quartiles"] == {
        "0-25%": 1,
        "25-50%": 1,
        "50-75%": 1,
        "75-100%": 1,
    }

    rebuilt = dna_env.build_corpus_map("project", chunk_chars=2000, batch_size=2)
    assert rebuilt["corpus"]["signature"] == corpus["signature"]
    assert [chunk["fingerprint"] for chunk in rebuilt["corpus"]["chunks"]] == [
        chunk["fingerprint"] for chunk in corpus["chunks"]
    ]


def test_canon_only_reference_is_not_silently_used_as_author_style(dna_env, monkeypatch):
    monkeypatch.setattr(
        dna_env.json_store,
        "get_reference_profiles",
        lambda _book_id: {"reference-1": "canon"},
    )
    with pytest.raises(ValueError, match="文风参考书"):
        dna_env.build_corpus_map("project")


def test_unreviewed_dna_never_enters_writer_context(dna_env):
    state = dna_env.build_corpus_map("project", chunk_chars=4000)
    state["layers"]["scene_grammar"].update(
        {
            "status": "needs_review",
            "rules": [{"text": "未确认的场景规则"}],
            "anti_style": [],
        }
    )
    dna_env.save_state("project", state)
    assert "未确认的场景规则" not in dna_env.build_author_dna_context("project")

    dna_env.update_layer("project", "scene_grammar", {"status": "accepted"})
    assert "未确认的场景规则" in dna_env.build_author_dna_context("project")


def test_interpretation_is_separate_until_explicit_acceptance_and_promotion(dna_env):
    dna_env.build_corpus_map("project", chunk_chars=4000)
    entry = dna_env.add_interpretation("project", {"statement": "人物害羞但并不缺乏主动欲望"})
    assert "人物害羞" not in dna_env.build_author_dna_context("project")

    dna_env.update_interpretation("project", entry["id"], {"status": "accepted"})
    context = dna_env.build_author_dna_context("project")
    assert "用户的作品解读" in context
    assert "人物害羞" in context
    assert "本续写采用的解释 Canon" not in context

    dna_env.update_interpretation("project", entry["id"], {"promoted": True})
    context = dna_env.build_author_dna_context("project")
    assert "本续写采用的解释 Canon" in context


def test_scene_contract_drops_future_plan_and_compiles_only_current_scene(dna_env):
    contract = dna_env.save_scene_contract(
        "project",
        {
            "enabled": True,
            "creative_intent": "表现第一次主动但性格仍连续",
            "purpose": "让关系轻微推进",
            "beats": ["她没有退开", "她抓住对方衣袖"],
            "start_state": "两人仍在犹豫",
            "end_state": "她完成一次微小主动",
            "stop_anchor": "对方尚未回答",
            "future_plan": ["下一场正式告白"],
        },
    )
    assert "future_plan" not in contract

    package = dna_env.compile_writer_package("project")
    text = package["text"]
    assert "表现第一次主动但性格仍连续" in text
    assert "她抓住对方衣袖" in text
    assert "对方尚未回答" in text
    assert "正式告白" not in text
    assert "未来事件不得猜测" in text

    # The runtime package keeps all future beats out of the cacheable system
    # prefix.  Each node receives only its own beat via NarrativeSegmentContract.
    runtime = dna_env.build_active_writer_package("project")
    assert "她抓住对方衣袖" not in runtime
    one_call = dna_env.build_active_writer_package("project", include_beats=True)
    assert "她抓住对方衣袖" in one_call


def test_narrative_contract_hides_future_event_names():
    from core.narrative_budget import NarrativeSegmentContract

    contract = NarrativeSegmentContract(
        index=1,
        total=3,
        beat="进入便利店",
        target_chars=800,
        max_chars=1000,
        forbidden_future=["女主告白", "两人争吵"],
        end_state="女主拿起饮料",
    )
    prompt = contract.render_prompt()
    assert "未来剧情的具体内容已由系统隐藏" in prompt
    assert "女主告白" not in prompt
    assert "两人争吵" not in prompt


@pytest.mark.asyncio
async def test_analysis_job_resumes_by_batch_and_leaves_layers_for_review(dna_env, monkeypatch):
    dna_env.build_corpus_map("project", chunk_chars=4000, batch_size=1)

    monkeypatch.setattr(
        dna_env,
        "_extract_batch",
        lambda _book_id, batch: [
            {
                "id": f"obs-{batch[0]['id']}",
                "layer": "story_engine",
                "claim": "关系由微小互动推进",
                "evidence_ids": [batch[0]["id"]],
                "counterexample_ids": [],
                "confidence": "medium",
                "scope": "work",
            }
        ],
    )

    def fake_synthesize(_book_id, key, observations):
        assert observations
        return {
            "key": key,
            "label": dna_env.LAYER_LABELS[key],
            "status": "needs_review",
            "summary": key,
            "rules": [{"text": f"rule-{key}", "evidence_ids": observations[0]["evidence_ids"]}],
            "anti_style": [],
            "evidence_ids": observations[0]["evidence_ids"],
            "updated_at": "now",
        }

    monkeypatch.setattr(dna_env, "_synthesize_layer", fake_synthesize)
    monkeypatch.setattr(
        dna_env,
        "_cross_audit",
        lambda _book_id, _layers: {
            "status": "needs_review",
            "passed": True,
            "conflicts": [],
            "warnings": [],
        },
    )

    job = dna_env.create_analysis_job("project")
    completed = await dna_env.run_analysis_job("project", job["id"])
    state = dna_env.load_state("project")

    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert state["observations"]
    assert all(layer["status"] == "needs_review" for layer in state["layers"].values())
    assert dna_env.build_author_dna_context("project") == ""


def test_interpretation_verifier_filters_untrusted_evidence_ids(dna_env, monkeypatch):
    dna_env.build_corpus_map("project", chunk_chars=4000, batch_size=1)
    entry = dna_env.add_interpretation("project", {"statement": "人物通过动作隐藏情绪"})
    monkeypatch.setattr(
        dna_env,
        "_call_json",
        lambda *_args, **_kwargs: {
            "classification": "plausible",
            "confidence": "medium",
            "reason": "候选片段与该解读相容",
            "evidence_ids": [dna_env.load_state("project")["corpus"]["chunks"][0]["id"], "fake-id"],
            "counter_evidence_ids": ["fake-id"],
        },
    )
    verified = dna_env.verify_interpretation("project", entry["id"])
    assert verified["classification"] == "plausible"
    assert "fake-id" not in verified["evidence_ids"]
    assert "fake-id" not in verified["counter_evidence_ids"]
    assert verified["status"] == "draft"


@pytest.mark.asyncio
async def test_delegate_writing_uses_active_scene_instead_of_future_instruction(monkeypatch, tmp_data_dir):
    import asyncio

    from core import author_dna
    from data.json_store import json_store
    from tools.impl import writing

    monkeypatch.setattr(author_dna, "DNA_DIR", tmp_data_dir / "author-dna")
    monkeypatch.setattr(
        author_dna,
        "get_settings",
        lambda: SimpleNamespace(experimental_features={"author_dna_lab": True}),
    )
    book = json_store.create_book("场景隔离测试", "")
    json_store.update_book(book["id"], {"projectType": "continuation"})
    author_dna.save_scene_contract(
        book["id"],
        {
            "enabled": True,
            "target_words": 1200,
            "purpose": "只完成当前试探",
            "start_state": "双方尚未表态",
            "end_state": "她第一次没有退开",
            "stop_anchor": "对方尚未回答",
            "beats": ["普通闲聊", "她抓住对方衣袖"],
        },
    )

    captured = {}

    async def fake_write_by_nodes(
        _loop,
        _context,
        _references,
        plot_chain,
        _chapter_function,
        writing_rules,
        _system,
        _book_id,
        _queue,
        _per_node,
        **kwargs,
    ):
        captured["plot_chain"] = plot_chain
        captured["writing_rules"] = writing_rules
        captured.update(kwargs)
        return "这是正文。" * 30, None

    async def fake_verify(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(writing, "_write_by_nodes", fake_write_by_nodes)
    monkeypatch.setattr("tools.impl.narrative_logic._verify_chapter", fake_verify)

    class FakeKB:
        def list_entities(self):
            return []

        def get_graph_insights(self):
            return {}

    result = await writing._delegate_writing_streaming(
        asyncio.get_running_loop(),
        {
            "instruction": "把当前试探、未来正式告白和最终结局一次写完",
            "chapter_title": "测试章",
            "target_words": 8000,
            "segment_plan": [{"beat": "未来正式告白"}],
        },
        FakeKB(),
        book["id"],
        "把未来正式告白也写完",
        queue=None,
    )

    assert result["saved"] is True
    assert captured["target_words"] == 1200
    assert [item["beat"] for item in captured["plot_chain"]] == ["普通闲聊", "她抓住对方衣袖"]
    assert "未来正式告白" not in captured["writing_rules"]
    assert "普通闲聊" not in captured["writing_rules"]
    assert "她抓住对方衣袖" not in captured["writing_rules"]
    assert "只完成当前试探" in captured["writing_rules"]


def test_spark_preserves_confirmed_dna_without_copying_reference_corpus(monkeypatch, tmp_data_dir, tmp_path):
    import zipfile

    from core import author_dna
    from core.archive import export_spark, import_spark
    from core.sqlite_store import SQLiteStore
    from data.json_store import json_store

    monkeypatch.setattr(author_dna, "DNA_DIR", tmp_data_dir / "author-dna")
    monkeypatch.setattr(
        author_dna,
        "get_settings",
        lambda: SimpleNamespace(experimental_features={"author_dna_lab": True}),
    )
    monkeypatch.setattr(SQLiteStore, "_db_dir", tmp_data_dir)
    source = json_store.create_book("DNA 来源项目", "")
    target = json_store.create_book("DNA 迁移项目", "")
    json_store.update_book(source["id"], {"projectType": "continuation"})
    state = author_dna.load_state(source["id"])
    state["corpus"].update(
        {
            "status": "ready",
            "reference_ids": ["external-reference"],
            "chunks": [{"id": "sensitive-chunk", "preview": "不应被归档的原文"}],
            "coverage": [{"title": "原作者样本"}],
            "total_chars": 200000,
        }
    )
    state["layers"]["scene_grammar"].update(
        {"status": "accepted", "rules": [{"text": "用微动作承载关系变化"}], "anti_style": []}
    )
    state["interpretations"] = [
        {
            "id": "interp-portable",
            "statement": "人物的害羞主要发生在表达层",
            "status": "accepted",
            "promoted": True,
        }
    ]
    state["scene_contract"] = {"enabled": True, "purpose": "当前场景"}
    author_dna.save_state(source["id"], state)

    archive_path = tmp_path / "author-dna.spark"
    export_spark(source["id"], str(archive_path))
    with zipfile.ZipFile(archive_path) as archive:
        portable = archive.read("author_dna.json").decode("utf-8")
        assert "用微动作承载关系变化" in portable
        assert "不应被归档的原文" not in portable
        assert "sensitive-chunk" not in portable

    import_spark(target["id"], str(archive_path))
    assert json_store.get_book(target["id"])["projectType"] == "continuation"
    restored = author_dna.load_state(target["id"])
    assert restored["book_id"] == target["id"]
    assert restored["corpus"]["status"] == "detached"
    assert restored["corpus"]["portable_confirmed"] is True
    assert restored["corpus"]["chunks"] == []
    assert restored["layers"]["scene_grammar"]["status"] == "accepted"
    assert restored["interpretations"][0]["promoted"] is True
    assert restored["scene_contract"]["enabled"] is True
    assert "用微动作承载关系变化" in author_dna.build_author_dna_context(target["id"])

    from core.writer import _build_reference_context

    assert "用微动作承载关系变化" in _build_reference_context(target["id"])
