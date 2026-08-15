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
