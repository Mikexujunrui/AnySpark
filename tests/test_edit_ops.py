"""Tests for apply_edit_ops, _split_paragraphs, _fuzzy_find in executor.py."""

from tools.executor import _fuzzy_find, _split_paragraphs, apply_edit_ops


class TestSplitParagraphs:
    def test_basic_split(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        segs = _split_paragraphs(text)
        assert len(segs) == 3
        assert segs[0] == "第一段。"
        assert segs[1] == "第二段。"
        assert segs[2] == "第三段。"

    def test_empty_text(self):
        assert _split_paragraphs("") == []
        assert _split_paragraphs("   ") == []

    def test_single_paragraph(self):
        segs = _split_paragraphs("只有一段文字。")
        assert len(segs) == 1
        assert segs[0] == "只有一段文字。"

    def test_whitespace_between_paragraphs(self):
        text = "第一段。\n  \n第二段。"
        segs = _split_paragraphs(text)
        assert len(segs) == 2


class TestFuzzyFind:
    def test_exact_match(self):
        text = "李明愤怒地摔碎了杯子，碎片散落一地。"
        result = _fuzzy_find(text, "愤怒地摔碎了杯子")
        assert result is not None
        assert "摔碎" in result

    def test_close_match(self):
        text = "李明愤怒地摔碎了杯子，碎片散落一地。"
        result = _fuzzy_find(text, "愤怒地打碎了杯子")  # 打碎 vs 摔碎
        assert result is not None

    def test_no_match(self):
        text = "今天天气真好。"
        result = _fuzzy_find(text, "完全无关的内容在这里", threshold=0.8)
        assert result is None

    def test_short_target(self):
        result = _fuzzy_find("一些文本", "短")
        assert result is None  # Too short (< 4 chars)

    def test_empty_inputs(self):
        assert _fuzzy_find("", "test") is None
        assert _fuzzy_find("test", "") is None


class TestApplyEditOps:
    def test_replace_with_confirm(self):
        text = "李明愤怒地摔碎了杯子。\n\n他转身离去。"
        ops = [
            {"op": "replace", "segment": 0, "confirm": "愤怒地摔碎了杯子", "to": "沉默地放下了杯子"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "沉默地放下了杯子" in result
        assert "愤怒" not in result
        assert "他转身离去" in result
        assert report[0]["status"] == "ok"

    def test_replace_fuzzy_fallback(self):
        text = "李明愤怒地摔碎了杯子。\n\n他转身离去。"
        ops = [
            {"op": "replace", "segment": 0, "confirm": "愤怒地打碎了杯子", "to": "沉默地放下了杯子"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "沉默地放下了杯子" in result
        assert report[0]["status"] == "ok"
        assert report[0].get("fuzzy") is True

    def test_replace_failed_no_match(self):
        text = "今天天气真好。"
        ops = [
            {"op": "replace", "segment": 0, "confirm": "完全不存在的文本片段", "to": "新文本"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert report[0]["status"] == "failed"
        assert result == text  # Unchanged

    def test_replace_whole_segment(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        ops = [
            {"op": "replace", "segment": 1, "to": "全新的内容。"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "全新的内容。" in result
        assert "第二段。" not in result
        assert report[0]["status"] == "ok"

    def test_delete_with_confirm(self):
        text = "保留这句话。\n\n删除这句话。"
        ops = [
            {"op": "delete", "segment": 1, "confirm": "删除这句话。"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "保留这句话" in result
        assert "删除这句话" not in result
        assert report[0]["status"] == "ok"

    def test_delete_whole_segment(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        ops = [
            {"op": "delete", "segment": 1}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "第一段" in result
        assert "第二段" not in result
        assert "第三段" in result
        assert report[0]["status"] == "ok"

    def test_insert_after(self):
        text = "第一段。\n\n第二段。"
        ops = [
            {"op": "insert_after", "segment": 0, "text": "插入的新段落。"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "第一段" in result
        assert "插入的新段落" in result
        assert "第二段" in result
        assert report[0]["status"] == "ok"

    def test_insert_before(self):
        text = "第一段。\n\n第二段。"
        ops = [
            {"op": "insert_before", "segment": 1, "text": "插入在第二段之前。"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert "第一段" in result
        assert "插入在第二段之前" in result
        assert "第二段" in result
        assert report[0]["status"] == "ok"

    def test_multiple_ops(self):
        text = "李明走进房间。\n\n他看到了桌子上的信。\n\n他拿起信读了起来。"
        ops = [
            {"op": "replace", "segment": 0, "confirm": "走进房间", "to": "冲进房间"},
            {"op": "insert_after", "segment": 1, "text": "信封上写着他的名字。"},
            {"op": "replace", "segment": 2, "confirm": "读了起来", "to": "仔细看了起来"},
        ]
        result, report = apply_edit_ops(text, ops)
        assert "冲进房间" in result
        assert "信封上写着他的名字" in result
        assert "仔细看了起来" in result
        assert report[0]["status"] == "ok"
        assert report[1]["status"] == "ok"
        assert report[2]["status"] == "ok"

    def test_invalid_segment_index(self):
        text = "只有一段。"
        ops = [
            {"op": "replace", "segment": 5, "confirm": "x", "to": "y"}
        ]
        result, report = apply_edit_ops(text, ops)
        assert report[0]["status"] == "failed"
        assert "超出范围" in report[0]["reason"]

    def test_unknown_op(self):
        text = "一段文字。"
        ops = [
            {"op": "unknown_op", "segment": 0}
        ]
        result, report = apply_edit_ops(text, ops)
        assert report[0]["status"] == "failed"

    def test_empty_text(self):
        result, report = apply_edit_ops("", [{"op": "replace", "segment": 0, "to": "x"}])
        assert result == ""
        assert report[0]["status"] == "skipped"

    def test_empty_ops(self):
        text = "原文不变。"
        result, report = apply_edit_ops(text, [])
        assert result == "原文不变。"
        assert report == []

    def test_preserves_unmodified_segments(self):
        """Core test: unmodified segments must be byte-identical."""
        seg0 = "这是第一段完全不变的原文。"
        seg1 = "李明愤怒地摔碎了杯子。"
        seg2 = "这是第三段也完全不变的原文。"
        text = f"{seg0}\n\n{seg1}\n\n{seg2}"
        ops = [
            {"op": "replace", "segment": 1, "confirm": "愤怒地摔碎了杯子", "to": "沉默地放下了杯子"}
        ]
        result, report = apply_edit_ops(text, ops)
        lines = [p.strip() for p in result.split("\n") if p.strip()]
        assert lines[0] == seg0  # Byte-identical
        assert lines[2] == seg2  # Byte-identical
        assert "沉默地放下了杯子" in lines[1]
        assert "愤怒" not in result
