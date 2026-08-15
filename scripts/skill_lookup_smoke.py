"""S60 冒烟（v2）：分步验证 agent 端到端使用 skill_lookup + write_chapter 点名。

真实 DeepSeek 链路。每步独立、聚焦单行为（避免一个复杂提示让模型走捷径）。
读 turns[0].tool_calls 确认实际工具调用。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.server.app import build_app


def _tools(data: dict) -> list[str]:
    turns = data.get("turns") or []
    if not turns:
        return []
    return list(turns[0].get("tool_calls") or [])


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "s60.db"
    client = TestClient(build_app(db_path=db))
    skills = client.get("/api/skills").json()
    print(f"[0] skill 索引 {len(skills)} 条: {[s['name'] for s in skills]}")

    # 步1：让 agent 用 skill_lookup 细看节奏控制（单行为）
    print("[1] agent 自主 skill_lookup ...")
    r1 = client.post(
        "/api/chat",
        json={
            "message": (
                "我打算写一段追逐戏，想用'节奏控制'这条技巧。"
                "请先 skill_lookup 查看它的完整内容，然后用一句话概括它的核心做法。"
            ),
            "book_id": "main",
        },
    )
    d1 = r1.json()
    print(f"[1] 工具调用: {_tools(d1)}")
    print(f"[1] 回复: {(d1.get('text') or '')[:300]}")

    # 步2：让 agent 用 write_chapter 意图模式 + skills 点名写一章（单行为）
    print("\n[2] agent write_chapter 点名 skills ...")
    r2 = client.post(
        "/api/chat",
        json={
            "message": (
                "现在请用 write_chapter 写新章节《雨夜追逐》，意图模式：intent 写清楚"
                "'主角在码头雨夜被追，短句加速、停顿制造张力，约300字'，references 留空，"
                "skills 参数传'节奏控制'。"
            ),
            "book_id": "main",
        },
    )
    d2 = r2.json()
    print(f"[2] 工具调用: {_tools(d2)}")
    print(f"[2] 回复: {(d2.get('text') or '')[:200]}")

    # 校验落盘
    chs = client.get("/api/chapters").json()
    titles = [c.get("title") for c in chs]
    print(f"[2] 章节列表: {titles}")
    if "雨夜追逐" in titles:
        ch = next(c for c in chs if c.get("title") == "雨夜追逐")
        content = ch.get("content", "")
        print(f"[2] 落盘成功，正文 {len(content)} 字")

    # 步3：索引注入存在性（通过让 agent 描述可用技巧）
    print("\n[3] agent 描述系统提示里的技巧索引 ...")
    r3 = client.post(
        "/api/chat",
        json={"message": "系统提示里有哪些可用的叙事技巧？只列名字。", "book_id": "main"},
    )
    d3 = r3.json()
    print(f"[3] 回复: {(d3.get('text') or '')[:300]}")

    print(
        "\n完成。判定：步1有 skill_lookup、步2有 write_chapter 且 skills 点名、"
        "步3列出索引=S60 全链路生效。"
    )


if __name__ == "__main__":
    main()
