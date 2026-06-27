# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from fastapi import APIRouter

from .books import router as books_router
from .chapters import router as chapters_router
from .characters import router as characters_router
from .chat import router as chat_router
from .documents import router as documents_router
from .export import router as export_router
from .interactive_routes import router as interactive_router
from .knowledge import router as knowledge_router
from .materials import router as materials_router
from .reviews import router as reviews_router
from .scheduler import router as scheduler_router
from .search import router as search_router
from .sessions import router as sessions_router
from .settings import router as settings_router
from .skills_route import router as skills_router
from .stats import router as stats_router
from .styles_route import router as styles_router
from .tasks import router as tasks_router
from .volumes import router as volumes_router
from .workflow import router as workflow_router

api_router = APIRouter(prefix="/api")
api_router.include_router(books_router)
api_router.include_router(knowledge_router)
api_router.include_router(chapters_router)
api_router.include_router(sessions_router)
api_router.include_router(documents_router)
api_router.include_router(characters_router)
api_router.include_router(workflow_router)
api_router.include_router(chat_router)
api_router.include_router(settings_router)
api_router.include_router(export_router)
api_router.include_router(skills_router)
api_router.include_router(scheduler_router)
api_router.include_router(search_router)
api_router.include_router(reviews_router)
api_router.include_router(volumes_router)
api_router.include_router(materials_router)
api_router.include_router(styles_router)
api_router.include_router(stats_router)
api_router.include_router(tasks_router)
api_router.include_router(interactive_router)
