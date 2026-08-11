"""anyspark.explore.direction — 项目档案/方向卡测试。"""

import tempfile
from pathlib import Path

from anyspark.explore import DirectionCard, ProjectArchive


def _archive() -> ProjectArchive:
    return ProjectArchive(Path(tempfile.mkdtemp()) / "test.db")


def test_archive_direction() -> None:
    arc = _archive()
    try:
        card = DirectionCard(
            title="废柴流开局",
            summary="主角开局废柴，暗藏天选身份",
            dimension="情节驱动",
            source="template",
            term="废柴流开局·反差铺垫",
        )
        arc.archive_direction(card)
        dirs = arc.directions()
        assert len(dirs) == 1
        assert dirs[0]["title"] == "废柴流开局"
        assert dirs[0]["source"] == "template"
    finally:
        arc.close()


def test_archive_constraints_moved_to_settings() -> None:
    """S83：约束已从 ProjectArchive 移入设定档（WorldSettingStore is_constraint）。"""
    import tempfile
    from pathlib import Path

    from anyspark.align.worldsettings import WorldSettingStore

    ws = WorldSettingStore(Path(tempfile.mkdtemp()) / "test.db")
    try:
        ws.add("女主=医者", is_constraint=1)
        ws.add("故事发生地=雾城", is_constraint=1, entities="雾城")
        ws.add("雾城是个海边小城", category="地点")  # 非约束不注入
        cons = ws.list_constraints()
        assert len(cons) == 2
        assert all(c.is_constraint == 1 for c in cons)
    finally:
        ws.close()
