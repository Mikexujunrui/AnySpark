"""citation.py 纯函数单测（S250，D2 引用管理）。"""

from __future__ import annotations

from anyspark.library.citation import (
    bibtex_key,
    fmt_bibtex,
    fmt_gbt7714,
    format_note,
    minimal_meta,
)

_ZH_JOURNAL = {
    "entry_type": "article",
    "authors": ["张三", "李四", "王五", "赵六"],
    "title": "手机依赖对睡眠质量的影响",
    "venue": "心理学报",
    "year": "2024",
    "volume": "56",
    "number": "3",
    "pages": "301-312",
    "doi": "10.1000/demo",
}


def test_gbt7714_zh_journal() -> None:
    """中文期刊条目：>3 作者取前 3 加「等」；卷(期):页码齐全。"""
    s = fmt_gbt7714(_ZH_JOURNAL)
    assert s == (
        "张三, 李四, 王五, 等. 手机依赖对睡眠质量的影响[J]. 心理学报, 2024, 56(3): 301-312."
        " DOI: 10.1000/demo."
    )


def test_gbt7714_en_book_and_online() -> None:
    """英文专著（出版地缺省 V1）与在线条目（[EB/OL] + URL）。"""
    book = fmt_gbt7714(
        {
            "entry_type": "book",
            "authors": ["John Smith"],
            "title": "Deep Learning",
            "venue": "MIT Press",
            "year": "2016",
        }
    )
    assert book == "John Smith. Deep Learning[M]. MIT Press, 2016."
    online = fmt_gbt7714(
        {
            "entry_type": "online",
            "authors": ["A B"],
            "title": "Preprint",
            "year": "2024",
            "url": "https://arxiv.org/abs/2101.00001",
        }
    )
    assert online == "A B. Preprint[EB/OL]. (2024). https://arxiv.org/abs/2101.00001."


def test_bibtex_article() -> None:
    """BibTeX：author 用 and 连接；pages 转双连字符；键=姓氏+年+题名首词。"""
    s = fmt_bibtex(_ZH_JOURNAL)
    assert s.startswith("@article{张2024手机")
    assert "author = {张三 and 李四 and 王五 and 赵六}" in s
    assert "pages = {301--312}" in s
    assert "journal = {心理学报}" in s
    assert "doi = {10.1000/demo}" in s


def test_bibtex_escape_and_thesis_degree() -> None:
    """特殊字符转义（&_）；degree=phd → phdthesis。"""
    s = fmt_bibtex(
        {
            "entry_type": "thesis",
            "degree": "phd",
            "authors": ["Wang, X & Y"],
            "title": "A_study of 50% cases",
            "venue": "清华 MIT",
            "year": "2023",
        }
    )
    assert "@phdthesis{" in s
    assert "Wang, X \\& Y" in s
    assert "A\\_study of 50\\% cases" in s


def test_minimal_meta_honest_fallback() -> None:
    """无元数据书：兜底条目标注待补全，format_note 提示缺作者/年份。"""
    meta = minimal_meta("某书")
    assert meta["note"] == "引用元数据待补全"
    assert "authors" in format_note(meta)
    assert format_note(_ZH_JOURNAL) == ""


def test_bibtex_key_formats() -> None:
    """键生成：中文姓 /「Surname, Given」/「Given Surname」/空作者兜底。"""
    assert bibtex_key({"authors": ["张三"], "year": "2024", "title": "睡眠研究"}) == "张2024睡眠"
    assert bibtex_key({"authors": ["Smith, John"], "year": "2023", "title": "Sleep"}) == (
        "smith2023sleep"
    )
    assert bibtex_key({"authors": ["John Smith"], "year": "2022", "title": "AI"}) == "smith2022ai"
    assert bibtex_key({"authors": [], "title": ""}).startswith("anon")
