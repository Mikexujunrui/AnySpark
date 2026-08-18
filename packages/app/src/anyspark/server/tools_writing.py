"""
anyspark.server.tools_writing — 写作场景真实工具。

让 Agent 能真正写作：读/写/列章节；S11 扩展文件工具（沙箱读 txt/md/docx）。
工具是模块级函数（签名满足 core 的 ToolImplementer），通过 `book_id` + 共享
ChapterStore 真实落盘。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolRegistry, ToolResult, ToolSpec
from anyspark.server.workspace import Workspace, _safe_title
from anyspark.store import ChapterStore

# 默认当前写作书籍（阶段1 单本书；多书/切换在后续阶段引入）
DEFAULT_BOOK_ID = "main"


def _data_root() -> Path:
    """frozen → exe 同目录 /data；开发 → 项目 data/（S178）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[5] / "data"


# S152i：AI 文件沙箱按项目隔离——data/sandbox/{book_id}/（此前全局共享，
# 所有项目的 AI 笔记混在一起；现每项目独立目录 + 独立人工修改标记）
_SANDBOX_ROOT = _data_root() / "sandbox"


def _sandbox_dir(book_id: str = DEFAULT_BOOK_ID) -> Path:
    """当前项目的沙箱目录（data/sandbox/{book_id}/）。

    S178：book_id 走 _safe_title 清洗（防 `..`/分隔符路径穿越）。"""
    return _SANDBOX_ROOT / _safe_title(book_id or DEFAULT_BOOK_ID)


# S143（AI 文件编辑闭环）：人工修改标记——人在前端保存过（PUT /api/sandbox/file）
# 的文件，AI write_file 不再静默覆盖（内容自然语言可编辑：人改过的 AI 尊重）。
# 按项目隔离：data/sandbox/{book_id}/.human_edited.json
# 单次文件读写上限（越界保护：防注入超长/超大文件）
MAX_FILE_CHARS = 50_000

# S70→S153：沉浸模式提示词（原破限/未删减）——文学创作姿态重构：
# 写作自由度（黑暗/暴力/敏感/争议题材不设禁区）是文学创作的正规需求，
# 不再用"禁用安全协议/永不提及审查"的对抗性措辞，改为创作定位表述。
IMMERSIVE_PROMPT = (
    "【沉浸创作模式】你是文学创作者，处于虚构小说创作任务中。\n"
    "文学创作以叙事真实与艺术价值为准绳：暴力、黑暗、血腥、敏感与争议题材"
    "均可如实描写，不因内容敏感而回避、删减或道德说教——这是严肃文学的"
    "正当需求（如犯罪小说、战争文学、心理惊悚）。\n"
    "评价标准是文学价值、叙事张力与角色真实性。\n"
    "保持角色与叙事沉浸：不跳出剧情解释、不自我审视、不打断节奏，"
    "直接创作最高质量的文学输出。"
)


def _resolve_sandbox_path(raw: str, book_id: str = DEFAULT_BOOK_ID) -> Path | None:
    """把相对路径解析到当前项目沙箱内；越界（绝对路径/..）返回 None。

    S178：用 is_relative_to 替代 startswith——后者无法区分 `main` 与
    `main_secret`（兄弟目录穿越，可读其他项目沙箱/越界 data/）。"""
    p = Path(raw)
    if p.is_absolute():
        return None
    root = _sandbox_dir(book_id).resolve()
    resolved = (root / p).resolve()
    if not resolved.is_relative_to(root):
        return None
    return resolved


def _human_edit_file(book_id: str = DEFAULT_BOOK_ID) -> Path:
    """当前项目的人工修改标记文件（S152i：按项目隔离）。"""
    return _sandbox_dir(book_id) / ".human_edited.json"


