# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for AI Flavor Scanner — 7 pure-rule detection checks."""

from core.ai_flavor_scanner import (
    AIFlavorReport,
    FlavorCheck,
    scan_chapter,
    scan_chapter_custom,
)

# ── Sample texts ──

_PAD = "测试文本用于填充字数以满足最低字符数要求。也是为了防止扫描器因文本过短而跳过检测。" * 3

# Heavily AI-flavored text (high density of hedge words, facial expressions, templates)
AI_HEAVY_TEXT = (
    "在这个充满危险的世界里，他缓缓站起身来。与此同时，一股莫名的恐惧涌上心头。"
    "他微微一怔，眼眸中闪过一丝惊异。她微微一笑，仿佛看穿了他的心思。"
    "他不知道为什么，但似乎有什么东西在隐隐作痛。他的嘴角微微上扬，目光落在她身上。"
    "就在这时，她的眼神变得柔和起来。他不由得感到一阵温暖，仿佛整个世界都亮了起来。"
    "他深吸一口气，缓缓走向她。她眼中闪烁着泪光，嘴角却挂着微笑。"
    "他伸出手，轻轻握住她的手。她微微一颤，却没有挣脱。"
    "那一刻，时间仿佛凝固了。他低声说道：'我一直在等你。'"
    "她抬起头，眼眸中满是惊喜。'真的吗？'她轻声问道。"
    "他点了点头，目光坚定。她微微一笑，泪水顺着脸颊滑落。"
)

# More human-like text (varied sentence lengths, diverse dialogue, less facial focus)
HUMAN_LIKE_TEXT = (
    "老张把烟头摁灭在搪瓷缸里，站起身来。椅子腿刮过水泥地面，发出刺耳的尖叫。"
    "他走到窗边，推开那扇生了锈的铁窗。外面在下雨。雨不大，但密，像谁在天上撒米。"
    "\n\n"
    "他回头看了一眼躺在床上的女人。她醒着，眼睛盯着天花板，一动不动。"
    "老张想说点什么，但喉咙里像堵了块棉花。他最终只是叹了口气，从口袋里摸出烟盒，又放了回去。"
    "\n\n"
    "'你走吧。'女人突然开口，声音很轻，但很稳。"
    "老张没动。他站在那里，像根生了根的柱子。"
    "\n\n"
    "'我说，你走吧。'她又说了一遍。这次声音更低，但更冷了。"
    "老张还是没动。过了很久，他才说：'雨停了我就走。'"
    "\n\n"
    "雨没有停。雨下了整整一夜。老张坐在窗边，一支接一支地抽烟。"
    "女人没有再说话。她翻了个身，面向墙壁。"
    "天快亮的时候，雨终于小了。老张站起来，拿起挂在门后的外套，头也不回地走了出去。"
    "门在他身后轻轻合上。女人没有抬头。她的肩膀微微颤抖了一下，但很快就平静了。"
)


class TestAIFlavorReport:
    """Test data structures."""

    def test_report_creation(self):
        r = AIFlavorReport(overall_score=85.0, is_clean=True)
        assert r.overall_score == 85.0
        assert r.is_clean is True
        assert r.checks == []

    def test_report_to_dict(self):
        check = FlavorCheck(
            name="测试", passed=True, score=90.0,
            threshold=3.0, actual_value=1.5,
        )
        r = AIFlavorReport(
            overall_score=90.0, is_clean=True,
            checks=[check], flagged_lines=["test line"],
        )
        d = r.to_dict()
        assert d["overall_score"] == 90.0
        assert d["is_clean"] is True
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "测试"

    def test_flavor_check_to_dict(self):
        c = FlavorCheck(
            name="AI过渡词密度", passed=False, score=30.0,
            threshold=3.0, actual_value=9.1,
            details=["AI过渡词密度 9.1/千字"],
        )
        d = c.to_dict()
        assert d["name"] == "AI过渡词密度"
        assert d["passed"] is False
        assert d["score"] == 30.0


class TestEmptyEdgeCases:
    """Test empty and short text edge cases."""

    def test_empty_content(self):
        r = scan_chapter("")
        assert r.is_clean is True
        assert r.overall_score == 100.0
        assert "跳过" in r.flagged_lines[0]

    def test_whitespace_only(self):
        r = scan_chapter("   \n\n  ")
        assert r.is_clean is True

    def test_very_short(self):
        r = scan_chapter("你好。")
        assert r.is_clean is True
        assert "跳过" in r.flagged_lines[0]


class TestAIHeavyDetection:
    """Test that AI-heavy text scores low."""

    def test_ai_heavy_low_score(self):
        r = scan_chapter(AI_HEAVY_TEXT)
        assert r.overall_score < 60.0, f"Expected low score, got {r.overall_score}"
        assert r.is_clean is False
        assert len(r.flagged_lines) > 0

    def test_ai_heavy_hedge_words(self):
        r = scan_chapter(AI_HEAVY_TEXT)
        hedge_check = next(c for c in r.checks if c.name == "AI模糊词密度")
        assert hedge_check.passed is False

    def test_ai_heavy_facial(self):
        r = scan_chapter(AI_HEAVY_TEXT)
        facial_check = next(c for c in r.checks if c.name == "面部微表情密度")
        assert facial_check.passed is False

    def test_ai_heavy_sentence_uniformity(self):
        r = scan_chapter(AI_HEAVY_TEXT)
        sentence_check = next(c for c in r.checks if c.name == "句长均匀度")
        assert sentence_check.passed is False


