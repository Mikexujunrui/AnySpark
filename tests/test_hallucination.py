"""Tests for the simplified hallucination detection.

Only two patterns are checked:
- fake_tool: "我调用了 write_chapter" (narrating a tool call in text)
- fake_write: "第3章已完成，共6000字" (claiming chapter written with specifics)

All keyword-based layers (past/future/investigation/sequential/fake_data/ack_trap)
were removed — they caused too many false positives on normal Chinese text.
"""

from core.hallucination import TOOL_NAME_PATTERNS, detect_hallucination

# ── fake_tool (Layer 1) ──────────────────────────────────────────────────────


class TestFakeToolNarration:
    def test_detects_called_write_chapter(self):
        result = detect_hallucination("我调用了 write_chapter 工具来写第1章。")
        assert result.detected
        assert result.layer == "fake_tool"

    def test_detects_using_delegate_writing(self):
        result = detect_hallucination("使用 delegate_writing 写入了第1章。")
        assert result.detected
        assert result.layer == "fake_tool"

    def test_detects_executed_edit_chapter(self):
        result = detect_hallucination("执行了 edit_chapter 来修改第3章。")
        assert result.detected
        assert result.layer == "fake_tool"

    def test_no_false_positive_tool_name_only(self):
        """Just mentioning a tool name without narration context should not trigger."""
        result = detect_hallucination("write_chapter 是用来写章节的工具。")
        if result.detected:
            assert result.layer != "fake_tool"

    def test_tool_name_patterns_present(self):
        assert "write_chapter" in TOOL_NAME_PATTERNS
        assert "delegate_writing" in TOOL_NAME_PATTERNS
        assert "edit_chapter" in TOOL_NAME_PATTERNS


# ── fake_write (Layer 2) ─────────────────────────────────────────────────────


class TestFakeWriteCompletion:
    def test_detects_chapter_with_word_count(self):
        """ "第3章已完成，共6000字" without tool_calls = fake_write."""
        text = "第3章已完成，共6000字，增加了对手戏。"
        result = detect_hallucination(text)
        assert result.detected
        assert result.layer == "fake_write"

    def test_detects_chapter_with_save_confirm(self):
        """ "第2章写入成功" without tool_calls = fake_write."""
        text = "第2章修改了内容，保存成功。"
        result = detect_hallucination(text)
        assert result.detected
        assert result.layer == "fake_write"

    def test_no_false_positive_chapter_ref_only(self):
        """Chapter reference without write verb + word count = not fake_write."""
        text = "第3章的标题是《初入江湖》。"
        result = detect_hallucination(text)
        assert not result.detected

    def test_no_false_positive_word_count_only(self):
        """Word count without chapter ref + write verb = not fake_write."""
        text = "这章约3000字，感觉很满意。"
        result = detect_hallucination(text)
        assert not result.detected

    def test_no_false_positive_write_verb_only(self):
        """Write verb without chapter ref + word count = not fake_write."""
        text = "我修改了一些内容，感觉好多了。"
        result = detect_hallucination(text)
        assert not result.detected


# ── Removed layers: verify they no longer fire ──────────────────────────────


class TestRemovedLayersDoNotFire:
    """All keyword-based layers were removed. These patterns used to trigger
    hallucination detection but should now pass through silently."""

    def test_past_tense_not_detected(self):
        """ "已完成"/"已删除" should NOT trigger — too common in normal text."""
        result = detect_hallucination("已完成的设定看起来不错。已删除的章节不需要恢复。")
        assert not result.detected

    def test_future_tense_not_detected(self):
        """ "我来写" should NOT trigger — normal conversation language."""
        result = detect_hallucination("我来帮你分析一下这个设计。我来写第三章。")
        assert not result.detected

    def test_investigation_not_detected(self):
        """ "让我检查" should NOT trigger — normal analysis language."""
        result = detect_hallucination("让我检查一下当前的章节状态。先看看分卷情况。")
        assert not result.detected

    def test_sequential_not_detected(self):
        """3+ completion keywords should NOT trigger — too common in Chinese."""
        text = "第一章完成了，接下来继续。成功的关键在于节奏。写入完成后确认。"
        result = detect_hallucination(text)
        assert not result.detected

    def test_ack_trap_not_detected(self):
        """Short "好的" should NOT trigger — not necessarily a trap."""
        result = detect_hallucination("好的")
        assert not result.detected

    def test_data_lists_not_detected(self):
        """Creative writing with data-like lists should NOT trigger."""
        text = "当前章节列表如下：\n1. 第一章 初入江湖\n2. 第二章 青云宗\n3. 第三章 叶家危机"
        result = detect_hallucination(text)
        assert not result.detected

    def test_word_count_claims_not_detected(self):
        """Word count claims without chapter ref + write verb = not detected."""
        text = "这章共6000字，约3000字是对话。总计9000字。"
        result = detect_hallucination(text)
        assert not result.detected


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_text(self):
        result = detect_hallucination("")
        assert not result.detected

    def test_normal_conversation(self):
        result = detect_hallucination("这个设计很好，角色弧光清晰。")
        assert not result.detected

    def test_long_creative_writing(self):
        """Long creative writing should not trigger any detection."""
        text = "尼尔站在墓地里，寒风吹过他的黑发。第1章完成了，接下来继续写第2章。" * 20
        result = detect_hallucination(text)
        # fake_write might trigger if chapter ref + write verb + word count
        # all appear — but this text doesn't have word counts, so it should pass
        if result.detected:
            assert result.layer == "fake_tool"  # only fake_tool could match

    def test_should_retry_property(self):
        result = detect_hallucination("我调用了 write_chapter 工具。")
        assert result.should_retry is True

    def test_no_detection_should_not_retry(self):
        result = detect_hallucination("这是一段普通的文字。")
        assert result.should_retry is False
