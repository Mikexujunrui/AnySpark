"""
AnySpark v4 — 阶段 5 真实链路冒烟：资料消化（摘要卡）+ 模式库。

运行：uv run python scripts/template_smoke.py
需要：.env 配置 DEEPSEEK_API_KEY（真实 DeepSeek）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv

from anyspark.models.deepseek import DeepSeekModel
from anyspark.template import MaterialDigestor, MaterialStore, default_library

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 上传一段材料（世界设定参考）
MATERIAL = """雾城设定（参考）：
雾城坐落于临江的港口，终年被浓雾笼罩。城中心有一座废弃的钟楼，
据说钟楼每到午夜会自行鸣响，响声只有本城人听得见。
雾城有四大码头，东码头已废弃三十年。城北是旧工业区，烟囱不再冒烟，
但地下的蒸汽管道仍在供热。本地人称雾为"雾瘴"，认为它是这座城呼吸的方式。
传说二十年前大雾曾持续四十天不散，那一年，港口失踪了七个人。
"""


def main() -> None:
    model = DeepSeekModel()
    print(f"模型: {model.model_name}\n")

    print("== 1. 模式库（L2 默认库）==")
    lib = default_library()
    for t in lib:
        print(f"  [{t.granularity}/{t.position}/{t.function}] {t.name}（可变参数: {t.params}）")

    print("\n== 2. 资料消化（真实 DeepSeek → 摘要卡）==")
    store = MaterialStore(Path(tempfile.mkdtemp()) / "mat.db")
    try:
        digestor = MaterialDigestor(model)
        card = digestor.digest(MATERIAL, purpose="fact")
        print(f"  标题: {card.title}")
        print(f"  主题: {card.topic}")
        print(f"  要点: {card.key_points}")
        print(f"  设定: {card.key_settings}")
        print(f"  角色: {card.characters}")
        print(f"  术语: {card.terms}")
        store.save(card)
        print(f"\n  已入库，原文保留 {len(card.source_text)} 字")

        print("\n== 3. 注入用摘要（省 token）==")
        print("  ---")
        print(card.summarize())
        print("  ---")
    finally:
        store.close()


if __name__ == "__main__":
    main()
