"""Import tool implementations — store inspiration, import reference/doc chapters, split.

Extracted from executor.py to keep module sizes manageable.
"""

import json
import logging
import re
from pathlib import Path

from core.config import config
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store

logger = logging.getLogger(__name__)


def _store_inspiration(args: dict, book_id: str, msg: str) -> str:
    content = args.get("content", msg)
    tags = args.get("tags", [])
    json_store.add_note(book_id, content, tags)
    return f"灵感已保存 (标签: {tags or ['灵感']})"


async def _import_reference_chapters(loop, args: dict, kb, book_id: str) -> str:
    """从参考书导入指定章节到当前书籍。

    args:
        ref_book_id: 参考书籍 ID
        chapter_ids: 要导入的章节 ID 列表
    """
    ref_book_id = args.get("ref_book_id")
    chapter_ids = args.get("chapter_ids", [])

    if not ref_book_id:
        return "错误：未指定参考书 ID"

    if not chapter_ids:
        return "错误：未指定要导入的章节 ID"

    # Validate ref_book_id is in reference books
    ref_books = json_store.get_reference_books(book_id)
    if ref_book_id not in ref_books:
        return f"错误：书籍 {ref_book_id} 不在当前书籍的参考书列表中"

    # Get chapters from reference book
    try:
        ref_chapters = json_store.load_chapters(ref_book_id)
    except Exception as e:
        return f"错误：无法读取参考书章节：{str(e)}"

    # Validate requested chapter IDs exist (with prefix matching for truncated IDs)
    ref_chapter_ids = {ch["id"] for ch in ref_chapters}
    # Build a lookup that supports both exact and prefix match
    invalid_ids = []
    resolved_ids = {}
    for cid in chapter_ids:
        if cid in ref_chapter_ids:
            resolved_ids[cid] = cid
        else:
            prefix_matches = [rid for rid in ref_chapter_ids if rid.startswith(cid)]
            if len(prefix_matches) == 1:
                resolved_ids[cid] = prefix_matches[0]
            else:
                invalid_ids.append(cid)
    if invalid_ids:
        return f"错误：以下章节 ID 在参考书中不存在：{', '.join(invalid_ids)}"

    # Import chapters (use resolved IDs)
    imported_count = 0
    imported_titles = []
    for chapter_id in chapter_ids:
        resolved_id = resolved_ids[chapter_id]
        ref_chapter = next((ch for ch in ref_chapters if ch["id"] == resolved_id), None)
        if not ref_chapter:
            continue

        title = ref_chapter.get("title", f"参考章节_{chapter_id}")
        # Content lives inside versions[current_version], not at chapter top-level
        view = json_store._chapter_view(ref_chapter)
        content = view.get("content", "")

        # Add to current book (not as extra, so it becomes a normal chapter)
        try:
            json_store.add_chapter(book_id, title, content, is_extra=False)
            imported_count += 1
            imported_titles.append(title[:30])
        except Exception as e:
            logger.error(f"导入章节失败 {chapter_id}: {e}")
            continue

    if imported_count == 0:
        return "导入失败：未能导入任何章节"

    return f"成功导入 {imported_count} 个章节：{', '.join(imported_titles)}"


async def _import_chapters(
        loop, args: dict, kb, book_id: str, session_id: str) -> str:
    doc_id = args.get("doc_id", "")
    sid = session_id or book_id
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        return f"文档 {doc_id} 不存在"

    full_text = Path(doc["path"]).read_text(encoding="utf-8")
    chapters_data = []

    chapters_data = _regex_split_chapters(full_text)

    if not chapters_data:
        chapters_data = await _llm_split_chapters(loop, full_text)

    if not chapters_data:
        return "未检测到章节结构。请确认文档格式，或手动指定章节。"

    for cd in chapters_data:
        json_store.add_chapter(book_id, cd["title"], cd["content"])

    total_chars = sum(len(cd["content"]) for cd in chapters_data)
    titles = ", ".join(cd["title"][:20] for cd in chapters_data[:5])
    return f"已创建 {len(chapters_data)} 个章节 (共 {total_chars} 字): {titles}{'...' if len(chapters_data) > 5 else ''}"


