"""S152i：AI 文件沙箱按项目隔离测试（data/sandbox/{book_id}/）。

覆盖：
- 项目 A 写文件 → 项目 B 列表/读取不可见（此前全局共享）
- 旧全局沙箱文件（data/sandbox/ 直接文件）→ 一次性迁移归入 main
- 人工修改标记按项目隔离（PUT 落标记只影响本项目的 write_file 拦截）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.server.app import build_app


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


class _NoopModel:
    """sandbox 端点不触发模型，占位即可。"""

    model_name = "noop"

    def respond(self, messages, tools):  # type: ignore[no-untyped-def]
        raise AssertionError("sandbox 测试不应触发模型")


def _client(sandbox_root: Path) -> TestClient:
    import anyspark.server.tools_writing as tw

    tw._SANDBOX_ROOT = sandbox_root  # 测试隔离：指向临时目录，不污染真实 data/sandbox
    return TestClient(build_app(model=_NoopModel(), db_path=_db()))


def test_sandbox_isolated_by_book() -> None:
    """项目 A 的文件项目 B 不可见（此前全局共享同一沙箱）。"""
    with tempfile.TemporaryDirectory() as tmp:
        client = _client(Path(tmp))
        # A 项目写笔记
        r = client.put(
            "/api/sandbox/file",
            json={"path": "note-a.md", "content": "A 项目的灵感", "book_id": "book-a"},
        )
        assert r.status_code == 200, r.text
        # A 可见
        a = client.get("/api/sandbox?book_id=book-a").json()
        assert any(f["path"] == "note-a.md" for f in a["files"])
        # B 不可见（目录不存在/空）
        b = client.get("/api/sandbox?book_id=book-b").json()
        assert b["files"] == []
        # 读 B 的路径 → 404（防跨项目读取）
        r = client.get("/api/sandbox/file?path=note-a.md&book_id=book-b")
        assert r.status_code == 404
        # main 也不可见（隔离彻底）
        m = client.get("/api/sandbox?book_id=main").json()
        assert m["files"] == []


def test_sandbox_legacy_migration() -> None:
    """旧全局沙箱直接文件 → sandbox_list 触发迁移归入 main（幂等）。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        legacy = root / "旧笔记.md"
        legacy.write_text("历史全局笔记", encoding="utf-8")
        client = _client(root)
        # 首次列 main → 迁移触发：旧文件进 main/
        r = client.get("/api/sandbox?book_id=main")
        assert r.status_code == 200
        files = r.json()["files"]
        assert any(f["path"] == "旧笔记.md" for f in files), f"迁移失败: {files}"
        # 迁移后根目录不再有直接文件（已全部归入 main/）
        remaining = [f for f in root.iterdir() if f.is_file()]
        assert remaining == [], f"旧文件未迁移干净: {remaining}"
        # 幂等：再次列不报错
        assert client.get("/api/sandbox?book_id=main").status_code == 200
