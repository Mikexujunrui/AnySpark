"""
anyspark.template — 模式库包。

设计规格（DESIGN.md 机制 6/10）：
- 三层模式库（L1 模型内化 / L2 默认库 / L3 外部库接口）
- 模板四要素元数据：{ 粒度, 位置, 功能, 可变参数 }
- 模板只做探索方向生成器，绝不做内容框架
- 资料消化：上传→摘要卡→图谱关联→原文保留；写作注入摘要卡省 token
"""

from .materials import MaterialCard, MaterialDigestor, MaterialStore
from .patterns import DEFAULT_TEMPLATES, Template, default_library

__all__ = [
    "DEFAULT_TEMPLATES",
    "MaterialCard",
    "MaterialDigestor",
    "MaterialStore",
    "Template",
    "default_library",
]
