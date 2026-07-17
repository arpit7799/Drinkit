"""
Application-wide exception hierarchy.

Using a typed exception hierarchy (rather than raising HTTPException
directly from service/repository layers) keeps the domain and service
layers free of any HTTP/framework concerns. The API layer is
responsible for translating these into HTTP responses — see
`app/core/exception_handlers.py`.
"""


class CivicAIError(Exception):
    """Base class for all application-specific exceptions."""

    def __init__(self, message: str = "An unexpected error occurred."):
        self.message = message
        super().__init__(message)


# --- Generic domain errors -------------------------------------------------


class NotFoundError(CivicAIError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, identifier: str | int | None = None):
        detail = f"{resource} not found"
        if identifier is not None:
            detail += f" (id={identifier})"
        super().__init__(detail)


class ConflictError(CivicAIError):
    """Raised when an operation conflicts with existing state (e.g. duplicate email)."""


class ValidationError(CivicAIError):
    """Raised for domain-level validation failures not caught by Pydantic schemas."""


# --- Auth errors -------------------------------------------------------------


class AuthError(CivicAIError):
    """Base class for authentication/authorization errors."""


class InvalidCredentialsError(AuthError):
    def __init__(self):
        super().__init__("Incorrect email or password.")


class InactiveUserError(AuthError):
    def __init__(self):
        super().__init__("This account is inactive.")


class UnverifiedEmailError(AuthError):
    def __init__(self):
        super().__init__("Email address has not been verified.")


class InvalidTokenError(AuthError):
    def __init__(self, message: str = "Invalid or expired token."):
        super().__init__(message)


class PermissionDeniedError(AuthError):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(message)


# --- Storage / upload errors ------------------------------------------------


class FileTooLargeError(CivicAIError):
    def __init__(self, max_mb: int):
        super().__init__(f"File exceeds the maximum allowed size of {max_mb} MB.")


class UnsupportedFileTypeError(CivicAIError):
    def __init__(self, allowed_types: list[str]):
        super().__init__(f"Unsupported file type. Allowed types: {', '.join(allowed_types)}.")


class CorruptedImageError(CivicAIError):
    def __init__(self):
        super().__init__("The uploaded image appears to be corrupted or unreadable.")