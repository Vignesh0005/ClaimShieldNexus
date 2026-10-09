class ClaimShieldException(Exception):
    status_code = 500
    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str | None = None, **details):
        super().__init__(message or self.error_code)
        self.message = message or self.error_code.replace("_", " ").capitalize()
        self.details = details


class NotFound(ClaimShieldException):
    status_code = 404
    error_code = "NOT_FOUND"


class TenantNotFound(NotFound):
    error_code = "TENANT_NOT_FOUND"


class Unauthorized(ClaimShieldException):
    status_code = 401
    error_code = "UNAUTHORIZED"


class Forbidden(ClaimShieldException):
    status_code = 403
    error_code = "FORBIDDEN"


class Conflict(ClaimShieldException):
    status_code = 409
    error_code = "CONFLICT"


class ValidationFailed(ClaimShieldException):
    status_code = 422
    error_code = "VALIDATION_FAILED"


class RateLimited(ClaimShieldException):
    status_code = 429
    error_code = "RATE_LIMITED"


class MLServerUnavailable(ClaimShieldException):
    status_code = 503
    error_code = "ML_SERVER_UNAVAILABLE"


class CopilotUnavailable(ClaimShieldException):
    status_code = 503
    error_code = "COPILOT_UNAVAILABLE"


class ImmutableRecord(ClaimShieldException):
    status_code = 409
    error_code = "IMMUTABLE_RECORD"