class TestHumanLikePasses:
    """Test that human-like text scores high."""

    def test_human_like_high_score(self):
        r = scan_chapter(HUMAN_LIKE_TEXT)
        assert r.overall_score > 60.0, f"Expected high score, got {r.overall_score}"

    def test_human_like_fewer_flags(self):
        r = scan_chapter(HUMAN_LIKE_TEXT)
        # Human-like text should have fewer flagged checks
        ai_failed = len([c for c in r.checks if not c.passed])
        # Compare: AI-heavy should have more failed checks
        r_ai = scan_chapter(AI_HEAVY_TEXT)
        ai_failed_count = len([c for c in r_ai.checks if not c.passed])
        assert ai_failed_count > ai_failed, \
            f"AI-heavy ({ai_failed_count} failed) should have more failures than human-like ({ai_failed})"


class TestCustomThresholds:
    """Test custom threshold configuration."""

    def test_all_checks_loose(self):
        r = scan_chapter_custom(
            AI_HEAVY_TEXT,
            thresholds={
                "transition_words": 100.0,
                "template_patterns": 100.0,
                "hedge_words": 100.0,
                "facial_micro": 100.0,
                "sentence_uniformity": 0.0,
            },
        )
        assert r.is_clean is True

    def test_selective_checks(self):
        r = scan_chapter_custom(
            AI_HEAVY_TEXT,
            enabled_checks=["transition_words", "hedge_words"],
        )
        assert len(r.checks) == 2
        assert r.checks[0].name == "AI过渡词密度"

    def test_unknown_check_ignored(self):
        r = scan_chapter_custom(
            AI_HEAVY_TEXT,
            enabled_checks=["nonexistent_check"],
        )
        assert len(r.checks) == 0


class TestParagraphOpenings:
    """Test paragraph opening homogeneity detection."""

    def test_no_consecutive(self):
        text = "第一段内容。\n第二段内容。\n第三段内容。\n" + _PAD
        r = scan_chapter(text)
        check = next(c for c in r.checks if c.name == "段落开头同构")
        assert check.passed is True

    def test_consecutive_same_subject(self):
        text = (
            "他又站起身。\n他又走到窗边。\n他又叹了口气。\n"
            "他又推开门。\n他又走了出去。\n他又回头看了一眼。\n"
        ) + _PAD
        r = scan_chapter(text)
        check = next(c for c in r.checks if c.name == "段落开头同构")
        assert check.passed is False


class TestDialogueTagMonotony:
    """Test dialogue tag diversity detection."""

    def test_no_dialogues(self):
        text = "这是一段没有对话的文本。" * 10
        r = scan_chapter(text)
        check = next(c for c in r.checks if c.name == "对话标签多样性")
        assert check.passed is True

    def test_diverse_tags(self):
        text = (
            "他说\u201c你好。\u201d她问道\u201c你是谁？\u201d"
            "他答道\u201c我是路人。\u201d她笑道\u201c真有趣。\u201d"
            "他喊道\u201c别走！\u201d她骂道\u201c滚开！\u201d"
            "他劝道\u201c冷静点。\u201d她叹道\u201c好吧。\u201d"
        ) + _PAD
        r = scan_chapter(text)
        check = next(c for c in r.checks if c.name == "对话标签多样性")
        # With diverse tags, should pass
        assert check.passed is True

    def test_monotonous_tags(self):
        text = (
            "他说道\u201c你好。\u201d她说道\u201c你好。\u201d"
            "他说道\u201c今天天气不错。\u201d她说道\u201c是的。\u201d"
            "他说道\u201c要不要出去走走。\u201d她说道\u201c好。\u201d"
            "他说道\u201c走吧。\u201d她说道\u201c嗯。\u201d"
        ) + _PAD
        r = scan_chapter(text)
        check = next(c for c in r.checks if c.name == "对话标签多样性")
        assert check.passed is False


class TestSentenceUniformity:
    """Test sentence length uniformity detection."""

    def test_varied_lengths(self):
        text = "短。这是一个中等长度的句子。这是一个非常非常非常非常非常长的句子，包含了很多文字内容很长很长很长很长。短。" + _PAD + "然后他又说了一些很长很长的话而且这些话语非常地冗长啰嗦简直让人无法忍受。"
        r = scan_chapter_custom(text, thresholds={"sentence_uniformity": 5.0})
        check = next(c for c in r.checks if c.name == "句长均匀度")
        # With relaxed threshold, should score higher than the AI-heavy text
        r_ai = scan_chapter(AI_HEAVY_TEXT)
        ai_check = next(c for c in r_ai.checks if c.name == "句长均匀度")
        assert check.score > ai_check.score
