"""anyspark.align.inject — 注入器测试（项目级 > 全局级）。"""

import tempfile
from pathlib import Path

from anyspark.align import (
    ManualEntry,
    ManualInjector,
    ManualStore,
    MemoryStore,
    SceneMemory,
)


def _db(name: str) -> Path:
    return Path(tempfile.mkdtemp()) / name


def test_inject_project_overrides_global() -> None:
    store = ManualStore(_db("m.db"))
    try:
        store.add(ManualEntry(content="全局：避免长句", scope="global", confidence=0.9))
        store.add(ManualEntry(content="本书：允许长句渲染氛围", scope="project", confidence=0.9))
        injector = ManualInjector(store)
        block = injector.build_system_block("main")
        # 两块都在，项目级在后（覆盖语义）
        assert "全局写作偏好" in block
        assert "本书写作偏好" in block
        assert "允许长句渲染氛围" in block
    finally:
        store.close()


def test_inject_empty_manual() -> None:
    store = ManualStore(_db("m2.db"))
    try:
        injector = ManualInjector(store)
        assert injector.build_system_block("main") == ""
    finally:
        store.close()


def test_memory_injector() -> None:
    mem = MemoryStore(_db("mem.db"))
    try:
        mem.save(SceneMemory(content="已决定主角是医生", book_id="main"))
        from anyspark.align import MemoryInjector

        inj = MemoryInjector(mem)
        block = inj.build_block("main")
        assert "主角是医生" in block
    finally:
        mem.close()
