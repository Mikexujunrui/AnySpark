# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for continuation pipeline, annotation engine, and emotional curve."""

from core.annotation_engine import (
    AnnotationCertainty,
    AnnotationDatabase,
    AnnotationEntry,
    AnnotationType,
    build_annotation_constraints,
    load_annotation_database,
    save_annotation_database,
)
from core.continuation_pipeline import (
    ActConstraintBundle,
    ContinuationContract,
    validate_chapter_content,
)


class TestAnnotationEntry:
    def test_basic_creation(self):
        entry = AnnotationEntry(
            id="ann_001",
            critic="批注者A",
            target_chapter=1,
            target_text="满纸荒唐言",
            comment_text="此是第一首标题诗",
            comment_type=AnnotationType.TECHNIQUE_COMMENT,
            implied_outcome="全书主旨",
            certainty=AnnotationCertainty.HIGH,
            related_characters=["作者"],
            must_fulfill=False,
        )
        assert entry.id == "ann_001"
        assert entry.certainty == AnnotationCertainty.HIGH

    def test_all_types_defined(self):
        assert AnnotationType.PLOT_HINT.value == "plot_hint"
        assert AnnotationType.CHARACTER_FATE.value == "character_fate"
        assert AnnotationType.TECHNIQUE_COMMENT.value == "technique_comment"
        assert AnnotationType.STRUCTURAL_NOTE.value == "structural_note"
        assert AnnotationType.ELISION_NOTE.value == "elision_note"
        assert AnnotationType.FUTURE_REFERENCE.value == "future_reference"

    def test_all_certainties(self):
        assert AnnotationCertainty.HIGH.value == "high"
        assert AnnotationCertainty.MEDIUM.value == "medium"
        assert AnnotationCertainty.SPECULATIVE.value == "speculative"


class TestAnnotationDatabase:
    def test_empty_database(self):
        db = AnnotationDatabase(book_id="test")
        assert len(db.entries) == 0
        assert len(db.get_must_fulfill()) == 0

    def test_filter_by_chapter(self):
        db = AnnotationDatabase(book_id="test", entries=[
            AnnotationEntry(id="a", critic="批注者A", target_chapter=1,
                       target_text="", comment_text="", comment_type=AnnotationType.PLOT_HINT,
                       implied_outcome="a", certainty=AnnotationCertainty.HIGH,
                       related_characters=[], must_fulfill=False),
            AnnotationEntry(id="b", critic="批注者A", target_chapter=5,
                       target_text="", comment_text="", comment_type=AnnotationType.PLOT_HINT,
                       implied_outcome="b", certainty=AnnotationCertainty.HIGH,
                       related_characters=[], must_fulfill=True),
        ])
        ch1 = db.get_by_chapter(1)
        assert len(ch1) == 1
        assert ch1[0].id == "a"
        must = db.get_must_fulfill()
        assert len(must) == 1
        assert must[0].id == "b"

    def test_filter_by_character(self):
        db = AnnotationDatabase(book_id="test", entries=[
            AnnotationEntry(id="a", critic="批注者A", target_chapter=1,
                       target_text="", comment_text="", comment_type=AnnotationType.PLOT_HINT,
                       implied_outcome="", certainty=AnnotationCertainty.HIGH,
                       related_characters=["角色甲"], must_fulfill=False),
        ])
        chars = db.get_by_character("角色甲")
        assert len(chars) == 1

    def test_filter_by_type(self):
        db = AnnotationDatabase(book_id="test", entries=[
            AnnotationEntry(id="a", critic="批注者A", target_chapter=1,
                       target_text="", comment_text="", comment_type=AnnotationType.PLOT_HINT,
                       implied_outcome="", certainty=AnnotationCertainty.HIGH,
                       related_characters=[], must_fulfill=False),
            AnnotationEntry(id="b", critic="批注者A", target_chapter=2,
                       target_text="", comment_text="", comment_type=AnnotationType.CHARACTER_FATE,
                       implied_outcome="", certainty=AnnotationCertainty.MEDIUM,
                       related_characters=[], must_fulfill=False),
        ])
        plot_hints = db.get_by_type(AnnotationType.PLOT_HINT)
        assert len(plot_hints) == 1


class TestAnnotationPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        """Test save and load with a temporary path."""

        # Use a temporary directory for the annotation data
        from core.annotation_engine import ANNOTATION_DIR
        original_dir = ANNOTATION_DIR

        try:
            # Monkey-patch the directory
            import core.annotation_engine as ze
            ze.ZHIPI_DIR = tmp_path / "annotations"

            db = AnnotationDatabase(book_id="test_save", entries=[
                AnnotationEntry(id="z001", critic="批注者A", target_chapter=1,
                           target_text="假作真时真亦假", comment_text="此联妙极",
                           comment_type=AnnotationType.TECHNIQUE_COMMENT,
                           implied_outcome="真假呼应", certainty=AnnotationCertainty.HIGH,
                           related_characters=["角色甲", "角色乙"], must_fulfill=False),
            ])
            save_annotation_database("test_save", db)
            loaded = load_annotation_database("test_save")
            assert loaded is not None
            assert len(loaded.entries) == 1
            assert loaded.entries[0].id == "z001"
            assert loaded.entries[0].critic == "批注者A"
        finally:
            ze.ANNOTATION_DIR = original_dir


class TestBuildAnnotationConstraints:
    def test_no_data_returns_empty(self):
        """build_annotation_constraints with no file should return empty."""
        result = build_annotation_constraints("non_existent_book")
        assert result == ""

    def test_empty_db_returns_empty(self):
        """Empty database should return empty string."""
        from pathlib import Path

        import core.annotation_engine as ze
        from core.annotation_engine import AnnotationDatabase

        original_dir = ze.ANNOTATION_DIR
        try:
            import tempfile
            ze.ANNOTATION_DIR = Path(tempfile.mkdtemp())
            db = AnnotationDatabase(book_id="empty_test")
            ze.save_annotation_database("empty_test", db)
            result = ze.build_annotation_constraints("empty_test")
            assert result == ""
        finally:
            ze.ANNOTATION_DIR = original_dir


class TestContinuationContract:
    def test_basic_contract(self):
        contract = ContinuationContract(
            book_id="test_book",
            total_chapters=40,
            acts=[
                {"num": 1, "chapters": "81-90", "title": "主角之殇",
                 "core_conflict": "三角关系终局"},
            ],
            foreshadow_payoff_map={"f_001": [81, 82]},
            character_arcs={"女主角": ["81回病重", "82回诀别"]},
            key_chapters={81: "主角之殇"},
            plan_summary="后40章续写方案A",
        )
        d = contract.to_dict()
        assert d["total_chapters"] == 40
        assert "81" in d["key_chapters"]

    def test_act_constraint_bundle(self):
        bundle = ActConstraintBundle(
            act_number=1,
            chapters=[81, 82, 83, 84, 85],
            core_conflict="三角关系终局",
            foreshadow_allocation={81: ["f_001"]},
            rhythm_curve=["起", "承", "转", "转", "合"],
        )
        assert bundle.act_number == 1
        assert len(bundle.chapters) == 5


class TestValidation:
    def test_empty_content(self):
        result = validate_chapter_content("")
        assert result.passed() is False
        assert len(result.issues) > 0

    def test_basic_content(self):
        result = validate_chapter_content(
            "话说老爷回至家中，心下甚喜。原来这老爷为人端方正直，"
            "深慕圣人之道，生平最恨那些浮华不实之辈。却说公子"
            "自那日出门后，一路上心事重重，不觉来到花园门前。"
            "只见园门大开，里头寂静无人，心下便觉诧异。"
            "正在出神之际，忽听背后有人笑道：'公子在这里做什么？'"
        )
        assert result.logic_check_passed is True
        assert result.foreshadow_compliance is True

    def test_modern_marker_detection(self):
        """Modern Chinese markers should lower voice score."""
        result = validate_chapter_content(
            "然后宝玉说：'但是我觉得，因为所以，虽然可是。'"
            "的时侯，而且或者。"
        )
        assert result.voice_consistency_score < 0.8

    def test_foreshadow_compliance(self):
        result = validate_chapter_content(
            "黛玉之死，金玉良缘终成",
            foreshadow_requirements=["黛玉之死", "金玉良缘"],
        )
        assert result.foreshadow_compliance is True

        result = validate_chapter_content(
            "元春省亲",
            foreshadow_requirements=["探春远嫁"],
        )
        assert result.foreshadow_compliance is False
        assert any("远嫁" in i for i in result.issues)
