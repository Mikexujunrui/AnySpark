"""anyspark.server — FastAPI 后端（对话→写作→修改闭环）。"""

from .app import build_app

__all__ = ["build_app"]
