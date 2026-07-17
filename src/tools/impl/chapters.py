"""Chapter CRUD tool implementations — list, read, edit, patch, delete, history, diff.

Extracted from executor.py to keep module sizes manageable.
"""

from core.config import config
from data.json_store import json_store


def _count_words(args: dict) -> str:
    text = args.get("text", "")
    chars = len(text.replace("\n", "").replace(" ", ""))
    return f"字符数: {chars}, 估计词数: {chars}"


def _list_chapters(book_id: str) -> str:
    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "暂无章节"
    lines = []
    regular_idx = 0
    extra_idx = 0
    for c in chapters:
        view = json_store._chapter_view(c)
        chars = len(view.get("content", ""))
        vc = view.get("version_count", 1)
        is_extra = view.get("is_extra", False)
        if is_extra:
            extra_idx += 1
            lines.append(
                f"- #E{extra_idx} [番外] {view.get('title', '?')[:30]} | {chars}字 | v{vc}")
        else:
            regular_idx += 1
            lines.append(
                f"- #{regular_idx} {view.get('title', '?')[:30]} | {chars}字 | v{vc}")
    hint = "提示: 用 #序号 引用普通章节（如 #1, #3），用 #E序号 引用番外（如 #E1, #E2）"
    lines.append(f"\n{hint}")
    return "章节列表:\n" + "\n".join(lines)


def _read_chapter(args: dict, book_id: str) -> str:
    cid = args.get("chapter_id", "")
    ref_book_id = args.get("ref_book_id", "")

    # If ref_book_id specified, read from reference book
    target_book_id = book_id
    if ref_book_id:
        # Verify it's a valid reference book
        ref_ids = json_store.get_reference_books(book_id)
        if not ref_ids or not any(r == ref_book_id or r.startswith(ref_book_id) for r in ref_ids):
            return f"❌ {ref_book_id} 不是当前项目的参考书。先用 set_reference_books 设置。"
        target_book_id = ref_book_id

    try:
        ch = json_store.get_chapter(target_book_id, cid)
        return ch.get("content", "")[:config.storage.max_context_chars]
    except Exception:
        return f"未找到章节 {cid}"


def _delete_chapter(args: dict, book_id: str) -> str:
    cid = args.get("chapter_id", "")
    count = json_store.delete_chapter(book_id, cid)
    return f"已删除 {count} 个章节"


def _delete_all_chapters(book_id: str) -> str:
    count = json_store.delete_all_chapters(book_id)
    return f"已删除全部 {count} 个章节"


def _delete_version(args: dict, book_id: str) -> str:
    chapter_id = args.get("chapter_id", "")
    version_id = args.get("version_id", "")
    if not chapter_id or not version_id:
        return "错误: 需要 chapter_id 和 version_id"
    try:
        result = json_store.delete_version(book_id, chapter_id, version_id)
        return f"已删除版本 {version_id[:12]}。剩余 {result.get('version_count', '?')} 个版本。"
    except Exception as e:
        return f"删除失败: {str(e)[:100]}"


def _purge_chapter_history(args: dict, book_id: str) -> str:
    chapter_id = args.get("chapter_id", "")
    if not chapter_id:
        return "错误: 需要 chapter_id（用 #序号 或 'all'）"
    try:
        if chapter_id.strip().lower() == "all":
            count = json_store.purge_all_chapters_history(book_id)
            return f"已清理全部章节历史。{count} 个章节被重置为 v1。"
        else:
            result = json_store.purge_chapter_history(book_id, chapter_id)
            return f"已清理 {result.get('title', '')} 的版本历史，重置为 v1。"
    except Exception as e:
        return f"清理失败: {str(e)[:100]}"


def _edit_chapter(args: dict, book_id: str) -> dict:
    chapter_id = args.get("chapter_id", "")
    content = args.get("content", "")
    message = args.get("message", "编辑")
    title = args.get("title")
    if not chapter_id or not content:
        return {"type": "writing_result", "error": "需要 chapter_id 和 content 参数"}
    try:
        result = json_store.edit_chapter(
            book_id, chapter_id, content, title=title, message=message)
        return {"type": "writing_result",
                "text": f"已保存: {result.get('title', '')} (v{result.get('version_count', 0)}, {len(content)}字)",
                "chapter_id": chapter_id, "chapter_title": result.get('title', ''),
                "word_count": len(content), "saved": True}
    except Exception as e:
        return {"type": "writing_result", "error": str(e)[:100]}


