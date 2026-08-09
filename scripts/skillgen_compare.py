# ruff: noqa: E402
# S67b 临时对比脚本：sys.path 注入后的延迟 import（E402）
"""S67b 临时对比：文风提取 旧 prompt vs 新 prompt（猎手准则第一章）。

用法：uv run python scripts/skillgen_compare.py
输出：两版候选到 data/dev/skillgen_compare/，终端打印对比。
真实 LLM 调用（DeepSeek），两次独立提炼。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages/app/src"))
sys.path.insert(0, str(ROOT / "packages/align/src"))

from anyspark.align.skillgen import GENERATE_PROMPT, render_skill_candidates
from anyspark.models import DeepSeekModel


def load_old_prompt() -> str:
    """从 git HEAD 取旧版 GENERATE_PROMPT（对比基线）。"""
    out = subprocess.run(
        ["git", "show", "HEAD:packages/align/src/anyspark/align/skillgen.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    src = out.stdout
    m = re.search(r'GENERATE_PROMPT = """(.*?)"""\n', src, re.DOTALL)
    if not m:
        raise RuntimeError("旧 prompt 未找到")
    return '"""' + m.group(1) + '"""'


def load_sample() -> str:
    # Windows 长路径（E501 豁免：断行破坏路径字面量）
    path = r"E:\Desktop\新建文件夹\soushu2023.com@《猎手准则》（校对版全本） 作者：你是不是笨蛋[搜书吧].txt"  # noqa: E501
    with open(path, encoding="gb18030", errors="replace") as fh:
        raw = fh.read()
    m = re.search(r"第一章.*?\n", raw)
    seg = raw[m.end() : m.end() + 2500]
    return seg


def run(model: object, prompt: str, text: str, max_items: int = 5) -> list[dict[str, str]]:
    """用指定 prompt 直接调用模型提炼（绕过 SkillGenerator 的固定 prompt）。"""
    p = prompt + f"\n{text[:6000]}\n"
    p += f"\n提炼最多 {max_items} 条，输出 JSON 数组。"
    from anyspark.core import Message

    output = model.respond([Message(role="system", content=p)], [])  # type: ignore[attr-defined]
    from anyspark.align.skillgen import _parse_skills

    return _parse_skills(output.text)[:max_items]


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-v4-pro")
    model = DeepSeekModel(temperature=0.3)
    text = load_sample()
    old_prompt = load_old_prompt()
    out_dir = ROOT / "data" / "dev" / "skillgen_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("========== 旧 prompt 提炼 ==========")
    old = run(model, old_prompt, text)
    print(render_skill_candidates(old))
    (out_dir / "old.md").write_text(render_skill_candidates(old), encoding="utf-8")

    print("\n========== 新 prompt 提炼 ==========")
    new = run(model, GENERATE_PROMPT, text)
    print(render_skill_candidates(new))
    (out_dir / "new.md").write_text(render_skill_candidates(new), encoding="utf-8")

    print(f"\n对比结果已存: {out_dir}/old.md, new.md")


if __name__ == "__main__":
    main()
