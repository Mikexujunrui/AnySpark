"""S48-P3 输入消化管线：文本提取/规则拆章/摘要卡/EPUB 导出测试。"""

from __future__ import annotations

import base64
import tempfile
import zipfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app
from anyspark.server.pipeline import chapterize, extract_text
from anyspark.server.workspace import Workspace


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


# ---------------------------------------------------------------------------
# 文本提取
# ---------------------------------------------------------------------------


def test_extract_txt_and_docx() -> None:
    ws = _ws()
    f = ws.save_upload("main", "note.txt", "第一章\n正文内容。".encode())
    assert "第一章" in extract_text(f)

    # docx（zipfile 拼装最小 document.xml）
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            "<w:document><w:p><w:t>第一章</w:t></w:p><w:p><w:t>正文。</w:t></w:p></w:document>",
        )
    d = ws.save_upload("main", "doc.docx", buf.getvalue())
    assert "第一章" in extract_text(d) and "正文。" in extract_text(d)


def test_extract_txt_gb18030_fallback() -> None:
    """S156：国内书籍 txt 常见 GBK/GB18030 编码——utf-8 硬读会丢中文，必须回退。"""
    ws = _ws()
    gb = "第一章 起点\n雨夜抵达雾城。\n\n第二章 灯塔\n钟声响起。".encode("gb18030")
    f = ws.save_upload("main", "书.txt", gb)
    text = extract_text(f)
    assert "第一章" in text and "起点" in text
    # 拆章应出 2 章而非乱码 1 章
    chs = chapterize(text, fallback_title="全文")
    assert len(chs) == 2 and chs[0]["title"] == "第一章 起点"


def test_extract_pdf_lightweight() -> None:
    """轻量 PDF：FlateDecode 文本流可提取；无流/扫描件返回提示。"""
    import zlib

    ws = _ws()
    # 构造最小 PDF（一个 FlateDecode 文本流：BT (Hello)Tj ET）
    stream = b"BT (Hello) Tj ET"
    comp = zlib.compress(stream)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(len(comp)).encode() + b" /Filter /FlateDecode >>\n"
        b"stream\n" + comp + b"\nendstream\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF"
    )
    f = ws.save_upload("main", "t.pdf", pdf)
    text = extract_text(f)
    assert "Hello" in text


# ---------------------------------------------------------------------------
# 规则拆章
# ---------------------------------------------------------------------------


def test_chapterize_chinese_and_english() -> None:
    text = "第一章 雨夜\n雨下了三天。\n\n第二章 灯塔\n雾城灯塔亮着。\n\n第三章\n结尾。"
    chs = chapterize(text)
    assert len(chs) == 3
    assert chs[0]["title"] == "第一章 雨夜"
    assert "雨下了三天" in chs[0]["content"]
    assert chs[1]["title"] == "第二章 灯塔"
    assert chs[2]["title"] == "第三章"

    en = "Chapter 1\nStart.\n\nCHAPTER 2\nThe end."
    chs2 = chapterize(en)
    assert len(chs2) == 2 and chs2[0]["title"] == "Chapter 1"


def test_chapterize_skips_empty_volume_title() -> None:
    """S156："第X卷"卷标题无正文时不应成章（空章跳过）。"""
    text = "第一卷 倒吊人\n\n第一章 起点\n正文一。\n\n第二章 奇异\n正文二。"
    chs = chapterize(text)
    assert len(chs) == 2
    assert chs[0]["title"] == "第一章 起点" and chs[1]["title"] == "第二章 奇异"


def test_chapterize_fallback_single() -> None:
    text = "没有章节标题的短文本。"
    chs = chapterize(text, fallback_title="全文")
    assert len(chs) == 1 and chs[0]["title"] == "全文"
    # 空文本
    assert chapterize("") == []


# ---------------------------------------------------------------------------
# 消化链路（API）
# ---------------------------------------------------------------------------


class _FakeModel:
    model_name = "fake"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="ok")


def test_ingest_chapters_and_card() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    ws = _ws()
    client = TestClient(build_app(model=_FakeModel(), db_path=db, workspace=ws))
    # 上传一本多章 txt
    novel = "第一章 雾城\n雨夜抵达。\n\n第二章 钟楼\n钟声响起。\n\n第三章 怀表\n发现怀表。"
    client.post(
        "/api/upload",
        json={"filename": "原稿.txt", "data_b64": base64.b64encode(novel.encode()).decode()},
    )
    r = client.post("/api/ingest", json={"filename": "原稿.txt"}).json()
    assert r["ok"] is True and r["kind"] == "chapters" and r["count"] == 3
    # 文件区：3 章 md
    files = ws.list_chapter_files("main")
    assert len(files) == 3 and files[0]["title"] == "第一章 雾城"
    # 库镜像
    from anyspark.store import ChapterStore

    assert len(ChapterStore(db).list_by_book("main")) == 3

    # 短文本 → 摘要卡
    client.post(
        "/api/upload",
        json={
            "filename": "设定.txt",
            "data_b64": base64.b64encode("雾城是江边之城。".encode()).decode(),
        },
    )
    r2 = client.post("/api/ingest", json={"filename": "设定.txt"}).json()
    assert r2["ok"] is True and r2["kind"] == "card"
    assert len(ws.list_cards("main")) == 1


def test_export_book_epub_with_image() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    ws = _ws()
    client = TestClient(build_app(model=_FakeModel(), db_path=db, workspace=ws))
    # 造一章 + 引用图片
    ws.write_chapter("main", 1, "第一章", "正文有图：![封面](../上传/封.png)")
    ws.save_upload("main", "封.png", b"\x89PNG-fake")
    from anyspark.store import ChapterStore

    ChapterStore(db).upsert("main", "第一章", "正文有图：![封面](../上传/封.png)", 1, "main")

    r = client.get("/api/export/book?format=epub")
    assert r.status_code == 200 and r.headers["content-type"] == "application/epub+zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "mimetype" in names and "OEBPS/content.opf" in names and "OEBPS/1.xhtml" in names
    # 图片被收集进 epub
    img_names = [n for n in names if n.startswith("OEBPS/images/")]
    assert len(img_names) == 1
    # 章节 xhtml 引用已改写为 images/ 路径
    xhtml = zf.read("OEBPS/1.xhtml").decode("utf-8")
    assert "images/" in xhtml and "封.png" in xhtml


import io  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