def _patch_chapter(args: dict, book_id: str) -> dict:
    chapter_id = args.get("chapter_id", "")
    patches = args.get("patches", [])
    message = args.get("message", "局部编辑")
    if not chapter_id:
        return {"type": "patch_result", "error": "需要 chapter_id 参数"}
    if not patches or not isinstance(patches, list):
        return {"type": "patch_result", "error": "patches 必须是非空的操作列表"}
    try:
        result = json_store.patch_chapter(book_id, chapter_id, patches, message=message)
        patched = result.get("patched_count", 0)
        failed = result.get("failed_ops", [])

        # 构建结构化结果
        operations = []
        for i, op in enumerate(patches):
            op_type = op.get("op", "unknown")
            op_result = {
                "index": i + 1,
                "op": op_type,
                "success": True
            }
            # 根据操作类型提取关键信息
            if op_type in ("insert_after", "insert_before"):
                op_result["position"] = op.get("after_paragraph") or op.get("before_paragraph", "")
                op_result["content"] = op.get("content", "")[:150]
            elif op_type == "replace":
                op_result["old_text"] = op.get("old_text", "")[:80]
                op_result["new_text"] = op.get("new_text", "")[:150]
            elif op_type == "delete":
                op_result["paragraph_index"] = op.get("paragraph_index", "")
            elif op_type == "append":
                op_result["content"] = op.get("content", "")[:150]
            elif op_type == "prepend":
                op_result["content"] = op.get("content", "")[:150]
            operations.append(op_result)

        # 标记失败的操作
        for f_op in failed:
            idx = f_op.get("idx", -1)
            if 0 <= idx < len(operations):
                operations[idx]["success"] = False
                operations[idx]["error"] = f_op.get("reason", "")

        lines = [f"已应用 {patched}/{len(patches)} 个 patch: {result.get('title', '')} "
                 f"(版本 {result.get('current_version', '')[:12]}, "
                 f"{result.get('word_count') or len(result.get('content', ''))}字)"]
        if failed:
            lines.append(f"失败的操作 ({len(failed)}个):")
            for f_op in failed:
                lines.append(f"  - [{f_op.get('idx', '?')}] {f_op.get('op', '?')}: {f_op.get('reason', '')}")

        return {
            "type": "patch_result",
            "text": "\n".join(lines),
            "chapter_id": chapter_id,
            "chapter_title": result.get("title", ""),
            "content": result.get("content", ""),
            "operations": operations,
            "patched_count": patched,
            "total_count": len(patches),
            "word_count": result.get("word_count", 0)
        }
    except ValueError as e:
        return {"type": "patch_result", "error": f"局部编辑失败: {str(e)[:200]}"}
    except Exception as e:
        return {"type": "patch_result", "error": f"局部编辑异常: {str(e)[:100]}"}


def _chapter_history(args: dict, book_id: str) -> str:
    chapter_id = args.get("chapter_id", "")
    if not chapter_id:
        return "错误: 需要 chapter_id 参数"
    try:
        history = json_store.chapter_history(book_id, chapter_id)
        if not history:
            return "无版本历史"
        lines = ["版本历史:"]
        for v in history:
            marker = " ← 当前" if v["is_current"] else ""
            lines.append(
                f"- [{v['id'][:12]}] {v['timestamp'][:16]} | "
                f"{v['message'][:30]} | {v['word_count']}字{marker}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查询失败: {str(e)[:100]}"


def _revert_chapter(args: dict, book_id: str) -> str:
    chapter_id = args.get("chapter_id", "")
    version_id = args.get("version_id", "")
    if not chapter_id or not version_id:
        return "错误: 需要 chapter_id 和 version_id 参数"
    try:
        result = json_store.revert_chapter(book_id, chapter_id, version_id)
        return (f"已回退到版本 {result.get('current_version', '')[:12]}: "
                f"{result.get('title', '')} ({len(result.get('content', ''))}字)")
    except Exception as e:
        return f"回退失败: {str(e)[:100]}"


async def _diff_chapters(loop, args: dict, book_id: str) -> str:
    import difflib
    chapter_id = args.get("chapter_id", "")
    version_a = args.get("version_a", "")
    version_b = args.get("version_b", "")
    if not chapter_id or not version_a:
        return "错误: 需要 chapter_id 和 version_a 参数"
    try:
        va = json_store.get_chapter_version(book_id, chapter_id, version_a)
        if version_b:
            vb = json_store.get_chapter_version(book_id, chapter_id, version_b)
        else:
            ch = json_store.get_chapter(book_id, chapter_id)
            vb = {
                "content": ch.get(
                    "content", ""), "id": ch.get(
                    "current_version", "now")}

        text_a = va.get("content", "").splitlines()
        text_b = vb.get("content", "").splitlines()

        diff = list(difflib.unified_diff(
            text_a, text_b,
            fromfile=f"{va['id'][:12]} ({va.get('message', '')})",
            tofile=f"{vb['id'][:12]} ({vb.get('message', '')})" if isinstance(
                vb, dict) and 'message' in vb else vb.get('id', 'current')[:12],
            lineterm="",
            n=2,
        ))

        if not diff:
            return "两个版本内容完全相同。"

        added = sum(1 for line in diff if line.startswith(
            "+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-")
                      and not line.startswith("---"))

        summary = f"差异摘要: +{added}行 / -{removed}行\n"
        diff_text = "\n".join(diff[:100])
        if len(diff) > 100:
            diff_text += f"\n... (共 {len(diff)} 行差异，仅显示前100行)"

        return summary + diff_text
    except Exception as e:
        return f"对比失败: {str(e)[:100]}"
