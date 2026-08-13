"""
anyspark.server.skill_io — skill 文件格式（S118 提案 D：内容生态基础设施）。

生态货币：skill 可文件化分享——导出格式 = 导入判别格式（闭环），
对方上传 skill 文件 → ingest 判别 → 草稿 → 人工确认转正。

文件格式（front-matter 五段式 md）：
```markdown
---
name: 悬念钩子
target: writing
tags: 悬疑,节奏
description: 每章结尾用未解问题钩住读者
---
（content 正文——可执行技法，五段式核心）
---
（example 案例——可选，具体情形摘录）
```
- front-matter = 首个 `---` 块内的键值行（name 必填；target/tags/description 可选）
- 其余正文按 `---` 分隔：第一段=content（必填），第二段=example（可选）
- 判别严格：name + content 都非空才认（普通 md 笔记不被误判为 skill）
"""

from __future__ import annotations

import re
from typing import Any

# target 合法值（对齐 WritingSkillStore）
_VALID_TARGETS = ("writing", "main", "both")


def parse_skill_file(text: str) -> dict[str, Any] | None:
    """解析 skill 文件 → {name, description, content, example, tags, target} | None。

    None = 不是 skill 文件（无 front-matter 或 name/content 缺失）——
    ingest 判别据此走原 card/chapters 分支，防误判。
    """
    if not text or not text.strip():
        return None
    lines = text.split("\n")
    # 首个 --- 行开始 front-matter
    if not lines or lines[0].strip() != "---":
        return None
    fm_end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end < 0:
        return None
    # front-matter 键值解析
    fm: dict[str, str] = {}
    for ln in lines[1:fm_end]:
        ln = ln.strip()
        if not ln or ":" not in ln:
            continue
        k, _, v = ln.partition(":")
        k = k.strip().lower()
        if k in ("name", "description", "content", "example", "tags", "target"):
            fm[k] = v.strip()
    name = fm.get("name", "").strip()
    if not name:
        return None
    # 正文按 --- 分隔：第一段 content，第二段 example
    body = "\n".join(lines[fm_end + 1 :]).strip()
    parts = [p.strip() for p in re.split(r"^\s*---\s*$", body, flags=re.MULTILINE) if p.strip()]
    content = parts[0] if parts else ""
    example = parts[1] if len(parts) > 1 else ""
    # 也可由 front-matter 显式提供
    if not content:
        content = fm.get("content", "").strip()
    if not example:
        example = fm.get("example", "").strip()
    if not content:
        return None
    target = fm.get("target", "writing").strip()
    if target not in _VALID_TARGETS:
        target = "writing"
    return {
        "name": name,
        "description": fm.get("description", "").strip(),
        "content": content,
        "example": example,
        "tags": fm.get("tags", "").strip(),
        "target": target,
    }


def render_skill_file(
    name: str,
    description: str = "",
    content: str = "",
    example: str = "",
    tags: str = "",
    target: str = "writing",
) -> str:
    """渲染 skill 为文件（front-matter 五段式，与 parse_skill_file 闭环）。"""
    target = target if target in _VALID_TARGETS else "writing"
    lines = ["---", f"name: {name}"]
    if target:
        lines.append(f"target: {target}")
    if tags:
        lines.append(f"tags: {tags}")
    if description:
        lines.append(f"description: {description}")
    lines.append("---")
    lines.append("")
    lines.append(content)
    if example:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(example)
    return "\n".join(lines)
