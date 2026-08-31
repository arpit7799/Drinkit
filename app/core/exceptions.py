"""Application errors exposed through the stable API error envelope."""


class AppError(Exception):
    """Expected application failure safe to return to an API caller."""

    status_code = 400
    code = "application_error"
    message = "The request could not be completed."
    headers: dict[str, str] | None = None


class AuthConflict(AppError):
    status_code = 409
    code = "email_already_registered"
    message = "An account with this email already exists."


class InvalidCredentials(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "Email or password is incorrect."
    headers = {"WWW-Authenticate": "Bearer"}


class InvalidRefreshToken(AppError):
    status_code = 401
    code = "invalid_refresh_token"
    message = "The refresh token is invalid or expired."
    headers = {"WWW-Authenticate": "Bearer"}


class InvalidAccessToken(AppError):
    status_code = 401
    code = "invalid_access_token"
    message = "The access token is invalid or expired."
    headers = {"WWW-Authenticate": "Bearer"}


class InventoryNotFound(AppError):
    status_code = 404
    code = "inventory_not_found"
    message = "The requested inventory resource was not found."


class InvalidInventoryRequest(AppError):
    status_code = 400
    code = "invalid_inventory_request"
    message = "The inventory request is invalid."


class InsufficientInventory(AppError):
    status_code = 409
    code = "insufficient_inventory"
    message = "There is not enough available inventory."


class InventoryIdempotencyConflict(AppError):
    status_code = 409
    code = "inventory_idempotency_conflict"
    message = "The idempotency key was already used with different data."


class ReservationConflict(AppError):
    status_code = 409
    code = "reservation_conflict"
    message = "The inventory reservation conflicts with an existing request."


class AddressNotFound(AppError):
    status_code = 404
    code = "address_not_found"
    message = "The requested address was not found."


class InvalidAddressRequest(AppError):
    status_code = 400
    code = "invalid_address_request"
    message = "The address request is invalid."


class FulfillmentLocationNotFound(AppError):
    status_code = 404
    code = "fulfillment_location_not_found"
    message = "The requested fulfillment location was not found."


class CoverageNotFound(AppError):
    status_code = 404
    code = "coverage_not_found"
    message = "The requested fulfillment coverage was not found."


class InvalidCoverageRequest(AppError):
    status_code = 400
    code = "invalid_coverage_request"
    message = "The fulfillment coverage request is invalid."
