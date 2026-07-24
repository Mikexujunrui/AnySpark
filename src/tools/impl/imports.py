"""Import tool implementations — store inspiration, import reference/doc chapters, split.

Extracted from executor.py to keep module sizes manageable.
"""

import json
import logging
import re

from core.config import config
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store

logger = logging.getLogger(__name__)


def _manage_notes(args: dict, book_id: str, msg: str) -> str:
    action = args.get("action", "list")
    if action == "add":
        content = args.get("content", "")
        if not content:
            return "错误: 添加笔记需要 content 参数"
        tags = args.get("tags", [])
        note = json_store.add_note(book_id, content, tags)
        return f"笔记已添加 (id: {note['id'][:12]}...)"
    elif action == "list":
        notes = json_store.load_notes(book_id)
        if not notes:
            return "暂无笔记。"
        lines = [f"共 {len(notes)} 条笔记:"]
        for n in notes:
            tags_str = f" [{', '.join(n.get('tags', []))}]" if n.get("tags") else ""
            lines.append(f"  [{n['id'][:12]}] {n['content'][:100]}{tags_str}")
        return "\n".join(lines)
    elif action == "delete":
        note_id = args.get("note_id", "")
        if not note_id:
            return "错误: 删除笔记需要 note_id 参数"
        ok = json_store.delete_note(book_id, note_id)
        return "笔记已删除" if ok else f"未找到笔记: {note_id}"
    else:
        return f"未知操作: {action}，支持 add | list | delete"


