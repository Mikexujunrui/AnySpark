#!/usr/bin/env python3
"""AnySpark 轻量对话 CLI（S49：不经过前端/pi，直接对话驱动后端）。

用法：
    anyspark-chat                 # 连 127.0.0.1:8000 对话
    anyspark-chat --base URL      # 指定后端
    anyspark-chat -m "写第一章"   # 单条消息（非交互）
    anyspark-chat --reset         # 清会话

特性：
- 流式输出（SSE text_delta 打字机）+ 工具执行状态显示
- Ctrl+C 取消当前轮（POST /api/chat/cancel），会话可续（输入"继续"）
- conversation_id 延续多轮（存 ~/.anyspark_cli.json）
- /quit /reset /tools 命令
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）

DEFAULT_BASE = "http://127.0.0.1:8000"
STATE_FILE = Path.home() / ".anyspark_cli.json"

# 默认请求：领域工具全开（小说写作必需）
BASE_REQ = {
    "enable_domain": True,
    "enable_codex": False,
    "skip_inject": [],
}


def load_state() -> dict[str, object]:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def save_state(state: dict[str, object]) -> None:
    from contextlib import suppress

    with suppress(OSError):
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def stream_chat(base: str, message: str, conv_id: str | None) -> tuple[str, str | None] | None:
    """SSE 流式对话：返回 (最终文本, conversation_id)；Ctrl+C 取消当前轮。"""
    req = {**BASE_REQ, "message": message}
    if conv_id:
        req["conversation_id"] = conv_id
    payload = json.dumps(req, ensure_ascii=False)
    cancelled = False
    try:
        with (
            httpx.Client(trust_env=False, timeout=None) as client,
            client.stream(
                "POST",
                f"{base}/api/chat/stream",
                content=payload,
                headers={"Content-Type": "application/json"},
            ) as resp,
        ):
            if resp.status_code != 200:
                print(f"\n[错误] HTTP {resp.status_code}", file=sys.stderr)
                return None
            buf = ""
            full = ""
            new_conv = conv_id
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    evt = ""
                    data = ""
                    for line in frame.split("\n"):
                        if line.startswith("event:"):
                            evt = line[6:].strip()
                        elif line.startswith("data:"):
                            data = line[5:].strip()
                    if not evt or not data:
                        continue
                    try:
                        p = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if evt == "text_delta":
                        t = str(p.get("content", ""))
                        print(t, end="", flush=True)
                        full += t
                    elif evt == "tool_execution_start":
                        print(
                            f"\n\x1b[90m[工具] {p.get('name', '')}…\x1b[0m",
                            end="",
                            flush=True,
                        )
                    elif evt == "tool_execution_end":
                        name = p.get("name", "")
                        ok = p.get("ok") is True
                        mark = "\x1b[32m✓\x1b[0m" if ok else "\x1b[31m✗\x1b[0m"
                        print(f" {mark} {name}", flush=True)
                    elif evt == "turn_start" or evt == "done":
                        cid = p.get("conversation_id")
                        if cid:
                            new_conv = str(cid)
                    elif evt == "error":
                        print(f"\n[错误] {p.get('message', '')}", file=sys.stderr)
                        return (full, new_conv)
            print()
            return (full, new_conv)
    except KeyboardInterrupt:
        cancelled = True
    except Exception as exc:
        print(f"\n[连接错误] {exc}", file=sys.stderr)
        return None
    if cancelled:
        try:
            with httpx.Client(trust_env=False, timeout=5) as client:
                client.post(
                    f"{base}/api/chat/cancel",
                    json={"conversation_id": conv_id},
                )
        except Exception:
            pass
        print("\n[已取消] 输入'继续'可续写", file=sys.stderr)
        return ("", conv_id)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AnySpark 对话 CLI")
    parser.add_argument("--base", default=os.getenv("ANYSPARK_BASE", DEFAULT_BASE))
    parser.add_argument("--reset", action="store_true", help="清空会话重新开始")
    parser.add_argument("--message", "-m", default=None, help="直接发一条消息（非交互模式）")
    args = parser.parse_args()

    state = load_state()
    if args.reset:
        state = {"conversation_id": None}
        save_state(state)
    conv_id = state.get("conversation_id")
    conv_id = str(conv_id) if conv_id else None
    base = args.base.rstrip("/")

    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            r = client.get(f"{base}/api/health")
            if r.status_code != 200:
                print(f"[错误] 后端不可用：{base}（先 anyspark_server start）", file=sys.stderr)
                return 1
            model = r.json().get("model", "?")
            print(f"\x1b[90mAnySpark CLI · {model} · {base}\x1b[0m")
    except Exception as exc:
        print(f"[错误] 无法连接 {base}：{exc}", file=sys.stderr)
        return 1

    if args.message:
        result = stream_chat(base, args.message, conv_id)
        if result:
            _, cid = result
            state["conversation_id"] = cid
            save_state(state)
        return 0

    print("\x1b[90m/quit 退出 · /reset 新会话 · /tools 看工具 · Ctrl+C 取消当前轮\x1b[0m")
    print("\x1b[90m写作即对话：直接告诉我要写什么\x1b[0m")
    while True:
        try:
            msg = input("\n\x1b[36m> \x1b[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return 0
        if not msg:
            continue
        if msg in ("/quit", "/exit"):
            print("再见。")
            return 0
        if msg == "/reset":
            conv_id = None
            state["conversation_id"] = None
            save_state(state)
            print("[新会话]")
            continue
        if msg == "/tools":
            try:
                with httpx.Client(trust_env=False, timeout=30) as client:
                    r = client.post(
                        f"{base}/api/chat",
                        json={
                            **BASE_REQ,
                            "message": "列出你当前可用的全部工具（只列名字，不要做事）。",
                        },
                    )
                    print(r.json().get("text", ""))
            except Exception as exc:
                print(f"[错误] {exc}", file=sys.stderr)
            continue

        result = stream_chat(base, msg, conv_id)
        if result:
            _, cid = result
            conv_id = cid
            state["conversation_id"] = cid
            save_state(state)


if __name__ == "__main__":
    raise SystemExit(main())
