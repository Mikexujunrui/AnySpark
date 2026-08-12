"""S103 书库 → skill 提炼端点测试（拆书模式：多维拆解成「书名」skill 草稿）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core import ModelOutput
from anyspark.server.app import build_app


class _FakeRefineModel:
    """fake model：返回拆书 skill JSON（mode=book 单候选）。"""

    def __init__(self) -> None:
        self.model_name = "fake-refine"

    def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='[{"name": "斗破苍穹写作法", '
            '"description": "爽文升级流的节奏与冲突组织方法论", '
            '"content": "升级流节奏：每卷先抑后扬，冲突逐级升级；对白推进信息", '
            '"example": "示例", "tags": "爽文,升级流", "target": "both"}]'
        )


def _client(tmp_path: Path) -> TestClient:
    return TestClient(build_app(db_path=tmp_path / "t.db", model=_FakeRefineModel()))


def test_library_refine_skill_full_chain(tmp_path: Path) -> None:
    """S103 全链路：建书 → 导入 → 提炼（草稿）→ 确认转正（生效）。"""
    client = _client(tmp_path)
    # 建书 + 导入两章
    r = client.post("/api/library", json={"name": "斗破苍穹"})
    book_id = r.json()["id"]
    r = client.post(
        "/api/library/import",
        json={
            "book_id": book_id,
            "content": "第一章 萧炎\n这里是正文。\n第二章 三年之约\n继续。",
            "title": "斗破苍穹",
        },
    )
    assert r.json()["chapters"] == 2

    # 提炼 → 草稿出现
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    draft = body["draft"]
    assert draft["name"] == "斗破苍穹写作法"
    assert draft["source"] == "library"

    # 草稿列表可见
    drafts = client.get("/api/skills/drafts").json()
    assert any(d["id"] == draft["id"] for d in drafts)

    # 重复提炼 → 409（同名草稿已存在）
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 409

    # 确认转正 → 进正式技能
    r = client.post(f"/api/skills/drafts/{draft['id']}/promote")
    assert r.status_code == 200
    skills = client.get("/api/skills").json()
    assert any(s["name"] == "斗破苍穹写作法" for s in skills)


def test_library_refine_empty_book_400(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.post("/api/library", json={"name": "空书"})
    book_id = r.json()["id"]
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 400


def test_library_refine_missing_book_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.post("/api/library/not-exist/refine-skill")
    assert r.status_code == 404


def test_skill_refine_tool_library_source_creates_draft(tmp_path: Path) -> None:
    """S103：skill_refine 工具支持 library_book_id（书库取原文）+ 候选存草稿。"""
    from anyspark.align import WritingSkillStore
    from anyspark.library import LibraryStore
    from anyspark.server.tools_domain import make_skill_refine_implementer

    class _Gen:
        def generate(self, source_text, hint, max_items, mode):  # type: ignore[no-untyped-def]
            assert mode in ("writing", "main")
            return []

        def generate_book(self, source_text, hint=""):  # type: ignore[no-untyped-def]
            # S106：拆书走新接口（分块抽样+归并）；原文来自书库全文
            assert "第一章" in source_text
            return [
                {
                    "name": "斗破苍穹写作法",
                    "description": "爽文节奏方法论",
                    "content": "冲突逐级升级；对白推进信息",
                    "example": "",
                    "tags": "",
                    "target": "both",
                }
            ]

    lib = LibraryStore(tmp_path / "lib.db", library_root=tmp_path / "libroot")
    book = lib.add_book("斗破苍穹")
    lib.import_chapter(book["id"], "第一章", "第一章 萧炎 正文", 0)
    skills = WritingSkillStore(tmp_path / "sk.db")

    spec, impl = make_skill_refine_implementer(_Gen(), None, library=lib, skills=skills)
    res = impl(spec, {"library_book_id": book["id"], "mode": "book"})
    assert res.ok is True
    assert "草稿已生成" in res.content

    drafts = skills.list_drafts()
    assert len(drafts) == 1
    assert drafts[0]["name"] == "斗破苍穹写作法"
    assert drafts[0]["source"] == "agent"

    # 再次提炼 → 同名草稿去重（不重复堆叠）
    res2 = impl(spec, {"library_book_id": book["id"], "mode": "book"})
    assert res2.ok is True
    assert "同名草稿" in res2.content
    assert len(skills.list_drafts()) == 1


def test_skill_refine_tool_missing_library_book(tmp_path: Path) -> None:
    from anyspark.library import LibraryStore
    from anyspark.server.tools_domain import make_skill_refine_implementer

    class _Gen:
        def generate(self, source_text, hint, max_items, mode):  # type: ignore[no-untyped-def]
            raise AssertionError("不应调用")

    lib = LibraryStore(tmp_path / "lib2.db", library_root=tmp_path / "lib2root")
    spec, impl = make_skill_refine_implementer(_Gen(), None, library=lib, skills=None)
    res = impl(spec, {"library_book_id": "not-exist", "mode": "book"})
    assert res.ok is False
    assert "书库无此书" in res.content
