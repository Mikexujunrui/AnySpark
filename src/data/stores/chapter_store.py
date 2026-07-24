# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Chapter CRUD with git-like versioning."""

import logging
import re
from datetime import datetime
from pathlib import Path

from core.book_locks import book_lock
from core.config import DATA_DIR, config
from core.errors import NotFoundError, StorageError
from core.event_bus import Event, EventType, bus
from core.search import fts as fts_engine
from data.stores._base import _fuzzy_find, _locate_in_paragraph, _split_paragraphs

logger = logging.getLogger(__name__)


class ChapterStoreMixin:
    """Mixin providing chapter + version management.  Requires BaseStore."""

    def load_chapters(self, book_id: str) -> list[dict]:
        raw = self._read_json(self._chapters_file(book_id))
        return [self._migrate_chapter(ch) for ch in raw]

    def save_chapters(self, book_id: str, chapters: list[dict]):
        self._write_json(self._chapters_file(book_id), chapters)

    def _migrate_chapter(self, ch: dict) -> dict:
        if "versions" in ch:
            return ch
        content = ch.pop("content", "")
        vid = f"v_{ch['id']}_0"
        ch["versions"] = [
            {
                "id": vid,
                "content": content,
                "title": ch.get("title", ""),
                "message": "初始版本",
                "timestamp": ch.get("createdAt", datetime.now().isoformat()),
                "parent": None,
                "word_count": len(content.replace("\n", "").replace(" ", "")),
            }
        ]
        ch["current_version"] = vid
        return ch

    def _make_version_id(self) -> str:
        return f"v_{int(datetime.now().timestamp() * 1000)}"

    def _next_version_label(self, ch: dict, patch: bool = False) -> str:
        """计算语义化版本号。

        patch=True  -> 在当前主版本上递增小版本 (v1 -> v1.1, v1.2 -> v1.3)
        patch=False -> 递增主版本 (v1.2 -> v2, v3.1 -> v4)
        首次创建 -> v1
        """
        versions = ch.get("versions", [])
        if not versions:
            return "v1"
        last = versions[-1]
        label = last.get("version_label", "")
        # 解析已有 label
        if label and label.startswith("v"):
            parts = label[1:].split(".")
            major = int(parts[0]) if parts[0].isdigit() else len(versions)
            minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        else:
            major = len(versions)
            minor = 0
        if patch:
            return f"v{major}.{minor + 1}"
        else:
            return f"v{major + 1}"

    def add_chapter(
        self, book_id: str, title: str, content: str, is_extra: bool = False, status: str = "draft"
    ) -> dict:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch_id = str(int(datetime.now().timestamp() * 1000))
            vid = self._make_version_id()
            trimmed = content[: config.storage.max_chapter_chars]
            chapter = {
                "id": ch_id,
                "title": title,
                "current_version": vid,
                "is_extra": is_extra,
                "status": status,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
                "versions": [
                    {
                        "id": vid,
                        "content": trimmed,
                        "title": title,
                        "message": "初始版本",
                        "timestamp": datetime.now().isoformat(),
                        "parent": None,
                        "word_count": len(trimmed.replace("\n", "").replace(" ", "")),
                        "version_label": "v1",
                    }
                ],
            }
            chapters.append(chapter)
            self.save_chapters(book_id, chapters)
            non_extra_count = sum(1 for c in chapters if not c.get("is_extra"))
            self.update_book_stats(book_id, chapter_count=non_extra_count)
        bus.emit_sync(
            Event(
                type=EventType.CHAPTER_CREATED,
                data={"book_id": book_id, "chapter_id": ch_id, "title": title, "is_extra": is_extra},
            )
        )
        try:
            fts_engine.index_chapter(book_id, {"id": chapter["id"], "title": title, "content": trimmed})
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS index_chapter failed for new chapter: {e}")
        self._invalidate_character_mentions(book_id)
        return self._chapter_view(chapter)

    def batch_add_chapters(self, book_id: str, chapters_data: list[dict]):
        """导入多个章节：一次加载、一次保存、一次索引。

        chapters_data: [{"title": str, "content": str}, ...]
        """
        if not chapters_data:
            return
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            new_chapters = []
            for cd in chapters_data:
                ch_id = str(int(datetime.now().timestamp() * 1000))
                vid = self._make_version_id()
                trimmed = cd["content"][: config.storage.max_chapter_chars]
                chapter = {
                    "id": ch_id,
                    "title": cd["title"],
                    "current_version": vid,
                    "is_extra": False,
                    "status": "draft",
                    "createdAt": datetime.now().isoformat(),
                    "updatedAt": datetime.now().isoformat(),
                    "versions": [
                        {
                            "id": vid,
                            "content": trimmed,
                            "title": cd["title"],
                            "message": "初始版本",
                            "timestamp": datetime.now().isoformat(),
                            "parent": None,
                            "word_count": len(trimmed.replace("\n", "").replace(" ", "")),
                            "version_label": "v1",
                        }
                    ],
                }
                chapters.append(chapter)
                new_chapters.append(chapter)
            self.save_chapters(book_id, chapters)
            non_extra_count = sum(1 for c in chapters if not c.get("is_extra"))
            self.update_book_stats(book_id, chapter_count=non_extra_count)
        # Rebuild FTS once for all chapters
        try:
            fts_engine.rebuild_chapters(book_id, chapters)
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS rebuild failed after batch import: {e}")
        self._invalidate_character_mentions(book_id)

    def _find_chapter(self, chapters: list[dict], chapter_id: str) -> dict | None:
        cid = chapter_id.strip()
        # 番外索引: #E1, #E2, ... 或 番外1, 番外2, ...
        extra_idx = self._parse_extra_index(cid)
        if extra_idx is not None:
            extras = [c for c in chapters if c.get("is_extra")]
            if 0 <= extra_idx < len(extras):
                return extras[extra_idx]
            return None
        # 普通章节索引: #1, #2, ... 只计非番外章节
        idx = self._parse_chapter_index(cid)
        if idx is not None:
            regular = [c for c in chapters if not c.get("is_extra")]
            if 0 <= idx < len(regular):
                return regular[idx]
            return None

        exact = next((c for c in chapters if c["id"] == cid), None)
        if exact:
            return exact
        matches = [c for c in chapters if c["id"].startswith(cid)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 and len(cid) >= 12:
            return matches[0]
        return None

    def _parse_chapter_index(self, cid: str) -> int | None:
        s = cid.strip()
        if s.startswith("#"):
            num = s[1:].strip()
            if num.isdigit():
                return int(num) - 1
        return None

    def _parse_extra_index(self, cid: str) -> int | None:
        """Parse #E1, #E2, ... or 番外1, 番外2, ... to 0-based index."""
        s = cid.strip()
        if s.startswith("#") and len(s) > 1:
            rest = s[1:]
            if rest.upper().startswith("E") and rest[1:].isdigit():
                return int(rest[1:]) - 1
        if s.startswith("番外") and s[2:].isdigit():
            return int(s[2:]) - 1
        return None

    def get_chapter(self, book_id: str, chapter_id: str) -> dict:
        chapters = self.load_chapters(book_id)
        ch = self._find_chapter(chapters, chapter_id)
        if not ch:
            raise NotFoundError(f"章节不存在: {chapter_id}")
        return self._chapter_view(ch)

    def _chapter_view(self, ch: dict) -> dict:
        cur = self._get_current_version(ch)
        content = cur.get("content", "")
        # honor explicit word_count on version, otherwise compute from content
        word_count = cur.get("word_count", 0)
        if not word_count and content:
            # strip whitespace & newlines for CJK-friendly char count
            word_count = len(content.replace("\n", "").replace(" ", ""))
        return {
            "id": ch["id"],
            "title": cur.get("title", ch.get("title", "")),
            "content": content,
            "createdAt": ch.get("createdAt", ""),
            "updatedAt": ch.get("updatedAt", ""),
            "current_version": ch.get("current_version", ""),
            "version_count": len(ch.get("versions", [])),
            "version_label": cur.get("version_label", f"v{len(ch.get('versions', []))}"),
            "word_count": word_count,
            "is_extra": ch.get("is_extra", False),
            "status": ch.get("status", "draft"),
        }

    def _get_current_version(self, ch: dict) -> dict:
        cur_id = ch.get("current_version", "")
        for v in ch.get("versions", []):
            if v["id"] == cur_id:
                return v
        if ch.get("versions"):
            return ch["versions"][-1]
        # Fallback: if no versions, use top-level content/title directly
        top_content = ch.get("content", "")
        if top_content:
            return {"content": top_content, "title": ch.get("title", "")}
        return {"content": "", "title": ch.get("title", "")}

    def edit_chapter(
        self, book_id: str, chapter_id: str, content: str, title: str = None, message: str = "编辑"
    ) -> dict:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            vid = self._make_version_id()
            parent = ch.get("current_version")
            cur_title = title or self._get_current_version(ch).get("title", ch.get("title", ""))
            trimmed = content[: config.storage.max_chapter_chars]
            version_label = self._next_version_label(ch, patch=False)
            new_version = {
                "id": vid,
                "content": trimmed,
                "title": cur_title,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "parent": parent,
                "word_count": len(trimmed.replace("\n", "").replace(" ", "")),
                "version_label": version_label,
            }
            ch["versions"].append(new_version)
            ch["current_version"] = vid
            ch["updatedAt"] = datetime.now().isoformat()
            if title:
                ch["title"] = title
            self.save_chapters(book_id, chapters)
        bus.emit_sync(
            Event(
                type=EventType.CHAPTER_UPDATED,
                data={"book_id": book_id, "chapter_id": ch["id"], "version": vid, "message": message},
            )
        )
        try:
            fts_engine.index_chapter(book_id, {"id": ch["id"], "title": cur_title, "content": trimmed})
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS index_chapter failed on update: {e}")
        self._invalidate_character_mentions(book_id)
        return self._chapter_view(ch)

    def patch_chapter(self, book_id: str, chapter_id: str, patches: list[dict], message: str = "局部编辑") -> dict:
        """局部编辑章节。

        patches 是一个操作列表，每个操作为：
          {"op": "replace", "find": "原文片段", "replace": "替换为"}
          {"op": "insert_after", "find": "锚点文本", "text": "插入的文本"}
          {"op": "insert_before", "find": "锚点文本", "text": "插入的文本"}
          {"op": "delete", "find": "要删除的文本"}
          {"op": "append", "text": "追加到章节末尾"}
          {"op": "prepend", "text": "插入到章节开头"}

        返回新版本视图，包含 patched_count（成功应用的操作数）和 failed_ops（失败操作详情）。
        """
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")

            cur_ver = self._get_current_version(ch)
            content = cur_ver.get("content", "")
            cur_title = cur_ver.get("title", ch.get("title", ""))
            original_content = content  # 保存原文，用于补丁版本对比

            patched_count = 0
            failed_ops = []
            patches_summary = []  # 成功操作的可读摘要
            paragraphs = _split_paragraphs(content)  # 段落预拆分，每次变更后重建

            def _resolve(patch_data):
                """Resolve target location: segment_id+confirm first, then find."""
                seg_id = patch_data.get("segment_id")
                confirm = patch_data.get("confirm", "")
                find = patch_data.get("find", "")

                # Strategy 1: segment_id + confirm (paragraph-level anchoring)
                if seg_id is not None:
                    try:
                        seg_id = int(seg_id)
                    except (ValueError, TypeError):
                        seg_id = None
                if seg_id is not None:
                    result = _locate_in_paragraph(paragraphs, seg_id, confirm or find)
                    if result:
                        return result
                    # segment_id provided but failed → try confirm in full content as fallback
                    if confirm:
                        result = _fuzzy_find(content, confirm)
                        if result:
                            return result
                    # Last fallback: try find in full content
                    if find:
                        result = _fuzzy_find(content, find)
                        if result:
                            return result
                    return None

                # Strategy 2: find only (legacy)
                if find:
                    return _fuzzy_find(content, find)
                return None

            for i, patch in enumerate(patches):
                op = patch.get("op", "replace")
                try:
                    if op == "replace":
                        find = patch.get("find", "")
                        confirm = patch.get("confirm", "")
                        repl = patch.get("replace", "")
                        seg_id = patch.get("segment_id")
                        if not find and not confirm and seg_id is None:
                            logger.warning("patch_chapter[%d] replace 缺少锚点 | chapter=%s", i, chapter_id)
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 find/confirm/segment_id"})
                            continue
                        result = _resolve(patch)
                        if result is None:
                            anchor = confirm or find
                            logger.warning(
                                "patch_chapter[%d] replace 未找到原文 | chapter=%s | anchor=%s | seg_id=%s",
                                i,
                                chapter_id,
                                anchor[:50],
                                seg_id,
                            )
                            failed_ops.append({"idx": i, "op": op, "reason": f"未找到原文: {anchor[:30].strip()}…"})
                            continue
                        pos, matched = result
                        content = content[:pos] + repl + content[pos + len(matched) :]
                        paragraphs = _split_paragraphs(content)  # 漂移修正
                        patches_summary.append({"op": op, "before": matched, "after": repl})
                        patched_count += 1

                    elif op == "insert_after":
                        find = patch.get("find", "")
                        confirm = patch.get("confirm", "")
                        text = patch.get("text", "")
                        seg_id = patch.get("segment_id")
                        if not find and not confirm and seg_id is None:
                            logger.warning("patch_chapter[%d] insert_after 缺少锚点 | chapter=%s", i, chapter_id)
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 find/confirm/segment_id"})
                            continue
                        result = _resolve(patch)
                        if result is None:
                            anchor = confirm or find
                            logger.warning(
                                "patch_chapter[%d] insert_after 未找到锚点 | chapter=%s | anchor=%s | seg_id=%s",
                                i,
                                chapter_id,
                                anchor[:50],
                                seg_id,
                            )
                            failed_ops.append({"idx": i, "op": op, "reason": f"未找到锚点: {anchor[:30].strip()}…"})
                            continue
                        pos, matched = result
                        idx = pos + len(matched)
                        content = content[:idx] + text + content[idx:]
                        paragraphs = _split_paragraphs(content)  # 漂移修正
                        patches_summary.append({"op": op, "anchor": matched, "inserted": text})
                        patched_count += 1

                    elif op == "insert_before":
                        find = patch.get("find", "")
                        confirm = patch.get("confirm", "")
                        text = patch.get("text", "")
                        seg_id = patch.get("segment_id")
                        if not find and not confirm and seg_id is None:
                            logger.warning("patch_chapter[%d] insert_before 缺少锚点 | chapter=%s", i, chapter_id)
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 find/confirm/segment_id"})
                            continue
                        result = _resolve(patch)
                        if result is None:
                            anchor = confirm or find
                            logger.warning(
                                "patch_chapter[%d] insert_before 未找到锚点 | chapter=%s | anchor=%s | seg_id=%s",
                                i,
                                chapter_id,
                                anchor[:50],
                                seg_id,
                            )
                            failed_ops.append({"idx": i, "op": op, "reason": f"未找到锚点: {anchor[:30].strip()}…"})
                            continue
                        pos, matched = result
                        content = content[:pos] + text + content[pos:]
                        paragraphs = _split_paragraphs(content)  # 漂移修正
                        patches_summary.append({"op": op, "anchor": matched, "inserted": text})
                        patched_count += 1

                    elif op == "delete":
                        find = patch.get("find", "")
                        confirm = patch.get("confirm", "")
                        seg_id = patch.get("segment_id")
                        if not find and not confirm and seg_id is None:
                            logger.warning("patch_chapter[%d] delete 缺少锚点 | chapter=%s", i, chapter_id)
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 find/confirm/segment_id"})
                            continue
                        result = _resolve(patch)
                        if result is None:
                            anchor = confirm or find
                            logger.warning(
                                "patch_chapter[%d] delete 未找到文本 | chapter=%s | anchor=%s | seg_id=%s",
                                i,
                                chapter_id,
                                anchor[:50],
                                seg_id,
                            )
                            failed_ops.append(
                                {"idx": i, "op": op, "reason": f"未找到要删除的文本: {anchor[:30].strip()}…"}
                            )
                            continue
                        pos, matched = result
                        content = content[:pos] + content[pos + len(matched) :]
                        paragraphs = _split_paragraphs(content)  # 漂移修正
                        patches_summary.append({"op": op, "deleted": matched})
                        patched_count += 1

                    elif op == "append":
                        text = patch.get("text", "")
                        if not text:
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 text 字段"})
                            continue
                        content = content + text
                        paragraphs = _split_paragraphs(content)
                        patches_summary.append({"op": op, "appended": text})
                        patched_count += 1

                    elif op == "prepend":
                        text = patch.get("text", "")
                        if not text:
                            failed_ops.append({"idx": i, "op": op, "reason": "缺少 text 字段"})
                            continue
                        content = text + content
                        paragraphs = _split_paragraphs(content)
                        patches_summary.append({"op": op, "prepended": text})
                        patched_count += 1

                    else:
                        failed_ops.append({"idx": i, "op": op, "reason": f"未知操作类型: {op}"})

                except Exception as e:
                    logger.warning("patch_chapter[%d] %s 异常 | chapter=%s | error=%s", i, op, chapter_id, str(e)[:80])
                    failed_ops.append({"idx": i, "op": op, "reason": str(e)[:80]})

            if failed_ops:
                logger.warning(
                    "patch_chapter 完成 | chapter=%s | success=%d/%d | failed=%d",
                    chapter_id,
                    patched_count,
                    len(patches),
                    len(failed_ops),
                )

            if patched_count == 0:
                raise ValueError(f"所有 patch 操作均失败: {failed_ops}")

            trimmed = content[: config.storage.max_chapter_chars]
            vid = self._make_version_id()
            parent = ch.get("current_version")
            version_label = self._next_version_label(ch, patch=True)
            new_version = {
                "id": vid,
                "content": trimmed,
                "title": cur_title,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "parent": parent,
                "word_count": len(trimmed.replace("\n", "").replace(" ", "")),
                "version_label": version_label,
                "original_content": original_content,
                "patches_summary": patches_summary,
            }
            ch["versions"].append(new_version)
            ch["current_version"] = vid
            ch["updatedAt"] = datetime.now().isoformat()
            self.save_chapters(book_id, chapters)

        bus.emit_sync(
            Event(
                type=EventType.CHAPTER_UPDATED,
                data={"book_id": book_id, "chapter_id": ch["id"], "version": vid, "message": message},
            )
        )
        try:
            fts_engine.index_chapter(book_id, {"id": ch["id"], "title": cur_title, "content": trimmed})
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS index failed on patch: {e}")

        view = self._chapter_view(ch)
        view["patched_count"] = patched_count
        view["failed_ops"] = failed_ops
        return view

    def reorder_chapters(self, book_id: str, order: list[str]) -> dict:
        """重新排列章节顺序。

        ``order`` 是章节 ID 列表，按期望的新顺序排列。
        不在列表中的章节保持原位置（排在最后）。
        重复 ID 只保留第一次出现。
        """
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            if not chapters:
                raise NotFoundError("该书没有章节")

            id_to_chapter = {}
            for ch in chapters:
                cid = ch.get("id", "")
                if cid:
                    id_to_chapter[cid] = ch

            seen = set()
            reordered = []
            for cid in order:
                if cid in seen:
                    continue
                seen.add(cid)
                ch = id_to_chapter.pop(cid, None)
                if ch:
                    reordered.append(ch)
                else:
                    logger.warning("reorder_chapters 跳过不存在的章节 | book=%s | id=%s", book_id, cid)

            # 未在 order 中出现的章节排在最后
            remaining = [ch for cid, ch in id_to_chapter.items()]
            reordered.extend(remaining)

            self.save_chapters(book_id, reordered)

            old_order = [c.get("id", "?") for c in chapters]
            new_order = [c.get("id", "?") for c in reordered]
            logger.info(
                "reorder_chapters 完成 | book=%s | count=%d | old=%s | new=%s",
                book_id,
                len(reordered),
                old_order,
                new_order,
            )

        return {
            "ok": True,
            "count": len(reordered),
            "skipped": len(order) - len(seen),
            "remaining": len(remaining),
        }

    def chapter_history(self, book_id: str, chapter_id: str) -> list[dict]:
        chapters = self.load_chapters(book_id)
        ch = self._find_chapter(chapters, chapter_id)
        if not ch:
            raise NotFoundError(f"章节不存在: {chapter_id}")
        current = ch.get("current_version", "")
        history = []
        for v in reversed(ch.get("versions", [])):
            entry = {
                "id": v["id"],
                "title": v.get("title", ""),
                "message": v.get("message", ""),
                "timestamp": v.get("timestamp", ""),
                "word_count": v.get("word_count", 0),
                "is_current": v["id"] == current,
                "version_label": v.get("version_label", ""),
                "patches_summary": v.get("patches_summary", []),
            }
            # patch 版本携带原文用于对比
            if v.get("original_content") is not None:
                entry["has_diff"] = True
            history.append(entry)
        return history

    def revert_chapter(self, book_id: str, chapter_id: str, version_id: str) -> dict:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            target = next((v for v in ch["versions"] if v["id"] == version_id or v["id"].startswith(version_id)), None)
            if not target:
                raise NotFoundError(f"版本不存在: {version_id}")
            ch["current_version"] = target["id"]
            ch["updatedAt"] = datetime.now().isoformat()
            if target.get("title"):
                ch["title"] = target["title"]
            self.save_chapters(book_id, chapters)
        try:
            current_content = target.get("content", "")
            fts_engine.index_chapter(
                book_id, {"id": ch["id"], "title": ch.get("title", ""), "content": current_content}
            )
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS re-index failed on revert: {e}")
        self._invalidate_character_mentions(book_id)
        return self._chapter_view(ch)

    def get_chapter_version(self, book_id: str, chapter_id: str, version_id: str) -> dict:
        chapters = self.load_chapters(book_id)
        ch = self._find_chapter(chapters, chapter_id)
        if not ch:
            raise NotFoundError(f"章节不存在: {chapter_id}")
        v = next((v for v in ch["versions"] if v["id"] == version_id or v["id"].startswith(version_id)), None)
        if not v:
            raise NotFoundError(f"版本不存在: {version_id}")
        return v

    def delete_version(self, book_id: str, chapter_id: str, version_id: str) -> dict:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            if len(ch.get("versions", [])) <= 1:
                raise StorageError("无法删除唯一版本", "至少保留一个版本")
            if ch.get("current_version") == version_id:
                raise StorageError("无法删除当前版本", "请先切换到其他版本再删除")
            target = next((v for v in ch["versions"] if v["id"] == version_id or v["id"].startswith(version_id)), None)
            if not target:
                raise NotFoundError(f"版本不存在: {version_id}")
            ch["versions"] = [v for v in ch["versions"] if v["id"] != target["id"]]
            ch["updatedAt"] = datetime.now().isoformat()
            self.save_chapters(book_id, chapters)
        return self._chapter_view(ch)

    def purge_chapter_history(self, book_id: str, chapter_id: str) -> dict:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            current = self._get_current_version(ch)
            new_vid = "v_1"
            current["id"] = new_vid
            current["message"] = "历史已清理，重置为 v1"
            current["timestamp"] = datetime.now().isoformat()
            ch["versions"] = [current]
            ch["current_version"] = new_vid
            ch["updatedAt"] = datetime.now().isoformat()
            self.save_chapters(book_id, chapters)
        return self._chapter_view(ch)

    def purge_all_chapters_history(self, book_id: str) -> int:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            count = 0
            for ch in chapters:
                if len(ch.get("versions", [])) > 1:
                    current = self._get_current_version(ch)
                    new_vid = "v_1"
                    current["id"] = new_vid
                    current["message"] = "历史已清理，重置为 v1"
                    current["timestamp"] = datetime.now().isoformat()
                    ch["versions"] = [current]
                    ch["current_version"] = new_vid
                    ch["updatedAt"] = datetime.now().isoformat()
                    count += 1
            self.save_chapters(book_id, chapters)
        return count

    def update_chapter(self, book_id: str, chapter_id: str, data: dict) -> dict:
        content = data.get("content")
        title = data.get("title")
        status = data.get("status")
        message = data.get("message", "通过API编辑")
        if content is not None:
            return self.edit_chapter(book_id, chapter_id, content, title=title, message=message)
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            if title:
                ch["title"] = title
            if status:
                ch["status"] = status
            ch["updatedAt"] = datetime.now().isoformat()
            self.save_chapters(book_id, chapters)
            self._invalidate_character_mentions(book_id)
            return self._chapter_view(ch)

    def set_chapter_status(self, book_id: str, chapter_id: str, status: str) -> dict:
        """Set chapter status (draft/final) and return chapter view."""
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            ch = self._find_chapter(chapters, chapter_id)
            if not ch:
                raise NotFoundError(f"章节不存在: {chapter_id}")
            ch["status"] = status
            ch["updatedAt"] = datetime.now().isoformat()
            self.save_chapters(book_id, chapters)
        return self._chapter_view(ch)

    def delete_chapter(self, book_id: str, chapter_id: str) -> int:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            target = self._find_chapter(chapters, chapter_id)
            if not target:
                return 0
            resolved_id = target["id"]
            before = len(chapters)
            chapters = [c for c in chapters if c["id"] != resolved_id]
            self.save_chapters(book_id, chapters)
            non_extra_count = sum(1 for c in chapters if not c.get("is_extra"))
            self.update_book_stats(book_id, chapter_count=non_extra_count)
        deleted = before - len(chapters)
        if deleted:
            bus.emit_sync(
                Event(
                    type=EventType.CHAPTER_DELETED,
                    data={"book_id": book_id, "chapter_id": resolved_id, "count": deleted},
                )
            )
        try:
            fts_engine.remove_chapter(resolved_id)
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS remove_chapter failed: {e}")
        self._invalidate_character_mentions(book_id)
        return deleted

    def delete_all_chapters(self, book_id: str) -> int:
        with book_lock(book_id):
            chapters = self.load_chapters(book_id)
            count = len(chapters)
            self.save_chapters(book_id, [])
            self.update_book_stats(book_id, chapter_count=0)
        try:
            fts_engine.clear_book(book_id)
        except (OSError, RuntimeError) as e:
            logger.debug(f"FTS clear_book failed: {e}")
        self._invalidate_character_mentions(book_id)
        return count

    # --- Character mentions cache (heatmap data) ---

    def _character_mentions_cache_file(self, book_id: str) -> Path:
        return DATA_DIR / f"char_mentions_{book_id}.json"

    def get_character_mentions(self, book_id: str) -> dict | None:
        """Return cached mentions matrix, or None if never computed."""
        try:
            data = self._read_json(self._character_mentions_cache_file(book_id))
            if isinstance(data, dict) and "matrix" in data:
                return data
        except NotFoundError:
            pass
        return None

    def _invalidate_character_mentions(self, book_id: str) -> None:
        """Drop stale cache. Safe to call even if cache file doesn't exist."""
        path = self._character_mentions_cache_file(book_id)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    def refresh_character_mentions(self, book_id: str) -> dict:
        """Scan all chapters for character name + alias mentions. Returns and caches the matrix.

        Uses a single compiled alternation regex per scan (one pass per chapter)
        for acceptable perf on 500k-char books with ~30 characters.
        """
        from core.graph_store import get_store

        kb = get_store(book_id)
        chars = [e for e in kb.list_entities() if getattr(e, "type", "") == "character"]

        # Build name -> id map with all aliases, sorted longest-first so
        # regex alternation prefers more specific names (e.g. "叶不凡" over "叶").
        name_to_id: dict[str, str] = {}
        for c in chars:
            all_names = [c.name] + list(getattr(c, "aliases", []) or [])
            for n in all_names:
                n = (n or "").strip()
                if n:
                    name_to_id[n] = c.id
        # Auto-derive short names from full names containing separator chars
        # e.g. "哈利·波特" -> "哈利", "罗恩·韦斯莱" -> "罗恩"
        # Only add if no conflict (short name not already mapped to a different ID)
        for c in chars:
            short = (c.name or "").split("·")[0].strip()
            if short and len(short) >= 2 and short not in name_to_id:
                name_to_id[short] = c.id
        if not name_to_id:
            result = {"matrix": [], "lastUpdatedAt": datetime.now().isoformat(), "chaptersCount": 0}
            self._write_json(self._character_mentions_cache_file(book_id), result)
            return result
        sorted_names = sorted(name_to_id.keys(), key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(n) for n in sorted_names))

        chapters = self.load_chapters(book_id)
        matrix: list[dict] = []
        for c in chars:
            ch_counts: list[dict] = []
            for idx, ch in enumerate(chapters, 1):
                content = self._get_current_version(ch).get("content", "") or ""
                count = 0
                if content:
                    matches = pattern.findall(content)
                    for m in matches:
                        if name_to_id.get(m) == c.id:
                            count += 1
                if count > 0:
                    ch_counts.append({"idx": idx, "count": count})
            matrix.append(
                {
                    "charId": c.id,
                    "charName": c.name,
                    "aliases": list(getattr(c, "aliases", []) or []),
                    "totalMentions": sum(x["count"] for x in ch_counts),
                    "chapters": ch_counts,
                }
            )

        # Sort by total mentions descending so important characters appear at top of heatmap.
        matrix.sort(key=lambda x: x["totalMentions"], reverse=True)

        result = {
            "matrix": matrix,
            "lastUpdatedAt": datetime.now().isoformat(),
            "chaptersCount": len(chapters),
        }
        self._write_json(self._character_mentions_cache_file(book_id), result)
        return result
