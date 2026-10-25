from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=180)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Informe seu nome")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count("@") != 1 or any(char.isspace() for char in value):
            raise ValueError("Informe um e-mail válido")
        local, domain = value.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Informe um e-mail válido")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=180)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class DemoLoginRequest(BaseModel):
    role: Literal["admin", "customer"]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str
    active: bool = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, min_length=5, max_length=180)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    role: Literal["user", "admin"] | None = None
    active: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value


class Promotion(BaseModel):
    active: bool = False
    type: Literal["percent", "fixed"] = "percent"
    value: float = Field(default=0, ge=0)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=500)
    price: float = Field(ge=0)
    category: str = Field(default="Outros", min_length=1, max_length=80)
    image: str = Field(default="", max_length=500)
    promo: Promotion | None = None
    promo_starts_at: datetime | None = None
    promo_ends_at: datetime | None = None
    active: bool = True

    @field_validator("promo")
    @classmethod
    def validate_promo(cls, value: Promotion | None) -> Promotion | None:
        if value and value.active and value.value <= 0:
            raise ValueError("Promoção ativa exige desconto maior que zero")
        if value and value.type == "percent" and value.value > 100:
            raise ValueError("Desconto percentual não pode exceder 100%")
        return value


class ProductPatch(ProductCreate):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    price: float | None = Field(default=None, ge=0)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    price: float
    category: str
    image: str
    promo: dict | None
    promo_starts_at: datetime | None = None
    promo_ends_at: datetime | None = None
    active: bool


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class OrderCreate(BaseModel):
    address: str = Field(min_length=5, max_length=300)
    notes: str = Field(default="", max_length=500)
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    name: str
    price: float
    quantity: int


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_email: str
    address: str
    notes: str
    status: str
    total: float
    created_at: datetime
    items: list[OrderItemResponse]


class OrderStatusUpdate(BaseModel):
    status: Literal["pendente", "preparando", "saiu_entrega", "entregue", "cancelado"]
