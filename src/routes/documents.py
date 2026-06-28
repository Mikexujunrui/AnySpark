import asyncio
import json
import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.config import UPLOAD_DIR, config
from core.document_parser import parse_document
from data.json_store import json_store

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS = {'.txt', '.md', '.docx'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def sanitize_filename(filename: str) -> str:
    """清洗文件名，防止路径穿越"""
    name = PurePosixPath(filename).name
    name = re.sub(r'[^\w\-_. \u4e00-\u9fff]', '_', name)
    return name or 'unnamed'


def validate_upload(filename: str, file_size: int) -> None:
    """验证上传文件"""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: {ext}")
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(400, f"文件过大: {file_size/1024/1024:.1f}MB > 50MB")


@router.post("/books/{book_id}/upload")
async def upload_document(book_id: str, file: UploadFile = File(...),
                          session_id: str = Form("")):
    if not session_id:
        raise HTTPException(400, "session_id required")

    safe_filename = sanitize_filename(file.filename or "file.txt")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    validate_upload(safe_filename, file_size)

    suffix = Path(safe_filename).suffix.lower()
    doc_id = str(int(datetime.now().timestamp() * 1000))
    save_path = UPLOAD_DIR / f"{doc_id}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    full_text = parse_document(save_path)
    json_store.add_doc(session_id, doc_id, safe_filename, len(full_text), str(save_path))

    return {"message": f"文件已就绪: {safe_filename} ({len(full_text)} 字, id: {doc_id[:8]})",
            "docId": doc_id, "filename": safe_filename, "chars": len(full_text)}


@router.get("/books/{book_id}/documents")
def list_documents(book_id: str, session_id: str = ""):
    sid = session_id or book_id
    return json_store.load_docs(sid)


@router.get("/books/{book_id}/documents/{doc_id}")
def read_document(book_id: str, doc_id: str, offset: int = 0, limit: int = 5000, session_id: str = ""):
    sid = session_id or book_id
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        raise HTTPException(404, "文档不存在")
    path = Path(doc["path"])
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    text = path.read_text(encoding="utf-8")
    return {"id": doc_id, "filename": doc["filename"], "chars": len(text),
            "content": text[offset:offset + limit], "offset": offset, "limit": limit,
            "hasMore": (offset + limit) < len(text)}


class DetectChaptersResponse(BaseModel):
    method: str
    pattern: str = ""
    chapters: list[dict] = []
    total_chars: int = 0
    sample_used: int = 0
    message: str = ""


@router.post("/books/{book_id}/documents/{doc_id}/detect-chapters")
async def detect_chapters(book_id: str, doc_id: str, session_id: str = Form("")):
    """Phase 1: AI detects chapter pattern from document sample, returns preview."""
    sid = session_id or book_id
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        raise HTTPException(404, "文档不存在")
    path = Path(doc["path"])
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    full_text = path.read_text(encoding="utf-8")
    total_chars = len(full_text)

    # Try regex first (fast path)
    chapters_data = _regex_split(full_text)
    if chapters_data:
        return DetectChaptersResponse(
            method="regex",
            pattern=r"第[一二三四五六七八九十百千万\d]+章",
            chapters=chapters_data[:20],
            total_chars=total_chars,
            message=f"正则匹配成功: {len(chapters_data)} 章",
        )

    # AI-assisted detection
    from core.llm_client import chat as llm_chat
    sample = full_text[:50000]
    detect_system = """你是文档结构分析专家。分析文本的章节标题格式，输出:
1. 精确的章节标题正则表达式（兼容 Python re 模块）
2. 所有识别到的章节标题

输出 JSON:
{
  "pattern": "正则表达式",
  "titles": ["第1章 xxx", "第2章 xxx"],
  "description": "格式说明"
}
注意: pattern 必须用原始字符串格式，不要包含 re.compile 调用。"""
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, llm_chat,
            f"分析以下文档的章节结构:\n{sample}", detect_system, 0.1, "extraction"
        )
    except Exception:
        raise HTTPException(500, "AI分析失败，请手动确认文档格式")

    j = response.strip()
    if j.startswith("```json"):
        j = j[7:]
    if j.startswith("```"):
        j = j[3:]
    if j.endswith("```"):
        j = j[:-3]
    try:
        data = json.loads(j.strip())
    except json.JSONDecodeError:
        raise HTTPException(500, "AI返回格式异常，请手动确认文档格式")

    ai_pattern = data.get("pattern", "")
    titles = data.get("titles", [])
    description = data.get("description", "")

    if not ai_pattern or len(titles) < 2:
        raise HTTPException(400, "无法识别章节结构。文档可能没有明确的章节分隔，或格式过于特殊。")

    # Apply AI pattern to full text
    chapters_data = _split_by_pattern(full_text, ai_pattern)
    if not chapters_data or len(chapters_data) < 2:
        chapters_data = _split_by_titles(full_text, titles)

    return DetectChaptersResponse(
        method="ai",
        pattern=ai_pattern,
        chapters=chapters_data[:20],
        total_chars=total_chars,
        sample_used=len(sample),
        message=f"AI检测到 {len(titles)} 个章节标题，格式: {description}。建议先预览确认。",
    )


