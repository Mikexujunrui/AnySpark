"""anyspark.check.report + reviewers — 报告与检测解析测试。"""

from __future__ import annotations

from anyspark.check import Finding, ReviewReport, SkeletonCheckItem, generate_dynamic_checks
from anyspark.check.reviewers import _parse_findings
from anyspark.check.skeleton import SKELETON_CHECKS


def test_report_render() -> None:
    report = ReviewReport(target="第三章")
    report.findings.append(
        Finding(
            category="一致性",
            severity="hard",
            message="自称孤儿但有母亲",
            evidence="第3章",
            suggestion="修正",
        )
    )
    text = report.render()
    assert "第三章" in text
    assert "硬伤" in text
    assert "自称孤儿但有母亲" in text
    assert report.hard_count == 1


def test_report_empty() -> None:
    report = ReviewReport(target="第一章")
    assert "未发现" in report.render()


def test_skeleton_has_seven_categories() -> None:
    cats = [c.category for c in SKELETON_CHECKS]
    assert "一致性" in cats
    assert "主题连贯" in cats
    assert len(SKELETON_CHECKS) == 7


def test_parse_findings_fence() -> None:
    findings = _parse_findings(
        "```json\n"
        '[{"message": "矛盾", "evidence": "第3章", "suggestion": "改", '
        '"severity": "hard"}]\n```',
        "一致性",
    )
    assert len(findings) == 1
    assert findings[0].severity == "hard"
    assert findings[0].category == "一致性"
    assert findings[0].source == "dynamic"


def test_parse_findings_noise() -> None:
    findings = _parse_findings(
        '审读结果：\n[{"message": "节奏拖", "severity": "suggestion"}] 完毕',
        "结构节奏",
    )
    assert len(findings) == 1
    assert findings[0].severity == "suggestion"


def test_parse_findings_invalid() -> None:
    assert _parse_findings("什么都没有", "一致性") == []


# -- S145 长章分块覆盖（第三方评审 4.3） --
def test_split_chunks_short_text_single() -> None:
    from anyspark.check.reviewers import _split_chunks

    assert _split_chunks("短文本") == ["短文本"]


def test_split_chunks_empty() -> None:
    from anyspark.check.reviewers import _split_chunks

    assert _split_chunks("") == []


def test_split_chunks_long_text_overlaps() -> None:
    from anyspark.check.reviewers import CHUNK_OVERLAP, CHUNK_SIZE, _split_chunks

    text = "章" * (CHUNK_SIZE * 2 + 1000)  # 远超单块
    chunks = _split_chunks(text)
    assert len(chunks) >= 2, "长文本应切成多块"
    assert all(len(c) <= CHUNK_SIZE for c in chunks), "每块不超上限"
    # 相邻块重叠：前一块尾部与后一块头部共享 CHUNK_OVERLAP 字
    overlap = chunks[0][-CHUNK_OVERLAP:]
    assert chunks[1].startswith(overlap), "相邻块应重叠（上下文不丢）"
    # 覆盖完整：无遗漏（按步进滑动直到末尾）
    assert "".join(c for c in chunks)[: len(text)] != ""  # 非空
    assert chunks[-1].endswith("章"), "最后一块覆盖到文末"


def test_split_chunks_boundary_exact() -> None:
    from anyspark.check.reviewers import CHUNK_SIZE, _split_chunks

    assert len(_split_chunks("章" * CHUNK_SIZE)) == 1, "恰好等于上限仍单块"


class _FakeModel:
    """假模型：返回固定 JSON 数组。"""

    def __init__(self, response: str) -> None:
        self._response = response

    def respond(self, messages: object, tools: object) -> object:
        class _Out:
            text = self._response

        return _Out()


def test_generate_dynamic_checks_empty_context() -> None:
    """空上下文不生成检测项。"""
    model = _FakeModel("[]")
    result = generate_dynamic_checks(model, "")
    assert result == []


def test_generate_dynamic_checks_parses_json() -> None:
    """正常 JSON 解析为 SkeletonCheckItem 列表。"""
    model = _FakeModel(
        '[{"category": "一致性", "description": "检查主角伤疤位置是否前后一致"},'
        '{"category": "伏笔", "description": "检查老魔杖是否在第7章前出现"}]'
    )
    result = generate_dynamic_checks(model, "主角：哈利（角色）")
    assert len(result) == 2
    assert isinstance(result[0], SkeletonCheckItem)
    assert result[0].category == "一致性"
    assert "伤疤" in result[0].description


def test_generate_dynamic_checks_garbage_returns_empty() -> None:
    """模型返回垃圾文本时返回空列表。"""
    model = _FakeModel("这不是JSON")
    result = generate_dynamic_checks(model, "主角：哈利")
    assert result == []


def test_generate_dynamic_checks_missing_fields_skipped() -> None:
    """缺字段的条目跳过。"""
    model = _FakeModel(
        '[{"category": "一致性, "description": "测试"},'
        '{"category": "", "description": "空类别"},'
        '{"description": "缺类别"}]'
    )
    result = generate_dynamic_checks(model, "上下文")
    # 只有第一条有效（category 和 description 都有值）
    assert len(result) <= 1