def _regex_split_chapters(full_text: str) -> list[dict]:
    chapter_heading = re.compile(
        r'^.*?(第[一二三四五六七八九十百千万\d]+章)\s*(.*?)$|^(Chapter\s+\d+)\s*(.*?)$',
        re.MULTILINE
    )
    matches = list(chapter_heading.finditer(full_text))
    if not matches:
        return []

    valid_matches = []
    for m in matches:
        line_start = full_text.rfind("\n", 0, m.start()) + 1
        line_end = full_text.find("\n", m.end())
        if line_end == -1:
            line_end = len(full_text)
        line = full_text[line_start:line_end]
        if len(line) < 120:
            valid_matches.append(m)

    if not valid_matches:
        return []

    candidates = []
    for i, m in enumerate(valid_matches):
        ch_num = m.group(1) or m.group(3)
        ch_name = (m.group(2) or m.group(4) or "").strip()
        title = f"{ch_num} {ch_name}".strip() if ch_name else ch_num
        start = m.end()
        end = valid_matches[i + 1].start() if i + \
            1 < len(valid_matches) else len(full_text)
        content = full_text[start:end].strip()
        candidates.append(
            {"title": title, "content": content, "chars": len(content)})

    min_chapter_chars = 500
    best_by_title: dict[str, dict] = {}
    for c in candidates:
        if c["chars"] < min_chapter_chars:
            continue
        norm_title = re.sub(r'\s+', '', c["title"])
        existing = best_by_title.get(norm_title)
        if not existing or c["chars"] > existing["chars"]:
            best_by_title[norm_title] = c

    chapters_data = []
    seen = set()
    for c in candidates:
        norm_title = re.sub(r'\s+', '', c["title"])
        if norm_title in seen:
            continue
        best = best_by_title.get(norm_title)
        if not best:
            continue
        seen.add(norm_title)
        chapters_data.append({
            "title": best["title"],
            "content": best["content"][:config.storage.max_chapter_chars],
        })

    return chapters_data


async def _llm_split_chapters(loop, full_text: str) -> list[dict]:
    sample = full_text[:50000]
    detect_system = """你是文档结构分析器。识别文本中的章节标题模式。
文档可能使用非标准章节格式（如"卷一"、"上篇"、数字编号、特殊符号分隔等）。

分析文本，输出所有你能识别的章节标题的原文。
输出JSON数组: [{"title": "完整章节标题原文"}, ...]
按文档顺序排列。如果没有明确的章节划分则返回空数组 []。"""
    result = await loop.run_in_executor(
        _ai_executor, llm_chat,
        f"分析以下文档的章节结构:\n{sample}", detect_system, 0.1, "extraction"
    )

    try:
        j = result.strip()
        if j.startswith("```"):
            j = j.split("\n", 1)[1]
        if j.endswith("```"):
            j = j.rsplit("\n", 1)[0]
        titles_list = json.loads(j.strip())
    except (json.JSONDecodeError, Exception):
        return []

    if not titles_list or not isinstance(
            titles_list, list) or len(titles_list) < 2:
        return []

    chapter_titles = [t.get("title", "")
                      for t in titles_list if t.get("title")]
    if len(chapter_titles) < 2:
        return []

    positions = []
    for title in chapter_titles:
        idx = full_text.find(title)
        if idx >= 0:
            positions.append({"title": title, "pos": idx})

    positions.sort(key=lambda x: x["pos"])
    positions = [p for i, p in enumerate(positions)
                 if i == 0 or p["pos"] - positions[i - 1]["pos"] > 200]

    chapters_data = []
    for i, p in enumerate(positions):
        start = p["pos"] + len(p["title"])
        end = positions[i + 1]["pos"] if i + \
            1 < len(positions) else len(full_text)
        content = full_text[start:end].strip()
        if len(content) > 200:
            chapters_data.append({
                "title": p["title"],
                "content": content[:config.storage.max_chapter_chars],
            })

    return chapters_data
