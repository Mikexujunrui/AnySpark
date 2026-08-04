#
# AnySpark v4 — anyspark-graph 知识图谱包（AI 事实源）
# 功能：实体/关系/事件存储 + FTS 检索；章节自动抽取；当前时空点注入；确定性校验证据
# 铁律：模型无关（全部承载物为自然语言）；core 单向依赖；机制硬编码、内容自然语言
# 版本：0.0.1（S7 知识图谱）
#
__version__ = "0.0.1"

from .extract import (
    EntityDraft,
    EventDraft,
    Extraction,
    GraphExtractor,
    RelationDraft,
    StateUpdate,
)
from .inject import GraphInjector
from .schema import ENTITY_TYPES, Entity, GraphEvent, GraphStore, Relation
from .verify import FactEvidence, GraphVerifier

__all__ = [
    "ENTITY_TYPES",
    "Entity",
    "EntityDraft",
    "EventDraft",
    "Extraction",
    "FactEvidence",
    "GraphEvent",
    "GraphExtractor",
    "GraphInjector",
    "GraphStore",
    "GraphVerifier",
    "Relation",
    "RelationDraft",
    "StateUpdate",
]
