import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect all data-file paths to a temp directory.

    json_store / task_queue / scheduler / git_store all import DATA_DIR
    from core.config at module level. Simply replacing core.config.DATA_DIR
    does NOT affect those modules' own references.  We force-import each
    module before monkeypatching to ensure the right DATA_DIR is captured.
    """
    import importlib

    import core.config as cfg

    # core.config (used by dynamic lookups)
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)

    # data/stores/_base — all file-path helpers reference its own DATA_DIR
    base_mod = sys.modules.get("data.stores._base")
    if base_mod is None:
        base_mod = importlib.import_module("data.stores._base")
    monkeypatch.setattr(base_mod, "DATA_DIR", tmp_path)
    # The singleton's _books_file was set in __init__ before the patch
    from data.json_store import json_store
    json_store._books_file = tmp_path / "books.json"

    # core/task_queue — module-level singleton cached the original DATA_DIR
    tq_mod = sys.modules.get("core.task_queue")
    if tq_mod is None:
        tq_mod = importlib.import_module("core.task_queue")
    monkeypatch.setattr(tq_mod, "DATA_DIR", tmp_path)
    tq_mod.task_queue._dir = tmp_path
    tq_mod.task_queue._file = tmp_path / "task_queue.json"

    # core/scheduler
    sch_mod = sys.modules.get("core.scheduler")
    if sch_mod is None:
        sch_mod = importlib.import_module("core.scheduler")
    monkeypatch.setattr(sch_mod, "DATA_DIR", tmp_path)

    yield tmp_path


@pytest.fixture
def sample_chapters():
    return [
        {"id": "ch1", "title": "第一章 初入江湖", "content": "少年李逸站在山门前..." * 100, "createdAt": "2026-01-01T00:00:00"},
        {"id": "ch2", "title": "第二章 初次交手", "content": "剑光闪烁，李逸拔剑迎敌..." * 100, "createdAt": "2026-01-02T00:00:00"},
        {"id": "ch3", "title": "第三章 真相大白", "content": "师父微笑着看向他..." * 100, "createdAt": "2026-01-03T00:00:00"},
    ]


@pytest.fixture
def sample_entities():
    return [
        {"id": "e1", "type": "character", "name": "李逸", "aliases": ["小李"], "data": {"age": "18", "faction": "青云门"}},
        {"id": "e2", "type": "character", "name": "张三", "aliases": [], "data": {"age": "30", "role": "师父"}},
        {"id": "e3", "type": "location", "name": "青云山", "aliases": ["青云门所在"], "data": {"region": "中原"}},
    ]
