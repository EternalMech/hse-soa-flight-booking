import logging

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def api_error_handler(request, error: APIError):
    body = {"error_code": error.code, "message": str(error)}
    if error.details is not None:
        body["details"] = error.details
    return JSONResponse(body, status_code=error.status)


def validation_error_handler(request, error: RequestValidationError):
    fields = [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
        for item in error.errors()
    ]
    return api_error_handler(request, APIError(400, "VALIDATION_ERROR", "Некорректные входные данные", {"fields": fields}))


def database_error_handler(request, error):
    logger.error("Booking database unavailable", exc_info=error)
    return api_error_handler(request, APIError(503, "DATABASE_UNAVAILABLE", "База бронирований временно недоступна"))


def http_error_handler(request, error: HTTPException):
    return api_error_handler(request, APIError(error.status_code, "HTTP_ERROR", str(error.detail)))


def unexpected_error_handler(request, error):
    logger.error("Unexpected Booking Service error", exc_info=error)
    return api_error_handler(request, APIError(500, "INTERNAL_ERROR", "Внутренняя ошибка сервиса"))
