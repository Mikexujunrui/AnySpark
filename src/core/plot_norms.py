# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Compact prompt rendering for reusable, user-controlled plot norms."""

from __future__ import annotations

from data.json_store import json_store


def build_plot_norms_prompt(book_id: str, max_chars: int = 1800) -> str:
    active = [norm for norm in json_store.load_plot_norms(book_id) if norm.get("active", False)]
    if not active:
        return ""

    lines = ["## 用户启用的剧情规范（高优先级，不得自行替换成通用套路）"]
    for norm in active[:8]:
        lines.append(f"### {str(norm.get('name', '未命名规范'))[:80]}")
        description = str(norm.get("description", "")).strip()
        if description:
            lines.append(description[:300])
        rules = norm.get("rules", []) if isinstance(norm.get("rules", []), list) else []
        avoid = norm.get("avoid", []) if isinstance(norm.get("avoid", []), list) else []
        for rule in rules[:10]:
            lines.append(f"- 必须：{str(rule)[:260]}")
        for item in avoid[:10]:
            lines.append(f"- 禁止：{str(item)[:260]}")
        if sum(len(line) for line in lines) >= max_chars:
            break
    return "\n".join(lines)[:max_chars]

