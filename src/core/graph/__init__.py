"""Graph store sub-package.

Splits the monolithic ``graph_store.py`` (2300+ lines) into focused mixins
plus a slim facade.  Each ``*Mixin`` class defines methods that rely on
``self._run()``, ``self.project_id``, ``self._invalidate_cache()`` and
``self._row_to_entity()`` — all provided by ``GraphStore`` in the parent file.

Usage::

    from core.graph_store import GraphStore  # single import, all mixins inherited
"""

from .analysis_store import AnalysisMixin
from .entity_store import EntityMixin
from .relation_store import RelationMixin

__all__ = ["EntityMixin", "RelationMixin", "AnalysisMixin"]
