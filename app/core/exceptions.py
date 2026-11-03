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


class VariantNotFound(AppError):
    status_code = 404
    code = "variant_not_found"
    message = "The requested product variant was not found."


class PriceNotFound(AppError):
    status_code = 404
    code = "price_not_found"
    message = "The requested price was not found."


class InvalidPricingRequest(AppError):
    status_code = 400
    code = "invalid_pricing_request"
    message = "The pricing request is invalid."


class CartNotFound(AppError):
    status_code = 404
    code = "cart_not_found"
    message = "The requested cart was not found."


class CartItemNotFound(AppError):
    status_code = 404
    code = "cart_item_not_found"
    message = "The requested cart item was not found."


class InvalidCartRequest(AppError):
    status_code = 400
    code = "invalid_cart_request"
    message = "The cart request is invalid."


class CartCurrencyConflict(AppError):
    status_code = 409
    code = "cart_currency_conflict"
    message = "The cart currency is fixed after cart creation."


class OrderNotFound(AppError):
    status_code = 404
    code = "order_not_found"
    message = "The requested order was not found."


class OrderLineNotFound(AppError):
    status_code = 404
    code = "order_line_not_found"
    message = "The requested order line was not found."


class InvalidOrderRequest(AppError):
    status_code = 400
    code = "invalid_order_request"
    message = "The order request is invalid."


class OrderStatusConflict(AppError):
    status_code = 409
    code = "order_status_conflict"
    message = "The order status does not allow this operation."


class EmptyCartError(AppError):
    status_code = 409
    code = "empty_cart"
    message = "Cannot create an order from an empty cart."


class AddressOwnershipError(AppError):
    status_code = 409
    code = "address_ownership_error"
    message = "The address does not belong to the customer."


class InsufficientInventoryForOrder(AppError):
    status_code = 409
    code = "insufficient_inventory_for_order"
    message = "There is not enough available inventory to fulfill the order."


class PaymentProviderError(AppError):
    status_code = 400
    code = "payment_provider_error"
    message = "The payment provider returned an error."


class DeliveryNotFound(AppError):
    status_code = 404
    code = "delivery_not_found"
    message = "The requested delivery was not found."


class DeliverySlotNotFound(AppError):
    status_code = 404
    code = "delivery_slot_not_found"
    message = "The requested delivery slot was not found."


class CourierNotFound(AppError):
    status_code = 404
    code = "courier_not_found"
    message = "The requested courier was not found."


class InvalidDeliveryRequest(AppError):
    status_code = 400
    code = "invalid_delivery_request"
    message = "The delivery request is invalid."


class CouponNotFound(AppError):
    status_code = 404
    code = "coupon_not_found"
    message = "The coupon code was not found."


class CouponInactive(AppError):
    status_code = 400
    code = "coupon_inactive"
    message = "The coupon is currently inactive."


class CouponExpired(AppError):
    status_code = 400
    code = "coupon_expired"
    message = "The coupon has expired or is not yet valid."


class CouponMinOrderNotMet(AppError):
    status_code = 400
    code = "coupon_min_order_not_met"
    message = "The order subtotal does not meet the minimum required for this coupon."


class CouponUsageLimitReached(AppError):
    status_code = 409
    code = "coupon_usage_limit_reached"
    message = "The global usage limit for this coupon has been reached."


class CouponCustomerLimitReached(AppError):
    status_code = 409
    code = "coupon_customer_limit_reached"
    message = "You have already reached the maximum allowed redemptions for this coupon."


class InsufficientLoyaltyPoints(AppError):
    status_code = 409
    code = "insufficient_loyalty_points"
    message = "You do not have enough loyalty points for this redemption."


class TaxCalculationError(AppError):
    status_code = 400
    code = "tax_calculation_error"
    message = "Unable to compute taxes for the requested jurisdiction."


class KYCRequiredForAlcohol(AppError):
    status_code = 403
    code = "kyc_required_for_alcohol"
    message = "Government ID / Age verification is required to purchase alcoholic beverages."


class UnderageAlcoholPurchase(AppError):
    status_code = 403
    code = "underage_alcohol_purchase"
    message = "You do not meet the minimum legal drinking age for the delivery jurisdiction."


class DryDayRestriction(AppError):
    status_code = 403
    code = "dry_day_restriction"
    message = "Alcohol sale and delivery is prohibited on dry days in this jurisdiction."


class AlcoholHoursRestriction(AppError):
    status_code = 403
    code = "alcohol_hours_restriction"
    message = "Alcohol delivery is not permitted outside licensed statutory operating hours."


class AlcoholVolumeExceeded(AppError):
    status_code = 400
    code = "alcohol_volume_exceeded"
    message = "The order exceeds the statutory maximum spirits volume permitted per delivery."


class InvalidHandoverOTP(AppError):
    status_code = 400
    code = "invalid_handover_otp"
    message = "The delivery handover OTP is invalid or expired."


class DeliveryComplianceNotFound(AppError):
    status_code = 404
    code = "delivery_compliance_not_found"
    message = "Compliance record for this order was not found."


class StateRegulationNotFound(AppError):
    status_code = 404
    code = "state_regulation_not_found"
    message = "Regulations not configured for the requested state."


class WarehouseTaskNotFound(AppError):
    status_code = 404
    code = "warehouse_task_not_found"
    message = "The requested warehouse fulfillment task was not found."


class WarehouseTaskConflict(AppError):
    status_code = 409
    code = "warehouse_task_conflict"
    message = "The fulfillment task status or assignment conflicts with this action."


class WarehouseBinNotFound(AppError):
    status_code = 404
    code = "warehouse_bin_not_found"
    message = "The requested warehouse bin was not found."


class InvalidWarehouseRequest(AppError):
    status_code = 400
    code = "invalid_warehouse_request"
    message = "The warehouse operation request is invalid."


class WarehouseItemNotFound(AppError):
    status_code = 404
    code = "warehouse_item_not_found"
    message = "The requested variant was not found in this fulfillment task."


class PartySessionNotFound(AppError):
    status_code = 404
    code = "party_session_not_found"
    message = "The requested party session was not found."


class PartyInviteCodeInvalid(AppError):
    status_code = 404
    code = "party_invite_code_invalid"
    message = "The party invite code is invalid or the session has expired."


class PartySessionLocked(AppError):
    status_code = 409
    code = "party_session_locked"
    message = "The party cart is currently locked by the host."


class PartyParticipantNotFound(AppError):
    status_code = 404
    code = "party_participant_not_found"
    message = "Participant was not found in this party session."


class PartyHostPermissionRequired(AppError):
    status_code = 403
    code = "party_host_permission_required"
    message = "Only the party host can perform this action."


class PartyItemNotFound(AppError):
    status_code = 404
    code = "party_item_not_found"
    message = "The requested item was not found in the party cart."


class PartyPackNotFound(AppError):
    status_code = 404
    code = "party_pack_not_found"
    message = "The requested curated party pack was not found."


class PartyCartEmpty(AppError):
    status_code = 400
    code = "party_cart_empty"
    message = "The party cart is empty."
