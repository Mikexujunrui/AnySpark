"""
anyspark.server.workspace — 项目工作区（S48 工作区化：每项目一路径）。

设计（主人拍板，极简版 B）：
```
书架/<项目>/
├── 上传/          # 原始存档：任何格式，只读不碰（上传物原地，不复制不转换）
├── 章节/          # md 正文（权威）：001-第一章-雨夜.md（文件名承载序号，正文纯文字）
├── 卡片/          # 可读产物：角色卡-陈渡.md、场景卡-雾城.md
└── anyspark.db    # 状态库：图谱/伏笔/计划/章节元数据/版本历史（全局单库，book_id=项目名）
```
- 章节正文以 md 文件为**唯一权威**（agent 文件本能操作、人工可直接打开编辑、git 友好）
- SQLite chapters 表降级为**镜像**（供图谱抽取/检测/伏笔回收等既有管线零改动读取）
- 写入双写（文件权威 + 库镜像）；人工编辑 md 后可用 import_chapters 重新同步入库
- 卡片/上传是文件产物与存档，不参与状态查询
- 哲学保持：机制（目录结构/文件名规范/双写）硬编码；内容（正文/卡片）自然语言
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# 工作区根：data/workspace（与 sandbox 同级；.gitignore 已含 data/）
WORKSPACE_ROOT = Path(__file__).resolve().parents[5] / "data" / "workspace"

# 子目录名（固定结构，机制硬编码）
UPLOAD_DIR = "上传"
CHAPTERS_DIR = "章节"
CARDS_DIR = "卡片"


def _safe_title(title: str) -> str:
    """标题消毒：去掉 Windows/路径非法字符，防目录穿越。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]', "", title).strip()
    return cleaned or "未命名"


def chapter_filename(order: int, title: str) -> str:
    """章节文件名规范：{order:03d}-{title}.md（文件名承载序号与标题）。"""
    return f"{int(order):03d}-{_safe_title(title)}.md"


def parse_chapter_filename(filename: str) -> tuple[int, str] | None:
    """从文件名解析 (order, title)；不匹配返回 None。"""
    m = re.match(r"^(\d{3})-(.+)\.md$", filename)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


class Workspace:
    """项目工作区：目录结构 + 章节文件读写（单连接 SQLite 镜像存元数据）。"""

    def __init__(self, root: Path = WORKSPACE_ROOT) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- 目录解析 --
    def project_dir(self, book_id: str = "main") -> Path:
        d = self.root / _safe_title(book_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def upload_dir(self, book_id: str = "main") -> Path:
        d = self.project_dir(book_id) / UPLOAD_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def chapters_dir(self, book_id: str = "main") -> Path:
        d = self.project_dir(book_id) / CHAPTERS_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cards_dir(self, book_id: str = "main") -> Path:
        d = self.project_dir(book_id) / CARDS_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def manual_file(self, book_id: str = "main") -> Path:
        return self.project_dir(book_id) / "说明书.md"

    # -- 章节文件操作（权威存储） --
    def list_chapter_files(self, book_id: str = "main") -> list[dict[str, Any]]:
        """扫描章节目录，返回 [{order, title, filename, path}]（按 order 排序）。"""
        items: list[dict[str, Any]] = []
        for f in sorted(self.chapters_dir(book_id).glob("*.md")):
            parsed = parse_chapter_filename(f.name)
            if parsed is None:
                continue
            order, title = parsed
            items.append({"order": order, "title": title, "filename": f.name, "path": str(f)})
        return items

    def chapter_file(self, book_id: str, order: int, title: str) -> Path:
        return self.chapters_dir(book_id) / chapter_filename(order, title)

    def read_chapter(self, book_id: str, order: int, title: str) -> str | None:
        """读取章节正文（md 权威）；文件不存在返回 None。"""
        f = self.chapter_file(book_id, order, title)
        if not f.exists():
            return None
        try:
            return f.read_text(encoding="utf-8")
        except OSError:
            return None

    def write_chapter(self, book_id: str, order: int, title: str, content: str) -> Path:
        """写章节正文（覆盖；权威在文件）。"""
        f = self.chapter_file(book_id, order, title)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f

    def delete_chapter_file(self, book_id: str, order: int, title: str) -> bool:
        f = self.chapter_file(book_id, order, title)
        if f.exists():
            f.unlink()
            return True
        return False

    # -- 上传区 --
    def save_upload(self, book_id: str, filename: str, data: bytes) -> Path:
        """保存原始上传物到上传区（只读存档；文件名消毒防穿越）。"""
        safe = _safe_title(Path(filename).name)
        # 防覆盖重名：加时间戳后缀
        dest = self.upload_dir(book_id) / safe
        n = 1
        while dest.exists():
            stem, suffix = (dest.stem, dest.suffix) if dest.suffix else (safe, "")
            dest = self.upload_dir(book_id) / f"{stem}-{n}{suffix}"
            n += 1
        dest.write_bytes(data)
        return dest

    def list_uploads(self, book_id: str = "main") -> list[dict[str, Any]]:
        """列出上传区文件（含大小/修改时间），用于前端展示与 agent 考据。"""
        out = []
        for f in sorted(self.upload_dir(book_id).iterdir()):
            if f.is_file():
                out.append({"name": f.name, "size": f.stat().st_size, "path": str(f)})
        return out

    # -- 卡片区 --
    def write_card(self, book_id: str, kind: str, name: str, content: str) -> Path:
        """写卡片文件：{kind}-{name}.md（kind 如 角色卡/场景卡/摘要卡）。"""
        safe_kind = _safe_title(kind)
        safe_name = _safe_title(name)
        f = self.cards_dir(book_id) / f"{safe_kind}-{safe_name}.md"
        f.write_text(content, encoding="utf-8")
        return f

    def list_cards(self, book_id: str = "main") -> list[dict[str, Any]]:
        return [
            {"filename": f.name, "path": str(f)}
            for f in sorted(self.cards_dir(book_id).glob("*.md"))
        ]

    # -- 结构总览 --
    def describe(self, book_id: str = "main") -> dict[str, Any]:
        return {
            "project": book_id,
            "root": str(self.project_dir(book_id)),
            "uploads": self.list_uploads(book_id),
            "chapters": self.list_chapter_files(book_id),
            "cards": self.list_cards(book_id),
        }
