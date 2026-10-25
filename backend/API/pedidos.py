from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

if __package__ and __package__.startswith("backend."):
    from ..api_schemas import OrderCreate, OrderResponse, OrderStatusUpdate
    from ..database import Order, OrderItem, Product, get_db
    from .contas import User, admin_user, current_user
else:
    from api_schemas import OrderCreate, OrderResponse, OrderStatusUpdate
    from database import Order, OrderItem, Product, get_db
    from API.contas import User, admin_user, current_user

router = APIRouter(prefix="/orders", tags=["pedidos"])


def effective_price(product: Product) -> Decimal:
    price = Decimal(str(product.price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    promo = product.promo or {}
    now = datetime.now(timezone.utc)
    start = product.promo_starts_at
    end = product.promo_ends_at
    if not promo.get("active"):
        return price
    if start is not None:
        start = start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start
        if now < start:
            return price
    if end is not None:
        end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end
        if now > end:
            return price
    value = Decimal(str(promo.get("value", 0)))
    if value < 0:
        raise HTTPException(400, "Promoção inválida")
    if promo.get("type") == "percent":
        if value > 100:
            raise HTTPException(400, "Promoção inválida")
        price *= (Decimal("100") - value) / Decimal("100")
    elif promo.get("type") == "fixed":
        price -= value
    else:
        raise HTTPException(400, "Promoção inválida")
    return max(price, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(data: OrderCreate, user: Annotated[User, Depends(current_user)],
                 db: Annotated[Session, Depends(get_db)]) -> Order:
    quantities: dict[int, int] = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
        if quantities[item.product_id] > 99:
            raise HTTPException(400, "Quantidade máxima por produto é 99")
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(
            Product.id.in_(quantities), Product.active.is_(True)
        ))
    }
    if len(products) != len(quantities):
        raise HTTPException(400, "Um ou mais produtos não estão disponíveis")

    order = Order(user_id=user.id, address=data.address.strip(), notes=data.notes.strip(),
                  total=Decimal("0.00"))
    for product_id, quantity in quantities.items():
        product = products[product_id]
        item_price = effective_price(product)
        order.items.append(OrderItem(product_id=product.id, name=product.name,
                                     price=item_price, quantity=quantity))
        order.total += item_price * quantity
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderResponse])
def list_orders(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> list[Order]:
    query = select(Order).options(selectinload(Order.items), selectinload(Order.user)).order_by(Order.created_at.desc())
    if user.role != "admin":
        query = query.where(Order.user_id == user.id)
    return list(db.scalars(query))


@router.patch("/{order_id}/status", response_model=OrderResponse)
def update_order_status(order_id: int, data: OrderStatusUpdate,
                        _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    order.status = data.status
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Mudança de status não permitida para este pedido")
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, user: Annotated[User, Depends(current_user)],
                 db: Annotated[Session, Depends(get_db)]) -> Order:
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Pedido não encontrado")
    if order.status != "pendente":
        raise HTTPException(409, "Somente pedidos pendentes podem ser cancelados")
    order.status = "cancelado"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Somente pedidos pendentes podem ser cancelados")
    db.refresh(order)
    return order