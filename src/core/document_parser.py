from pathlib import Path

MAX_CHUNK_SIZE = 8000


def parse_document(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == '.txt':
        return _read_text(path)
    elif suffix == '.docx':
        return _parse_docx(path)
    elif suffix == '.md':
        return _read_text(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}")


def chunk_text(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    paragraphs = text.split('\n')
    chunks = []
    current = ''

    for para in paragraphs:
        if len(current) + len(para) + 1 > max_size and current:
            chunks.append(current.strip())
            current = para
        else:
            current += '\n' + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _read_text(path: Path) -> str:
    for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312']:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding='utf-8', errors='replace')


def _parse_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)
    return '\n'.join(paragraphs)
