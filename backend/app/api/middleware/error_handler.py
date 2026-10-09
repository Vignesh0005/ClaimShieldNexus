from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.exceptions import ClaimShieldException
from app.core.logging import logger


def _body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ClaimShieldException)
    async def _domain(request: Request, exc: ClaimShieldException):
        headers = {"Retry-After": str(exc.details["retry_after_seconds"])} if "retry_after_seconds" in exc.details else None
        return JSONResponse(_body(exc.error_code, exc.message, exc.details), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_FAILED", "The request did not pass validation.", {"errors": errors}), status_code=422)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        return JSONResponse(_body("HTTP_ERROR", str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        logger.warning("integrity_error", path=request.url.path, error=str(exc.orig)[:200])
        return JSONResponse(_body("CONFLICT", "The record conflicts with one that already exists. Fetch the current state and try again."), status_code=409)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Details go to the log and Sentry, never to the caller.
        logger.error("unhandled_error", path=request.url.path, error=repr(exc), exc_info=exc)
        return JSONResponse(_body("INTERNAL_ERROR", "Something went wrong on the server. The error has been logged."), status_code=500)
