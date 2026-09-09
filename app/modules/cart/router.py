"""Authenticated customer shopping-cart routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.models.cart import ShoppingCart
from app.modules.auth.dependencies import get_current_user
from app.modules.cart.schemas import (
    CartItemCreateRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
)
from app.modules.cart.service import (
    add_cart_item,
    get_or_create_cart,
    remove_cart_item,
    update_cart_item,
)

router = APIRouter(prefix="/cart", tags=["cart"])


def _cart_response(cart: ShoppingCart) -> CartResponse:
    items = [
        CartItemResponse(
            id=item.id,
            variant_id=item.variant_id,
            quantity=item.quantity,
            currency_code=item.currency_code,
            unit_price_minor=item.unit_price_minor,
            line_total_minor=item.quantity * item.unit_price_minor,
        )
        for item in cart.items
    ]
    return CartResponse(
        id=cart.id,
        currency_code=cart.currency_code,
        status=cart.status,
        items=items,
        subtotal_minor=sum(item.line_total_minor for item in items),
    )


@router.get("", response_model=CartResponse)
async def get_current_cart(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Return the authenticated customer's active cart."""

    cart = await get_or_create_cart(session, user_id=current_user.id)
    return _cart_response(cart)


@router.post("/items", response_model=CartResponse)
async def add_item(
    request: CartItemCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Add quantity to a priced variant line in the customer's cart."""

    cart = await add_cart_item(
        session,
        user_id=current_user.id,
        variant_id=request.variant_id,
        quantity=request.quantity,
        currency_code=request.currency_code,
    )
    return _cart_response(cart)


@router.patch("/items/{item_id}", response_model=CartResponse)
async def update_item(
    item_id: UUID,
    request: CartItemUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> CartResponse:
    """Replace the quantity of an owned cart line."""

    cart = await update_cart_item(
        session,
        user_id=current_user.id,
        item_id=item_id,
        quantity=request.quantity,
    )
    return _cart_response(cart)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Remove an owned cart line."""

    await remove_cart_item(session, user_id=current_user.id, item_id=item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
