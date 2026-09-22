from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pwdlib import PasswordHash
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pao.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",") if item.strip()]

if JWT_SECRET == "dev-secret-change-me" and os.getenv("ENVIRONMENT", "development") == "production":
    raise RuntimeError("Defina JWT_SECRET antes de executar em produção")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(80), default="Outros")
    image: Mapped[str] = mapped_column(String(500), default="")
    promo: Mapped[dict] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    address: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="pendente")
    total: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(150))
    price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")


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


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = ""
    price: float = Field(ge=0)
    category: str = "Outros"
    image: str = ""
    promo: dict | None = None
    active: bool = True


class ProductResponse(ProductCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class OrderCreate(BaseModel):
    address: str = Field(min_length=5, max_length=300)
    notes: str = ""
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
    address: str
    notes: str
    status: str
    total: float
    created_at: datetime
    items: list[OrderItemResponse]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login necessário")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito ao administrador")
    return user


def seed_database() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == "admin@pao.com")):
            db.add_all(
                [
                    User(name="Admin Demo", email="admin@pao.com", password_hash=password_hash.hash("admin123"), role="admin"),
                    User(name="Cliente Demo", email="cliente@pao.com", password_hash=password_hash.hash("123456")),
                ]
            )
        if not db.scalar(select(Product).limit(1)):
            db.add_all(
                [
                    Product(name="Pão Francês", description="Casquinha crocante e miolo macio.", price=0.75, category="Pães"),
                    Product(name="Pão de Queijo", description="Receita mineira tradicional.", price=14.90, category="Pães"),
                    Product(name="Café Espresso", description="Grãos torrados e café tirado na hora.", price=5.50, category="Bebidas"),
                ]
            )
        db.commit()


app = FastAPI(title="Pão para Toda Obra API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*-5500\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    seed_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(data: UserCreate, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    email = data.email
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado")
    user = User(name=data.name.strip(), email=email, password_hash=password_hash.hash(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado")
    db.refresh(user)
    return AuthResponse(access_token=create_token(user), user=user)


@app.post("/auth/login", response_model=AuthResponse)
def login(data: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    return AuthResponse(access_token=create_token(user), user=user)


@app.get("/products", response_model=list[ProductResponse])
def list_products(db: Annotated[Session, Depends(get_db)]) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id)))


@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(data: ProductCreate, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, data: ProductCreate, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    for key, value in data.model_dump().items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}")
def delete_product(product_id: int, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    product.active = False
    db.commit()
    return {"status": "deleted"}


@app.post("/orders", response_model=OrderResponse, status_code=201)
def create_order(data: OrderCreate, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> Order:
    product_ids = [item.product_id for item in data.items]
    products = {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(product_ids), Product.active.is_(True)))}
    if len(products) != len(set(product_ids)):
        raise HTTPException(status_code=400, detail="Um ou mais produtos não estão disponíveis")

    order = Order(
        user_id=user.id,
        address=data.address.strip(),
        notes=data.notes.strip(),
        total=0.0,
    )
    for requested in data.items:
        product = products[requested.product_id]
        order.items.append(OrderItem(product_id=product.id, name=product.name, price=product.price, quantity=requested.quantity))
        order.total += product.price * requested.quantity
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders", response_model=list[OrderResponse])
def list_orders(user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> list[Order]:
    query = select(Order).order_by(Order.created_at.desc())
    if user.role != "admin":
        query = query.where(Order.user_id == user.id)
    return list(db.scalars(query))


@app.patch("/orders/{order_id}/status", response_model=OrderResponse)
def update_order_status(order_id: int, new_status: str, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Order:
    allowed = {"pendente", "preparando", "saiu_entrega", "entregue", "cancelado"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    order.status = new_status
    db.commit()
    db.refresh(order)
    return order
