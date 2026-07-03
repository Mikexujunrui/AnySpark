from core.exporter import export_single_chapter_txt, export_txt


def test_export_txt(sample_chapters):
    data = export_txt("测试小说", sample_chapters)
    text = data.decode("utf-8")
    assert "《测试小说》" in text
    assert "第一章 初入江湖" in text
    assert "第二章 初次交手" in text
    assert "第三章 真相大白" in text
    assert "共 3 章" in text


def test_export_txt_empty():
    data = export_txt("空书", [])
    text = data.decode("utf-8")
    assert "《空书》" in text
    assert "共 0 章" in text


def test_export_txt_with_metadata(sample_chapters):
    data = export_txt("带元数据", sample_chapters, include_metadata=True)
    text = data.decode("utf-8")
    assert "[创建:" in text
    assert "[字数:" in text


def test_export_single_chapter():
    chapter = {"title": "单章标题", "content": "这是内容"}
    data = export_single_chapter_txt(chapter)
    text = data.decode("utf-8")
    assert "单章标题" in text
    assert "这是内容" in text