async def _import_reference_chapters(loop, args: dict, kb, book_id: str) -> str:
    """从参考书批量导入章节到当前书籍。

    args:
        ref_book_id: 参考书籍 ID
        chapter_ids: 要导入的章节 ID 列表，传 ["*"] 或 ["all"] 导入全部章节
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

    # ── Handle "import all" shortcut ──
    import_all = len(chapter_ids) == 1 and str(chapter_ids[0]).strip() in ("*", "all")
    if import_all:
        # Limit to a reasonable max to avoid OOM
        max_chapters = 200
        if len(ref_chapters) > max_chapters:
            return (
                f"参考书共有 {len(ref_chapters)} 章，超过单次导入上限 {max_chapters} 章。"
                f'请指定章节范围（如 chapter_ids=["#1","#2",...]）或分批导入。'
            )
        chapter_ids = [ch["id"] for ch in ref_chapters]

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

    # ── Collect chapters data for batch import ──
    # Deduplicate by title against existing chapters in target book
    existing_chapters = json_store.load_chapters(book_id)
    existing_titles = {ch.get("title", "") for ch in existing_chapters}

    chapters_data = []
    skipped_titles = []
    for chapter_id in chapter_ids:
        resolved_id = resolved_ids[chapter_id]
        ref_chapter = next((ch for ch in ref_chapters if ch["id"] == resolved_id), None)
        if not ref_chapter:
            continue

        title = ref_chapter.get("title", f"参考章节_{chapter_id}")
        if title in existing_titles:
            skipped_titles.append(title[:30])
            continue

        view = json_store._chapter_view(ref_chapter)
        content = view.get("content", "")
        chapters_data.append({"title": title, "content": content})

    if not chapters_data:
        skip_info = f"（跳过 {len(skipped_titles)} 章已存在）" if skipped_titles else ""
        return f"导入完成：无需导入，所有目标章节已存在{skip_info}"

    # ── Batch import: one load, one save, one FTS rebuild ──
    json_store.batch_add_chapters(book_id, chapters_data)

    titles = ", ".join(cd["title"][:30] for cd in chapters_data[:5])
    result = f"成功导入 {len(chapters_data)} 个章节：{titles}"
    if len(chapters_data) > 5:
        result += f"...（共 {len(chapters_data)} 章）"
    if skipped_titles:
        result += f"\n跳过 {len(skipped_titles)} 章已存在：{', '.join(skipped_titles[:5])}"
        if len(skipped_titles) > 5:
            result += f"...（共 {len(skipped_titles)} 章）"
    return result


async def _import_chapters(loop, args: dict, kb, book_id: str, session_id: str) -> str:
    doc_id = args.get("doc_id", "")
    sid = session_id or book_id
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        return f"文档 {doc_id} 不存在"

    from core.document_parser import parse_document

    full_text = parse_document(doc["path"])
    chapters_data = []

    chapters_data = _regex_split_chapters(full_text)

    if not chapters_data:
        chapters_data = await _llm_split_chapters(loop, full_text)

    if not chapters_data:
        return "未检测到章节结构。请确认文档格式，或手动指定章节。"

    # 批量导入：一次加载、一次保存，1281章也从O(n²)降到O(n)
    json_store.batch_add_chapters(book_id, chapters_data)

    total_chars = sum(len(cd["content"]) for cd in chapters_data)
    titles = ", ".join(cd["title"][:20] for cd in chapters_data[:5])
    return (
        f"已创建 {len(chapters_data)} 个章节 (共 {total_chars} 字): {titles}{'...' if len(chapters_data) > 5 else ''}"
    )


def _regex_split_chapters(full_text: str) -> list[dict]:
    # Chinese numeral pattern (一~九百九十九) + digit pattern
    cn_num = r"[零一二三四五六七八九十百千万]+"
    digit = r"\d+"
    num = f"(?:{cn_num}|{digit})"
    # Optional volume prefix: "第X卷" before the chapter heading
    vol_prefix = rf"(?:第{num}[卷部篇集])?\s*"
    # Chapter heading: 第X章/回/节/幕/话
    ch_heading = rf"{vol_prefix}第{num}\s*[章回节幕话]"
    # Special chapters: 序章/楔子/番外/尾声/后记/附录/终章/引子
    special = r"(?:序章|楔子|番外|尾声|后记|附录|终章|引子|开篇|结局)"
    # Numbered: 123. or 123、 or 【123】 at line start
    numbered = r"^\s*\d+[\s\.、，．]+"
    # Roman numerals: I. II. III. etc at line start
    roman = r"^\s*[IVXLCDM]{2,}\."

    chapter_heading = re.compile(
        rf"^({ch_heading}|{special})\s*[：:]?\s*(.*?)$"
        rf"|^(Chapter\s+\d+|Volume\s+\d+)\s*[：:]?\s*(.*?)$"
        rf"|({numbered})\s*(.*?)$"
        rf"|({roman})\s*(.*?)$",
        re.MULTILINE,
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
        # New regex groups: 1=ch_heading|special, 2=title, 3=Chapter/Volume, 4=title,
        # 5=numbered, 6=title, 7=roman, 8=title
        if m.group(1):
            ch_num = m.group(1)
            ch_name = (m.group(2) or "").strip()
        elif m.group(3):
            ch_num = m.group(3)
            ch_name = (m.group(4) or "").strip()
        elif m.group(5):
            ch_num = m.group(5).strip()
            ch_name = (m.group(6) or "").strip()
        else:
            ch_num = m.group(7).strip()
            ch_name = (m.group(8) or "").strip()
        title = f"{ch_num} {ch_name}".strip() if ch_name else ch_num
        start = m.end()
        end = valid_matches[i + 1].start() if i + 1 < len(valid_matches) else len(full_text)
        content = full_text[start:end].strip()
        candidates.append({"title": title, "content": content, "chars": len(content)})

    min_chapter_chars = 500
    best_by_title: dict[str, dict] = {}
    for c in candidates:
        if c["chars"] < min_chapter_chars:
            continue
        norm_title = re.sub(r"\s+", "", c["title"])
        existing = best_by_title.get(norm_title)
        if not existing or c["chars"] > existing["chars"]:
            best_by_title[norm_title] = c

    chapters_data = []
    seen = set()
    for c in candidates:
        norm_title = re.sub(r"\s+", "", c["title"])
        if norm_title in seen:
            continue
        best = best_by_title.get(norm_title)
        if not best:
            continue
        seen.add(norm_title)
        chapters_data.append(
            {
                "title": best["title"],
                "content": best["content"][: config.storage.max_chapter_chars],
            }
        )

    return chapters_data


async def _llm_split_chapters(loop, full_text: str) -> list[dict]:
    # Sample from beginning, middle, and end for large texts
    text_len = len(full_text)
    if text_len <= 50000:
        sample = full_text
    else:
        head = full_text[:20000]
        mid_start = text_len // 2 - 10000
        mid = full_text[mid_start : mid_start + 20000]
        tail = full_text[-20000:]
        sample = f"{head}\n\n... (省略中间内容) ...\n\n{mid}\n\n... (省略中间内容) ...\n\n{tail}"
    detect_system = """你是文档结构分析器。识别文本中的章节标题模式。
文档可能使用非标准章节格式（如"卷一"、"上篇"、数字编号、特殊符号分隔等）。

分析文本，输出所有你能识别的章节标题的原文。
输出JSON数组: [{"title": "完整章节标题原文"}, ...]
按文档顺序排列。如果没有明确的章节划分则返回空数组 []。"""
    result = await loop.run_in_executor(
        _ai_executor, llm_chat, f"分析以下文档的章节结构:\n{sample}", detect_system, 0.1, "extraction"
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

    if not titles_list or not isinstance(titles_list, list) or len(titles_list) < 2:
        return []

    chapter_titles = [t.get("title", "") for t in titles_list if t.get("title")]
    if len(chapter_titles) < 2:
        return []

    positions = []
    for title in chapter_titles:
        idx = full_text.find(title)
        if idx >= 0:
            positions.append({"title": title, "pos": idx})

    positions.sort(key=lambda x: x["pos"])
    positions = [p for i, p in enumerate(positions) if i == 0 or p["pos"] - positions[i - 1]["pos"] > 200]

    chapters_data = []
    for i, p in enumerate(positions):
        start = p["pos"] + len(p["title"])
        end = positions[i + 1]["pos"] if i + 1 < len(positions) else len(full_text)
        content = full_text[start:end].strip()
        if len(content) > 200:
            chapters_data.append(
                {
                    "title": p["title"],
                    "content": content[: config.storage.max_chapter_chars],
                }
            )

    return chapters_data
