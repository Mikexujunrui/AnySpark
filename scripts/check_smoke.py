"""
AnySpark v4 — 阶段 4 真实链路冒烟：多检测者审读（含故意设定矛盾）。

运行：uv run python scripts/check_smoke.py
需要：.env 配置 DEEPSEEK_API_KEY（真实 DeepSeek）
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from anyspark.check import check_text, compile_rule, run_review
from anyspark.models.deepseek import DeepSeekModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 故意含设定矛盾的正文（第3章自称孤儿，第7章有母亲）
TEXT = """第三章
阿诚坐在门槛上，说自己是个孤儿，从小在福利院长大，从没见过父母。
他发誓这辈子不会再相信任何亲人。

第七章
“阿诚，你妈来了。”邻居朝院里喊。
阿诚抬头，看见那个自称是他母亲的女人站在院门口，手里拎着一袋橘子。
"""


def main() -> None:
    model = DeepSeekModel()
    print(f"模型: {model.model_name}\n")

    print("== 1. 轻量规则编译器（用户自然语言规则）==")
    rule = compile_rule("不要破折号")
    if rule:
        hits = rule.checker("他——不，她走了。")
        print(f"  规则「{rule.description}」命中: {hits}")

    print("\n== 2. 多检测者审读（真实 DeepSeek 并行，含设定矛盾）==")
    report = run_review(model, "第三/七章（摘录）", TEXT)
    print(report.render())
    print(f"\n  硬伤数: {report.hard_count} / 总发现: {len(report.findings)}")

    print("\n== 3. 用户规则并入检测 ==")
    rules = [r for r in [compile_rule("不要感叹号"), compile_rule("每段不超过三句话")] if r]
    results = check_text(rules, "第三章\n阿诚说自己是个孤儿！他发誓不再信任何人！")
    for rule, hits in results:
        print(f"  「{rule.description}」命中 {len(hits)} 处")


if __name__ == "__main__":
    main()
