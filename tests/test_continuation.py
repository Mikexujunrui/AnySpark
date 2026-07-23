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
