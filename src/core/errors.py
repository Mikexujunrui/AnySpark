from typing import Any

from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: Any = None):
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_response(self) -> dict:
        resp = {"error": self.error_code, "message": self.message}
        if self.detail:
            resp["detail"] = self.detail
        return resp


class NotFoundError(AppError):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class PermissionDeniedError(AppError):
    status_code = 403
    error_code = "PERMISSION_DENIED"


class LLMError(AppError):
    status_code = 502
    error_code = "LLM_ERROR"


class StorageError(AppError):
    status_code = 500
    error_code = "STORAGE_ERROR"


class Neo4jError(AppError):
    status_code = 503
    error_code = "NEO4J_UNAVAILABLE"


class ToolExecutionError(AppError):
    status_code = 500
    error_code = "TOOL_EXECUTION_ERROR"


def register_error_handlers(app):
    @app.exception_handler(AppError)
    async def app_error_handler(request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response()
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": str(exc)[:200]}
        )
