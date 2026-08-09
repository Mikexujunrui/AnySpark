# AnySpark v4 — anyspark-play 互动推演扩展包
# 互动小说式推演树：从某场景切入、扮演角色、每步多候选行动、用户选择推进、
# 可回溯分叉、导出灵感卡接写正文。灵感来源 + 互动玩法。
# 设计规格：DESIGN.md §12.27（S65）。依赖 core + explore（单向，复用角色卡加载）。
#
__version__ = "0.0.1"

from .engine import PlayEngine
from .export import export_path_markdown
from .tree import PlayStore

__all__ = [
    "PlayEngine",
    "PlayStore",
    "export_path_markdown",
]
