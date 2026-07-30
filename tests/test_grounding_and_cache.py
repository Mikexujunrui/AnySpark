from core.extraction_cache import ExtractionCache
from core.grounding import ground_progressive_result
from core.settings import AppSettings, ModelSlot, ProviderConfig, validate_runtime_settings


def test_grounding_filters_unsupported_entities_and_relations():
    result = {
        "new_entities": [
            {"type": "character", "name": "林舟", "aliases": [], "data": {"身份": "剑客"}},
            {"type": "character", "name": "幻觉人物", "aliases": [], "data": {"身份": "不存在"}},
        ],
        "updates": [],
        "relations": [
            {"from": "林舟", "to": "青云山", "type": "located_at"},
            {"from": "林舟", "to": "幻觉地点", "type": "located_at"},
        ],
        "spatial_relations": [],
        "foreshadows": [],
        "timeline_events": [],
    }
    text = "林舟提剑登上青云山，回望来路。"

    grounded, stats = ground_progressive_result(result, text, "#1", "山门")

    assert [entity["name"] for entity in grounded["new_entities"]] == ["林舟"]
    assert len(grounded["relations"]) == 1
    assert grounded["new_entities"][0]["data"]["_sources"][0]["chapter_id"] == "#1"
    assert stats.dropped_entities == 1
    assert stats.dropped_relations == 1


def test_extraction_cache_uses_content_fingerprint(tmp_path, monkeypatch):
    import core.extraction_cache as cache_module

    monkeypatch.setattr(cache_module, "DATA_DIR", tmp_path)
    cache = ExtractionCache("book:1")
    assert not cache.is_current("chapter-1", "正文")

    cache.mark("chapter-1", "正文")
    cache.save()
    reloaded = ExtractionCache("book:1")
    assert reloaded.is_current("chapter-1", "正文")
    assert not reloaded.is_current("chapter-1", "修改后的正文")


def test_runtime_preflight_reports_missing_key_and_model():
    provider = ProviderConfig(id="p1", name="测试供应商", type="openai", api_key="", models=["m1"])
    settings = AppSettings(
        providers=[provider],
        slot_pro=ModelSlot(provider_id="p1", model="m1"),
        slot_flash=ModelSlot(provider_id="p1", model=""),
        mode="split",
    )

    errors = validate_runtime_settings(settings)

    assert any("API Key" in error for error in errors)
    assert any("尚未选择模型" in error for error in errors)


def test_runtime_preflight_accepts_complete_configuration():
    provider = ProviderConfig(id="p1", name="测试供应商", type="openai", api_key="secret", models=["m1"])
    settings = AppSettings(
        providers=[provider],
        slot_pro=ModelSlot(provider_id="p1", model="m1"),
        slot_flash=ModelSlot(provider_id="p1", model="m1"),
        mode="split",
    )

    assert validate_runtime_settings(settings) == []


def test_legacy_frozen_data_migration_is_copy_only(tmp_path, monkeypatch):
    import json
    import sys

    import core.config as config_module

    legacy_root = tmp_path / "old-portable"
    legacy_data = legacy_root / "data"
    legacy_data.mkdir(parents=True)
    (legacy_data / "books.json").write_text('[{"id":"book-1"}]', encoding="utf-8")
    (legacy_data / "settings.json").write_text('{"providers":[]}', encoding="utf-8")
    target_root = tmp_path / "appdata" / "AnySpark"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(legacy_root / "AnySpark.exe"))
    migrated_from = config_module._migrate_legacy_frozen_data(target_root)

    assert migrated_from == str(legacy_root)
    assert json.loads((target_root / "data" / "books.json").read_text(encoding="utf-8"))[0]["id"] == "book-1"
    assert (legacy_data / "books.json").exists()
    assert json.loads((target_root / "migration.json").read_text(encoding="utf-8"))["source_preserved"] is True


def test_pre_upgrade_backup_is_created_once_per_version(tmp_path, monkeypatch):
    import sys
    import zipfile

    import core.config as config_module

    target_root = tmp_path / "AnySpark"
    data_dir = target_root / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "books.json").write_text('[{"id":"book-1"}]', encoding="utf-8")
    (target_root / ".install-version").write_text("3.0.1", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(config_module, "APP_VERSION", "3.1.0")

    backup = config_module._backup_data_before_upgrade(target_root, data_dir)
    assert backup is not None and backup.exists()
    with zipfile.ZipFile(backup) as archive:
        assert "books.json" in archive.namelist()
    assert (target_root / ".install-version").read_text(encoding="utf-8") == "3.1.0"
    assert config_module._backup_data_before_upgrade(target_root, data_dir) is None
