"""
anyspark.server.ingest — 输入消化管线共享核心（S83 R2 收敛）。

消除 tools_domain.make_ingest_implementer（ingest_document 工具）与
routes_tools.ingest_upload（端点）的重复实现：read_upload → extract_text →
chapterize → is_card 判别 → 摘要卡/拆章，两处调用本管线，差异留在各自包装层。

行为契约（两处原实现零变化）：
- 错误不抛异常，全部返回 IngestResult（error_code 分类 + error 完整文案）
- 唯一差异：allowed_ext 扩展名校验仅端点启用（工具不过滤扩展名）
- unknown 错误携带原始 exception，端点可 re-raise 恢复原 500 行为
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 允许的文本扩展名（端点校验用；工具不校验——保持原行为）
INGEST_ALLOWED_EXT = {".txt", ".md", ".markdown", ".docx", ".pdf"}


@dataclass
class IngestResult:
    """消化管线结果（调用方各自包装为 ToolResult / HTTP 响应）。"""

    ok: bool = True
    kind: str = ""  # "card" | "chapters" | ""（错误）
    # card 分支
    title: str = ""
    topic: str = ""
    key_points: list[str] = field(default_factory=list)
    card_file: str = ""
    material_id: str = ""
    # chapters 分支：[{"order", "title", "chars"}]
    chapters: list[dict[str, Any]] = field(default_factory=list)
    # 错误（ok=False 时）
    error: str = ""  # 完整错误文案（工具直接用作 content）
    error_code: str = ""  # not_found | bad_ext | empty | unknown | ""
    upload_names: str = ""  # not_found 时现有上传文件清单（工具文案用）
    exception: Exception | None = None  # unknown 时原始异常（端点 re-raise 保 500）


def ingest_pipeline(
    workspace: Any,
    chapters: Any,
    materials: Any,
    model: Any,
    book_id: str,
    filename: str,
    mode: str = "auto",
    allowed_ext: set[str] | None = None,
    skills: Any | None = None,
) -> IngestResult:
    """消化上传区文件：skill 文件判别 / 长文拆章 / 短文本摘要卡。

    - workspace/chapters/materials/model：组合根依赖（同原实现注入）
    - allowed_ext：扩展名校验（端点传 INGEST_ALLOWED_EXT；工具传 None 不校验）
    - skills（S118）：传入 WritingSkillStore 时启用 skill 文件判别分支——
      front-matter 五段式 → 解析 → skill_drafts 草稿（全局，人工确认转正）
    - 失败返回 IngestResult(ok=False, error_code, error, ...)；不抛异常
    """
    from anyspark.server.pipeline import chapterize, extract_text
    from anyspark.server.skill_io import parse_skill_file

    path = workspace.read_upload(book_id, filename)
    if path is None:
        ups = workspace.list_uploads(book_id)
        names = "、".join(u["name"] for u in ups) or "（空）"
        return IngestResult(
            ok=False,
            error_code="not_found",
            error=f"上传区无「{filename}」。现有：{names}",
            upload_names=names,
        )
    if allowed_ext and path.suffix.lower() not in allowed_ext:
        return IngestResult(
            ok=False,
            error_code="bad_ext",
            error="仅支持 txt/md/docx/pdf 文本消化（图片放未来）",
        )
    try:
        text = extract_text(path)
        if not text.strip():
            return IngestResult(
                ok=False,
                error_code="empty",
                error="无法提取文本（扫描件 OCR 放未来计划），可先列上传区确认文件格式。",
            )
        # S118 提案 D：skill 文件判别（front-matter 严格，不误判普通 md）
        if skills is not None:
            skill = parse_skill_file(text)
            if skill is not None:
                draft = skills.add_draft(
                    name=skill["name"],
                    description=skill["description"],
                    content=skill["content"],
                    example=skill["example"],
                    tags=skill["tags"],
                    type=skill["type"],
                    pack_id=skill.get("pack_id", ""),
                    source="import",
                )
                if draft is None:
                    return IngestResult(
                        ok=False,
                        error_code="dup",
                        error=f"skill「{skill['name']}」已存在同名草稿或技能（先确认/删除旧的）",
                    )
                return IngestResult(
                    ok=True,
                    kind="skill",
                    title=skill["name"],
                    material_id=str(draft.get("id", "")),
                )
        chaps = chapterize(text, fallback_title=path.stem)
        # 判别：mode 强制 / 单章短文本 → 摘要卡；否则拆章（与原实现逐字一致）
        is_card = mode == "card" or (mode != "chapters" and len(chaps) == 1 and len(text) < 3000)
        if is_card:
            from anyspark.template import MaterialDigestor

            digestor = MaterialDigestor(model)
            saved = materials.save(digestor.digest(text), book_id)
            card_md = (
                f"# {saved.title}\n\n主题：{saved.topic}\n\n"
                + "要点："
                + "；".join(saved.key_points[:6])
                + "\n设定："
                + "；".join(saved.key_settings[:6])
                + "\n角色："
                + "、".join(saved.characters[:8])
                + "\n术语："
                + "、".join(saved.terms[:8])
            )
            f = workspace.write_card(book_id, "摘要卡", saved.title, card_md)
            return IngestResult(
                ok=True,
                kind="card",
                title=saved.title,
                topic=saved.topic,
                key_points=list(saved.key_points[:4]),
                card_file=f.name,
                material_id=saved.id,
            )
        written: list[dict[str, Any]] = []
        for i, ch in enumerate(chaps):
            workspace.write_chapter(book_id, i, ch["title"], ch["content"])
            chapters.upsert(book_id, ch["title"], ch["content"], i, "main")
            written.append({"order": i, "title": ch["title"], "chars": len(ch["content"])})
        return IngestResult(ok=True, kind="chapters", chapters=written)
    except Exception as exc:
        return IngestResult(
            ok=False,
            error_code="unknown",
            error=f"消化失败：{exc}",
            exception=exc,
        )
