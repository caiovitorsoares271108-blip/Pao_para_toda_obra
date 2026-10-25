from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

if __package__ and __package__.startswith("backend."):
    from ..api_schemas import ProductCreate, ProductPatch, ProductResponse
    from ..database import Product, get_db
    from .contas import User, admin_user
else:
    from api_schemas import ProductCreate, ProductPatch, ProductResponse
    from database import Product, get_db
    from API.contas import User, admin_user

router = APIRouter(prefix="/products", tags=["cardapio"])


def _promo_active(product: Product, now: datetime) -> bool:
    promo = product.promo or {}
    if not promo.get("active"):
        return False
    start = product.promo_starts_at
    end = product.promo_ends_at
    return (start is None or start <= now) and (end is None or now <= end)


@router.get("", response_model=list[ProductResponse])
def list_products(db: Annotated[Session, Depends(get_db)]) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id)))


@router.get("/admin", response_model=list[ProductResponse])
def list_products_admin(_: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.id)))


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(data: ProductCreate, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, data: ProductPatch, _: Annotated[User, Depends(admin_user)],
                   db: Annotated[Session, Depends(get_db)]) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    changes = data.model_dump(exclude_unset=True)
    if changes.get("promo_starts_at") and changes.get("promo_ends_at"):
        if changes["promo_starts_at"] > changes["promo_ends_at"]:
            raise HTTPException(400, "O início da promoção deve anteceder o fim")
    for key, value in changes.items():
        setattr(product, key, value.model_dump() if hasattr(value, "model_dump") else value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def deactivate_product(product_id: int, _: Annotated[User, Depends(admin_user)],
                       db: Annotated[Session, Depends(get_db)]) -> dict:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    product.active = False
    db.commit()
    return {"status": "deleted"}