class ImportConfirm(BaseModel):
    pattern: str = ""
    titles: list[str] = []
    confirm: bool = True
    extract_knowledge: bool = False
    volume_name: str = ""


@router.post("/books/{book_id}/documents/{doc_id}/import-chapters")
async def confirm_import(book_id: str, doc_id: str, data: ImportConfirm, session_id: str = ""):
    """Phase 2: User confirms or adjusts pattern, then import chapters."""
    sid = session_id or book_id
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        raise HTTPException(404, "文档不存在")
    path = Path(doc["path"])
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    full_text = path.read_text(encoding="utf-8")

    if data.pattern:
        chapters_data = _split_by_pattern(full_text, data.pattern)
    elif data.titles:
        chapters_data = _split_by_titles(full_text, data.titles)
    else:
        chapters_data = _regex_split(full_text)

    if not chapters_data:
        raise HTTPException(400, "未匹配到章节，请检查正则或标题列表")

    for cd in chapters_data:
        json_store.add_chapter(book_id, cd["title"], cd["content"])

    titles = ", ".join(cd["title"][:20] for cd in chapters_data[:5])
    return {
        "message": f"已导入 {len(chapters_data)} 个章节",
        "count": len(chapters_data),
        "preview": f"{titles}{'...' if len(chapters_data) > 5 else ''}",
        "chapter_ids": [cd.get("id") for cd in chapters_data if cd.get("id")],
    }


class BatchExtractRequest(BaseModel):
    chapter_ids: list[str] = []


@router.post("/books/{book_id}/documents/{doc_id}/import-chapters/batch-extract")
async def batch_extract_after_import(book_id: str, doc_id: str, data: BatchExtractRequest):
    """Phase 3 (optional): Batch extract knowledge from imported chapters."""
    if not data.chapter_ids:
        return {"message": "无需提取", "extracted": 0, "entities": []}

    try:
        from core.extractor import extract_from_text
        from core.graph_store import GraphStore

        store = GraphStore(project_id=book_id)
        chapters = json_store.load_chapters(book_id)
        all_extracted = []

        for cid in data.chapter_ids:
            chapter = next((c for c in chapters if c.get("id") == cid), None)
            if not chapter:
                continue
            text = chapter.get("content", "")
            if not text.strip():
                continue
            try:
                result = extract_from_text(book_id, text[:3000])
                if result and result.get("entities"):
                    for entity in result["entities"]:
                        try:
                            store.add_entity(entity)
                            all_extracted.append({
                                "name": entity.get("name", ""),
                                "type": entity.get("type", ""),
                            })
                        except Exception:
                            pass
            except Exception:
                pass

        return {
            "message": f"提取完成，共 {len(all_extracted)} 个实体",
            "extracted": len(all_extracted),
            "entities": all_extracted[:50],
        }
    except ImportError:
        raise HTTPException(500, "知识提取模块不可用")
    except Exception as e:
        raise HTTPException(500, f"批量提取失败: {str(e)[:200]}")


# ── Helper functions ──

def _regex_split(full_text: str) -> list[dict]:
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

    chapters_data = []
    for i, m in enumerate(valid_matches):
        ch_num = m.group(1) or m.group(3)
        ch_name = (m.group(2) or m.group(4) or "").strip()
        title = f"{ch_num} {ch_name}".strip() if ch_name else ch_num
        start = m.end()
        end = valid_matches[i + 1].start() if i + 1 < len(valid_matches) else len(full_text)
        content = full_text[start:end].strip()
        if len(content) < 500:
            continue
        chapters_data.append({"title": title, "content": content[:config.storage.max_chapter_chars]})
    return chapters_data


def _split_by_pattern(full_text: str, pattern: str) -> list[dict]:
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except re.error:
        return []
    matches = list(compiled.finditer(full_text))
    if not matches or len(matches) < 2:
        return []
    chapters_data = []
    for i, m in enumerate(matches):
        title = m.group().strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()
        if len(content) < 200:
            continue
        chapters_data.append({"title": title, "content": content[:config.storage.max_chapter_chars]})
    return chapters_data


def _split_by_titles(full_text: str, titles: list[str]) -> list[dict]:
    positions = []
    for title in titles:
        idx = full_text.find(title)
        if idx >= 0:
            positions.append({"title": title, "pos": idx})
    positions.sort(key=lambda x: x["pos"])
    positions = [p for i, p in enumerate(positions)
                 if i == 0 or p["pos"] - positions[i - 1]["pos"] > 200]
    if len(positions) < 2:
        return []
    chapters_data = []
    for i, p in enumerate(positions):
        start = p["pos"] + len(p["title"])
        end = positions[i + 1]["pos"] if i + 1 < len(positions) else len(full_text)
        content = full_text[start:end].strip()
        if len(content) > 200:
            chapters_data.append({"title": p["title"], "content": content[:config.storage.max_chapter_chars]})
    return chapters_data