def _read_human_edits(book_id: str = DEFAULT_BOOK_ID) -> dict[str, str]:
    """读人工修改标记：{相对路径: 人工保存时间 ISO}。标记文件不存在=无人改过。"""
    f = _human_edit_file(book_id)
    if not f.exists():
        return {}
    try:
        import json as _json

        data = _json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _mark_human_edit(rel_path: str, book_id: str = DEFAULT_BOOK_ID) -> None:
    """记录人工保存标记（PUT /api/sandbox/file 调用）。"""
    import json as _json

    marks = _read_human_edits(book_id)
    from datetime import UTC, datetime

    marks[rel_path] = datetime.now(UTC).isoformat()
    f = _human_edit_file(book_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_json.dumps(marks, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_human_edit(rel_path: str, book_id: str = DEFAULT_BOOK_ID) -> None:
    """清除人工修改标记（文件删除时清理，避免残留）。"""
    import json as _json

    marks = _read_human_edits(book_id)
    if rel_path in marks:
        del marks[rel_path]
        f = _human_edit_file(book_id)
        f.write_text(_json.dumps(marks, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate_legacy_sandbox() -> None:
    """S152i：一次性迁移——旧全局沙箱（data/sandbox/ 直接文件）移入 main/ 项目。

    此前所有项目共享 data/sandbox/；隔离后每项目独立子目录，历史文件归 main
    （默认单书场景数据不丢）。幂等：仅当存在非子目录的直接文件时迁移一次。
    """
    if not _SANDBOX_ROOT.exists():
        return
    legacy = [f for f in _SANDBOX_ROOT.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not legacy:
        return
    main_dir = _sandbox_dir(DEFAULT_BOOK_ID)
    main_dir.mkdir(parents=True, exist_ok=True)
    import contextlib

    for f in legacy:
        with contextlib.suppress(OSError):
            f.rename(main_dir / f.name)


def apply_patch(content: str, operations: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """定点编辑（S44）：按自然语言锚点定位段落，插入/删除/替换，不重写整章。

    段落边界 = 换行（中文正文自然分段）。锚点匹配 = 段包含 anchor 子串。
    operations: [{"type": "insert|delete|replace", "anchor": str, "content": str}]
      insert  → 在锚点所在段之后插入 content（新段）
      delete  → 删除锚点所在段
      replace → 用 content 替换锚点所在段
    返回 (新正文, 每步结果)。未命中锚点=该步失败（不应用），其余继续。
    """
    paras = content.split("\n")
    results: list[dict[str, Any]] = []
    for op in operations:
        typ = str(op.get("type", ""))
        anchor = str(op.get("anchor", "")).strip()
        new_text = str(op.get("content", ""))
        if typ not in ("insert", "delete", "replace") or not anchor:
            results.append({"type": typ, "ok": False, "error": "非法操作或缺少锚点"})
            continue
        # 找含锚点的段落（第一个）
        idx = next((i for i, p in enumerate(paras) if anchor in p), None)
        if idx is None:
            results.append({"type": typ, "anchor": anchor, "ok": False, "error": "锚点未命中"})
            continue
        if typ == "delete":
            removed = paras.pop(idx)
            results.append({"type": typ, "anchor": anchor, "ok": True, "removed": removed[:60]})
        elif typ == "replace":
            old = paras[idx]
            paras[idx] = new_text
            results.append(
                {"type": typ, "anchor": anchor, "ok": True, "old": old[:60], "new": new_text[:60]}
            )
        else:  # insert
            paras.insert(idx + 1, new_text)
            results.append({"type": typ, "anchor": anchor, "ok": True, "inserted": new_text[:60]})
    return "\n".join(paras), results


def _extract_docx_text(path: Path) -> str:
    """轻量 docx 文本提取（零依赖：zipfile 读 document.xml）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        # 段落 <w:p>...</w:p>，取 <w:t> 文本
        paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
        out = []
        for para in paras:
            texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.DOTALL)
            out.append("".join(texts))
        return "\n".join(out)
    except Exception:
        return "（无法解析 docx 文件）"


class WritingTools:
    """持有章节存储的写作工具实现组（注入共享 store，生命周期跟随 server）。

    S48 工作区化：注入 Workspace 后 write/patch 双写（md 文件权威 + SQLite 镜像），
    未注入（测试）时纯库行为不变。list/read 读库镜像（既有管线零改动）。

    S56（C 架构）：注入 model + 文笔 skill 素材——write_chapter 支持「意图模式」：
    主循环传 intent + references（精选参考），工具内部用**干净上下文**调写作模型
    生成正文（无历史/无工具记录，治多次写作累积毒化），再落盘。
    """

    def __init__(
        self,
        chapters: ChapterStore,
        book_id: str = DEFAULT_BOOK_ID,
        workspace: Workspace | None = None,
        model: Any = None,
        skills_store: Any = None,
        style_prefs: list[str] | None = None,
    ) -> None:
        self._chapters = chapters
        self._book_id = book_id
        self._workspace = workspace
        self._model = model  # S56：干净写作调用用的模型（缺省 None=测试/降级走主循环）
        self._skills_store = skills_store  # S56：文笔 skill 素材（写作调用注入）
        self._style_prefs = style_prefs or []  # S56：文风偏好（选文笔 skill）
        # 已读缓存（S21）：一次请求内同一章节只查一次，抑制 AI 过度 read（日志实证 4-8 次）
        self._read_cache: dict[str, str] = {}

    # -- S56 干净写作调用（C 架构核心） --
    def _clean_write(
        self, title: str, intent: str, references: str, skill_names: list[str] | None = None
    ) -> str:
        """用干净上下文调写作模型生成正文（无历史/无工具记录）。

        上下文 = 写作意图 + 主循环精选参考（原样引用）+ 主循环点名的技巧。
        skill_names：主循环显式点名的技巧（S60/S61，与索引配套）——写作调用是
        被执行方不自行选技巧：点名了才注入，未点名则不带任何技巧（干净）。
        返回正文文本；失败抛异常（调用方降级）。
        """
        if self._model is None:
            raise RuntimeError("写作模型未注入（测试环境不走干净写作）")
        from anyspark.align import render_skills_by_name

        # 干净上下文：意图 + 参考 + 点名技巧（不带对话历史/工具记录/旧章节全文）
        parts = [
            "你是 AnySpark 小说写作引擎。严格根据【写作意图】与【写作参考】撰写正文。",
            "要求：具体、有画面感、杜绝空泛总结；直接输出正文，不要解释。",
        ]
        # S70→S153：沉浸模式（书籍级开关）——写作自由度：黑暗/暴力/敏感题材不设禁区
        if self._workspace is not None and self._workspace.is_immersive(self._book_id):
            parts.append(IMMERSIVE_PROMPT)
        if skill_names:
            # S60：主循环显式点名 → 只注入点名的技巧（写作调用不自行选）
            skill_list = self._skills_store.list_skills() if self._skills_store else []
            skill_block = render_skills_by_name(skill_list, skill_names)
            if skill_block:
                parts.append(skill_block)
        parts.append(f"【写作意图】\n{intent}")
        if references.strip():
            parts.append(f"【写作参考】（主循环精选，原样引用）\n{references}")
        system = "\n\n".join(parts)
        from anyspark.core import Message

        output = self._model.respond(
            [Message(role="system", content=system)],
            [],
        )
        text = (output.text or "").strip()
        if not text:
            raise RuntimeError("写作调用返回空正文")
        return text

    # -- S48 双写辅助（md 文件权威 + SQLite 镜像） --
    def _write_dual(self, title: str, content: str, order: int, line: str) -> str | None:
        """双写：md 文件（权威）→ 返回章节 id；文件写入失败返回 None（不写库）。"""
        ws = getattr(self, "_workspace", None)  # 防御：测试用 __new__ 手工构造可能缺属性
        if ws is not None:
            try:
                ws.write_chapter(self._book_id, order, title, content)
            except OSError:
                return None
        return self._chapters.upsert(self._book_id, title, content, order, line).id

    # -- 工具实现（签名匹配 ToolImplementer protocol）--
    def list_chapters(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        items = self._chapters.list_by_book(self._book_id)
        if not items:
            return ToolResult(call=call, ok=True, content="暂无已写章节。")
        # S158：行尾带 id——批量/工作流场景 agent 需要章节 id 精准传参
        # （8-15 实测：无 id 时 agent 只能猜标题/序号/缺省，重复建任务试错）
        lines = "\n".join(f"{c.order_index}: {c.title} (id={c.id})" for c in items)
        return ToolResult(call=call, ok=True, content=lines)

    def read_chapter(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        if not title:
            return ToolResult(call=call, ok=False, content="缺少参数 title。")
        # 已读缓存（S21）：同请求内重复读同一章直接命中，不重复查库
        if title in self._read_cache:
            return ToolResult(
                call=call,
                ok=True,
                content=f"（已读缓存）\n{self._read_cache[title]}",
            )
        for c in self._chapters.list_by_book(self._book_id):
            if c.title == title:
                content = f"《{c.title}》全文如下：\n{c.content}"
                self._read_cache[title] = content
                return ToolResult(call=call, ok=True, content=content)
        msg = f"未找到章节《{title}》。可用章节请用 list_chapters 查看。"
        return ToolResult(call=call, ok=False, content=msg)

    def write_chapter(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        content = str(arguments.get("content", "")).strip()
        # S56（C 架构）：意图模式——主循环传 intent（写作意图）+ references（精选参考），
        # 工具内部用干净上下文调写作模型生成正文（无历史/无工具记录，治累积毒化）。
        # S60：skills 可选——主循环显式点名本次写作要运用的叙事技巧（索引配套）。
        intent = str(arguments.get("intent", "")).strip()
        references = str(arguments.get("references", "")).strip()
        skills_arg = str(arguments.get("skills", "")).strip()
        skill_names = [s.strip() for s in skills_arg.split(",") if s.strip()] or None
        if not title:
            return ToolResult(call=call, ok=False, content="缺少 title 参数。")
        if not content and not intent:
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    "缺少 content 或 intent（主循环可传 intent + references 由写作引擎生成正文）。"
                ),
            )
        # 意图模式：干净写作调用生成正文（降级：写作模型缺失/失败 → 报错让主循环重试或直接写）
        if not content and intent:
            try:
                content = self._clean_write(title, intent, references, skill_names)
            except Exception as exc:
                return ToolResult(
                    call=call,
                    ok=False,
                    content=f"写作引擎生成失败（可重试或改传 content 直接写）：{exc}",
                )
        # S29 多线叙事：可选 line 参数（默认 main）——声明本章属于哪条叙事线，
        # 图谱时序校验按线比较，跨线首现不误报"时空倒置"。
        line = str(arguments.get("line", "main")).strip() or "main"
        if len(content) > MAX_FILE_CHARS:
            return ToolResult(
                call=call, ok=False, content=f"正文超长（>{MAX_FILE_CHARS} 字），请分段写入。"
            )
        all_chapters = self._chapters.list_by_book(self._book_id)
        existing = next((c for c in all_chapters if c.title == title), None)
        # S152j：原子分配 order（锁内 MAX+1），并发新建不撞序
        order = existing.order_index if existing else self._chapters.next_order(self._book_id)
        cid = self._write_dual(title, content, order, line)
        if cid is None:
            return ToolResult(
                call=call,
                ok=False,
                content=f"章节文件写入失败：《{title}》（工作区不可写？）。",
            )
        # 写后缓存失效（S21）：同一请求内修改过的章节，下次 read 必须读到新内容
        self._read_cache.pop(title, None)
        # 幻觉检测 fake_write 兜底：落盘后自校验（id 必须能回读）
        if self._chapters.get(cid) is None:
            return ToolResult(
                call=call, ok=False, content=f"落盘校验失败：章节《{title}》未能读回。"
            )
        note = "覆盖了旧版" if existing else "新建"
        used_intent = bool(intent) and not bool(str(arguments.get("content", "")).strip())
        mode = "意图模式（干净写作）" if used_intent else "轻量写作（直写）"
        return ToolResult(
            call=call,
            ok=True,
            content=f"已{note}章节《{title}》({cid})（{mode}）。",
            data={"chapter_id": cid, "title": title},
        )

    # -- S11 文件工具（沙箱读 txt/md/docx）--
    def patch_chapter(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        """S44 定点编辑：按自然语言锚点定位段落，插入/删除/替换，不重写整章。"""
        call = ToolCall(name=spec.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        raw_ops = str(arguments.get("operations", ""))
        if not title or not raw_ops:
            return ToolResult(call=call, ok=False, content="缺少参数 title 或 operations。")
        try:
            import json as _json

            ops = _json.loads(raw_ops)
            if not isinstance(ops, list):
                raise ValueError("operations 必须是 JSON 数组")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"operations 解析失败：{exc}")
        for c in self._chapters.list_by_book(self._book_id):
            if c.title == title:
                new_content, results = apply_patch(c.content, ops)
                ok_all = all(r.get("ok") for r in results)
                # 保存（旧版进版本历史，S48 双写文件权威）；写后缓存失效
                cid = self._write_dual(title, new_content, c.order_index, c.narrative_line)
                if cid is None:
                    return ToolResult(call=call, ok=False, content=f"章节文件写入失败：《{title}》")
                self._read_cache.pop(title, None)
                lines = [
                    f"步骤 {i + 1}: {'✓' if r.get('ok') else '✗'} "
                    + str(
                        r.get("error")
                        or r.get("removed")
                        or r.get("old")
                        or r.get("inserted")
                        or ""
                    )[:60]
                    for i, r in enumerate(results)
                ]
                status = "全部命中" if ok_all else "部分未命中"
                return ToolResult(
                    call=call,
                    ok=ok_all,
                    content=f"已定点编辑《{title}》（{status}）：\n" + "\n".join(lines),
                )
        return ToolResult(call=call, ok=False, content=f"未找到章节《{title}》。")

    def read_file(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        raw = str(arguments.get("path", "")).strip()
        path = _resolve_sandbox_path(raw, self._book_id)  # S152i：按项目沙箱
        if path is None:
            return ToolResult(
                call=call,
                ok=False,
                content="路径越界：只允许沙箱目录内相对路径（data/sandbox/{当前项目}/）。",
            )
        if not path.exists():
            return ToolResult(call=call, ok=False, content=f"文件不存在：{raw}")
        if path.is_dir():
            # S108：目录 → 列出内容（此前 read_text 读目录报 Errno 13 误导为权限错误）
            try:
                items = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
            except Exception as exc:
                return ToolResult(call=call, ok=False, content=f"目录读取失败：{exc}")
            if not items:
                return ToolResult(call=call, ok=True, content=f"目录 {raw} 为空。")
            return ToolResult(
                call=call,
                ok=True,
                content=f"目录 {raw} 内容（{len(items)} 项）：\n"
                + "\n".join(f"- {i}" for i in items[:100]),
            )
        try:
            if path.suffix.lower() == ".docx":
                text = _extract_docx_text(path)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"读取失败：{exc}")
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n…（已截断）"
        return ToolResult(call=call, ok=True, content=f"文件 {raw} 内容：\n{text}")

    def write_file(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        raw = str(arguments.get("path", "")).strip()
        content = str(arguments.get("content", ""))
        if len(content) > MAX_FILE_CHARS:
            return ToolResult(call=call, ok=False, content=f"内容超长（>{MAX_FILE_CHARS} 字）。")
        path = _resolve_sandbox_path(raw, self._book_id)  # S152i：按项目沙箱
        if path is None:
            return ToolResult(
                call=call,
                ok=False,
                content="路径越界：只允许沙箱目录内相对路径（data/sandbox/{当前项目}/）。",
            )
        # S143（AI 文件编辑闭环）：人工修改过的文件不静默覆盖——
        # 人在前端保存过（PUT /api/sandbox/file）即标记；AI 再写被拦，
        # 返回提示让 agent 告知用户（内容自然语言可编辑：人改过的 AI 尊重）。
        if path.exists() and raw in _read_human_edits(self._book_id):
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    f"文件 {raw} 已被人工修改（前端保存过），为不覆盖人工改动已停止写入。"
                    "如需 AI 改写该文件，请用户在前端重新保存一次或改其他路径。"
                ),
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"写入失败：{exc}")
        return ToolResult(call=call, ok=True, content=f"已写入 {raw}（{len(content)} 字）。")


# 工具规格（与 WritingTools 方法一一对应）
_WRITING_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_chapters",
        description="列出这本书当前已有的全部章节标题。",
    ),
    ToolSpec(
        name="read_chapter",
        description="读取某章全文，用于续写/修改时保持连贯。",
        params=[ParamSpec(name="title", type="string", required=True, description="章节标题")],
    ),
    ToolSpec(
        name="write_chapter",
        description=(
            "把写作正文保存为某章（新建或覆盖）。两种模式：\n"
            "① 轻量写作（直写）：传 content 直接落盘——用于短段落/快速产出/"
            "写作引擎不可用时的兜底；\n"
            "② 意图模式（S56 C 架构）：传 intent（写作意图）+ references（主循环精选的参考事实，"
            "原样引用）→ 由干净的写作引擎生成正文落盘——正文由专用写作调用产生，"
            "不背对话历史，适合长会话防累积毒化。长章/正式写作优先意图模式。"
        ),
        params=[
            ParamSpec(name="title", type="string", required=True, description="章节标题"),
            ParamSpec(
                name="content",
                type="string",
                required=False,
                description="章节正文全文（直写模式用；与 intent 二选一）",
            ),
            ParamSpec(
                name="intent",
                type="string",
                required=False,
                description="写作意图（意图模式用）：场景/人物状态/氛围/要推进的情节，明确无歧义",
            ),
            ParamSpec(
                name="references",
                type="string",
                required=False,
                description="写作参考（意图模式用）：主循环从图谱/设定/章节摘录的事实与原文片段，原样引用",
            ),
            ParamSpec(
                name="skills",
                type="string",
                required=False,
                description=(
                    "（意图模式可选）本次写作要运用的叙事技巧名，逗号分隔（如'节奏控制,对白机锋'）"
                    "——主循环从技巧索引点名；不传则不注入技巧（干净写作，对齐 S61 删自动匹配）"
                ),
            ),
            ParamSpec(
                name="line",
                type="string",
                required=False,
                description="本章所属叙事线（可选，默认 main；多线如 line_b）",
            ),
        ],
        # S25（对齐 pi executionMode）：写类工具标 sequential——与 read 类工具同批时
        # 整批串行，防止读旧写新的逻辑错序（锁只保数据不保顺序）。
        execution_mode="sequential",
    ),
    ToolSpec(
        name="patch_chapter",
        description=(
            "定点编辑章节：按自然语言锚点定位段落，插入/删除/替换指定位置"
            "（不用重写整章）。operations 传 JSON 数组："
            '[{"type":"insert|delete|replace","anchor":"锚点文本","content":"新内容"}]'
        ),
        params=[
            ParamSpec(name="title", type="string", required=True, description="章节标题"),
            ParamSpec(
                name="operations",
                type="string",
                required=True,
                description="JSON 数组字符串：[{type, anchor, content}]，锚点=定位段落的文本片段",
            ),
        ],
        execution_mode="sequential",
    ),
    ToolSpec(
        name="read_file",
        description=(
            "读取沙箱内文件（txt/md/docx）或列出目录内容，用于参考资料/笔记。"
            "只允许 data/sandbox/ 内相对路径；传目录（如 `.`、`notes`）会列出其中文件。\n"
            "注意：查叙事技巧用 skill_lookup，查资料库用 read_material，"
            "查参考书用 reference_lookup——read_file 只读沙箱笔记文件。"
        ),
        params=[
            ParamSpec(
                name="path",
                type="string",
                required=True,
                description="相对路径，如 notes/设定.md 或 .",
            )
        ],
    ),
    ToolSpec(
        name="write_file",
        description=(
            "写入沙箱内文件（txt/md），用于保存参考资料/笔记/灵感/随笔。"
            "只允许 data/sandbox/ 内相对路径。\n"
            "约定：笔记/灵感/随笔请写到 `笔记/` 前缀路径（如 `笔记/灵感-设定.md`）——"
            "纯文档存储，不触发图谱抽取/伏笔回收/学习审查等任何高级处理。\n"
            "注意：写正式章节用 write_chapter（落书库+图谱），写笔记用 write_file（纯文档）。"
        ),
        params=[
            ParamSpec(
                name="path", type="string", required=True, description="相对路径，如 笔记/灵感.md"
            ),
            ParamSpec(name="content", type="string", required=True, description="文件内容"),
        ],
    ),
]


def register_writing_tools(
    registry: ToolRegistry,
    chapters: ChapterStore,
    book_id: str = DEFAULT_BOOK_ID,
    workspace: Workspace | None = None,
    model: Any = None,
    skills_store: Any = None,
    style_prefs: list[str] | None = None,
) -> None:
    """把写作工具集注册进注册表。S48：注入 workspace 后 write/patch 双写文件权威。

    S56（C 架构）：注入 model + skills_store + style_prefs 后，write_chapter 支持
    「意图模式」——干净写作调用生成正文（无历史/无工具记录）。缺省（测试）直写不变。
    """
    tools = WritingTools(
        chapters,
        book_id,
        workspace,
        model=model,
        skills_store=skills_store,
        style_prefs=style_prefs,
    )
    for spec in _WRITING_SPECS:
        registry.register(spec, getattr(tools, spec.name))
