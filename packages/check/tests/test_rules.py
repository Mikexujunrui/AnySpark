"""anyspark.check.rules — 轻量规则编译器测试。"""

from anyspark.check import check_text, compile_rule


def test_compile_forbidden_word() -> None:
    rule = compile_rule("不要破折号")
    assert rule is not None
    assert "破折号" in rule.description
    hits = rule.checker("他——不，她走了。")
    assert hits  # 命中破折号


def test_compile_term_preference() -> None:
    rule = compile_rule("称呼要用「她」，不要用「那个女孩」")
    assert rule is not None
    hits = rule.checker("那个女孩推开门")
    assert len(hits) == 1
    assert hits[0] == "那个女孩"


def test_compile_max_sentences() -> None:
    rule = compile_rule("每段不超过三句话")
    assert rule is not None
    hits = rule.checker("第一句。第二句。第三句。第四句。\n短段。")
    assert len(hits) == 1  # 第一段超了，第二段没超


def test_compile_unknown_rule_returns_none() -> None:
    assert compile_rule("今天天气真好") is None


def test_check_text_multiple_rules() -> None:
    r1 = compile_rule("不要破折号")
    r2 = compile_rule("称呼要用「她」，不要用「那个女孩」")
    rules = [r for r in [r1, r2] if r]
    text = "那个女孩——她笑了。"
    results = check_text(rules, text)
    assert len(results) == 2  # 两条规则都命中
    total_hits = sum(len(h) for _, h in results)
    assert total_hits == 2
