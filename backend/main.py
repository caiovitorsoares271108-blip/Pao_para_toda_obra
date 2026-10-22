from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

import jwt 
from flask import Flask, abort, send_from_directory
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.wsgi import WSGIMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pwdlib import PasswordHash
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    if ENVIRONMENT == "production":
        raise RuntimeError("DATABASE_URL é obrigatória em produção")
    DATABASE_URL = "sqlite:///./pao.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgres://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgresql://")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))
AUTH_COOKIE_NAME = "pao_session"
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",") if item.strip()]
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"

if JWT_SECRET == "dev-secret-change-me" and ENVIRONMENT == "production":
    raise RuntimeError("Defina JWT_SECRET antes de executar em produção")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(pool_size=5, max_overflow=5, pool_recycle=1800)
engine = create_engine(DATABASE_URL, **engine_options)
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
    price: Mapped[float] = mapped_column(Numeric(10, 2))
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
    total: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    @property
    def user_email(self) -> str:
        return self.user.email if self.user else ""


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(150))
    price: Mapped[float] = mapped_column(Numeric(10, 2))
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


class DemoLoginRequest(BaseModel):
    role: Literal["admin", "customer"]


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
    user_email: str
    address: str
    notes: str
    status: str
    total: float
    created_at: datetime
    items: list[OrderItemResponse]


class OrderStatusUpdate(BaseModel):
    status: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


def demo_account_configs() -> dict[str, tuple[str, str]]:
    return {
        "admin": (os.getenv("DEMO_ADMIN_EMAIL", "").strip().lower(), "admin"),
        "customer": (os.getenv("DEMO_CUSTOMER_EMAIL", "").strip().lower(), "user"),
    }


def demo_accounts_enabled() -> bool:
    return ENVIRONMENT == "development" and SEED_DEMO_DATA


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = credentials.credentials if credentials else request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login necessário")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
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


def initialize_database() -> None:
    Base.metadata.create_all(engine)
    seed_demo_accounts = ENVIRONMENT == "development" and SEED_DEMO_DATA
    with SessionLocal() as db:
        demo_accounts = [
            (
                "DEMO_ADMIN_NAME",
                "DEMO_ADMIN_EMAIL",
                "DEMO_ADMIN_PASSWORD",
                "Administrador Demo",
                "admin",
            ),
            (
                "DEMO_CUSTOMER_NAME",
                "DEMO_CUSTOMER_EMAIL",
                "DEMO_CUSTOMER_PASSWORD",
                "Cliente Demo",
                "user",
            ),
        ]
        if not seed_demo_accounts:
            demo_accounts = []
        for name_key, email_key, password_key, default_name, role in demo_accounts:
            email = os.getenv(email_key, "").strip().lower()
            password = os.getenv(password_key, "")
            if email and password and not db.scalar(select(User).where(User.email == email)):
                db.add(User(
                    name=os.getenv(name_key, default_name).strip(),
                    email=email,
                    password_hash=password_hash.hash(password),
                    role=role,
                ))

        initial_accounts = [
            ("INITIAL_ADMIN_NAME", "INITIAL_ADMIN_EMAIL", "INITIAL_ADMIN_PASSWORD", "Administrador", "admin"),
            ("INITIAL_CUSTOMER_NAME", "INITIAL_CUSTOMER_EMAIL", "INITIAL_CUSTOMER_PASSWORD", "Cliente", "user"),
        ]
        for name_key, email_key, password_key, default_name, role in initial_accounts:
            email = os.getenv(email_key, "").strip().lower()
            password = os.getenv(password_key, "")
            if not email or len(password) < 6:
                continue
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(
                    name=os.getenv(name_key, default_name).strip() or default_name,
                    email=email,
                    password_hash=password_hash.hash(password),
                    role=role,
                ))

        if ENVIRONMENT != "test" and not db.scalar(select(Product).limit(1)):
            db.add_all([
                Product(name="Pão Francês", description="Casquinha crocante, miolo macio. Assado várias vezes ao dia.", price=0.75, category="Pães", image="https://images.unsplash.com/photo-1586444248902-2f64eddc13df?auto=format&fit=crop&w=900&q=82"),
                Product(name="Pão de Queijo (6 un.)", description="Receita mineira tradicional, quentinho e elástico por dentro.", price=14.90, category="Pães", image="https://images.unsplash.com/photo-1574017019416-5b1f68b5a2c1?auto=format&fit=crop&w=900&q=82"),
                Product(name="Baguete Artesanal", description="Fermentação longa, casca crocante e aroma de padaria.", price=12.90, category="Pães", image="https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=900&q=82"),
                Product(name="Pão Integral de Forma", description="Fatiado, rico em fibras e sem conservantes.", price=16.50, category="Pães", image="https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?auto=format&fit=crop&w=900&q=82"),
                Product(name="Pão Australiano", description="Massa macia e levemente adocicada, perfeita para sanduíches.", price=18.90, category="Pães", image="https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=900&q=82"),
                Product(name="Sonho de Creme", description="Massa fofinha com recheio de creme de confeiteiro.", price=8.50, category="Doces", image="https://images.unsplash.com/photo-1550617931-e17a7b70dce2?auto=format&fit=crop&w=900&q=82"),
                Product(name="Croissant de Chocolate", description="Folhado amanteigado com recheio generoso de chocolate.", price=9.90, category="Doces", image="https://images.unsplash.com/photo-1587312246397-1c817a8eb86d?auto=format&fit=crop&w=900&q=82"),
                Product(name="Fatia de Bolo de Fubá", description="Molhadinho com casquinha crocante, receita de família.", price=7.90, category="Doces", image="https://images.unsplash.com/photo-1588195538326-c5b1e9f80a1b?auto=format&fit=crop&w=900&q=82"),
                Product(name="Rocambole de Doce de Leite", description="Massa fofa enrolada com doce de leite cremoso.", price=8.90, category="Doces", image="https://images.unsplash.com/photo-1551024506-0bccd828d307?auto=format&fit=crop&w=900&q=82"),
                Product(name="Brigadeiro Gourmet", description="Chocolate intenso com granulado crocante, feito na hora.", price=4.50, category="Doces", image="https://images.unsplash.com/photo-1571115177098-24ec42ed204d?auto=format&fit=crop&w=900&q=82"),
                Product(name="Coxinha de Frango", description="Massa lisa e recheio cremoso de frango desfiado.", price=7.50, category="Salgados", image="https://images.unsplash.com/photo-1626768902589-2ae9efd0fffb?auto=format&fit=crop&w=900&q=82"),
                Product(name="Esfiha de Carne", description="Aberta, com carne temperada e toque de limão.", price=6.90, category="Salgados", image="https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=900&q=82"),
                Product(name="Pastel de Queijo", description="Massa fina e crocante com queijo derretido.", price=7.00, category="Salgados", image="https://images.unsplash.com/photo-1619531045520-d574aca6d54b?auto=format&fit=crop&w=900&q=82"),
                Product(name="Empada de Palmito", description="Massa delicada com recheio de palmito e requeijão.", price=8.90, category="Salgados", image="https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=900&q=82"),
                Product(name="Cookie de Chocolate", description="Macio por dentro, crocante por fora, com gotas de chocolate.", price=6.50, category="Doces", image="https://images.unsplash.com/photo-1499636136210-6f4ee919583b?auto=format&fit=crop&w=900&q=82"),
                Product(name="Café Espresso", description="Grãos torrados na medida, tirado na hora.", price=5.50, category="Bebidas", image="https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=900&q=82"),
                Product(name="Suco de Laranja 300 ml", description="Laranjas espremidas na hora, sem açúcar.", price=8.90, category="Bebidas", image="https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=900&q=82"),
                Product(name="Chá Gelado de Pêssego", description="Chá preto com suco de pêssego e hortelã.", price=7.50, category="Bebidas", image="https://images.unsplash.com/photo-1541795795328-f073b763494e?auto=format&fit=crop&w=900&q=82"),
                Product(name="Capuccino Cremoso", description="Café com leite cremoso, chocolate e canela.", price=9.90, category="Bebidas", image="https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=900&q=82"),
                Product(name="Torta de Limão", description="Massa crocante com mousse de limão e merengue.", price=12.90, category="Doces", image="https://images.unsplash.com/photo-1587312246397-1c817a8eb86d?auto=format&fit=crop&w=900&q=82"),
                Product(name="Pão de Batata com Requeijão", description="Massa macia com recheio cremoso de requeijão.", price=11.90, category="Pães", image="https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?auto=format&fit=crop&w=900&q=82"),
            ])
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

frontend_directory = Path(__file__).resolve().parent.parent / "frontend"
frontend = Flask(__name__, static_folder=None)


@frontend.get("/")
@frontend.get("/undex.html")
def serve_frontend():
    return send_from_directory(frontend_directory, "undex.html")


@frontend.get("/<path:requested_path>")
def serve_frontend_asset(requested_path: str):
    requested_file = frontend_directory / requested_path
    if requested_file.is_file() and frontend_directory in requested_file.parents:
        return send_from_directory(frontend_directory, requested_path)
    abort(404)


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception:
        raise HTTPException(status_code=503, detail="Banco de dados indisponível")


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(data: UserCreate, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
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
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@app.post("/auth/login", response_model=AuthResponse)
def login(data: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@app.get("/auth/demo-accounts")
def list_demo_accounts(db: Annotated[Session, Depends(get_db)]) -> dict[str, list[dict[str, str]]]:
    if not demo_accounts_enabled():
        return {"accounts": []}
    labels = {"admin": "Entrar como administrador", "customer": "Entrar como cliente"}
    accounts = []
    for role, (email, expected_role) in demo_account_configs().items():
        user = db.scalar(select(User).where(User.email == email)) if email else None
        if user and user.role == expected_role:
            accounts.append({"role": role, "label": labels[role]})
    return {"accounts": accounts}


@app.post("/auth/demo-login", response_model=AuthResponse)
def demo_login(data: DemoLoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    if not demo_accounts_enabled():
        raise HTTPException(status_code=404, detail="Acesso de demonstração desativado")
    email, expected_role = demo_account_configs()[data.role]
    user = db.scalar(select(User).where(User.email == email)) if email else None
    if not user or user.role != expected_role:
        raise HTTPException(status_code=404, detail="Conta de demonstração não encontrada")
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@app.get("/auth/me", response_model=UserResponse)
def get_current_user(user: Annotated[User, Depends(current_user)]) -> User:
    return user


@app.post("/auth/session", response_model=UserResponse)
def renew_auth_cookie(user: Annotated[User, Depends(current_user)], response: Response) -> User:
    set_auth_cookie(response, create_token(user))
    return user


@app.post("/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )
    return {"status": "ok"}


@app.get("/products", response_model=list[ProductResponse])
def list_products(db: Annotated[Session, Depends(get_db)]) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id)))


@app.get("/products/admin", response_model=list[ProductResponse])
def list_products_admin(_: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.id)))


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

    from decimal import Decimal, ROUND_HALF_UP

    def applied_price(product: Product) -> Decimal:
        price = Decimal(str(product.price))
        promo = product.promo or {}
        if not promo.get("active"):
            return price
        value = Decimal(str(promo.get("value", 0)))
        if value < 0:
            raise HTTPException(status_code=400, detail="Promoção inválida")
        if promo.get("type") == "percent":
            if value > 100:
                raise HTTPException(status_code=400, detail="Promoção inválida")
            price *= (Decimal("100") - value) / Decimal("100")
        elif promo.get("type") == "fixed":
            price -= value
        else:
            raise HTTPException(status_code=400, detail="Promoção inválida")
        return max(price, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    order = Order(
        user_id=user.id,
        address=data.address.strip(),
        notes=data.notes.strip(),
        total=Decimal("0.00"),
    )
    for requested in data.items:
        product = products[requested.product_id]
        item_price = applied_price(product)
        order.items.append(OrderItem(product_id=product.id, name=product.name, price=item_price, quantity=requested.quantity))
        order.total += item_price * requested.quantity
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
def update_order_status(order_id: int, data: OrderStatusUpdate, _: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> Order:
    allowed = {"pendente", "preparando", "saiu_entrega", "entregue", "cancelado"}
    if data.status not in allowed:
        raise HTTPException(status_code=400, detail="Status inválido")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    order.status = data.status
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: int, user: Annotated[User, Depends(current_user)], db: Annotated[Session, Depends(get_db)]) -> Order:
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if order.status != "pendente":
        raise HTTPException(status_code=409, detail="Somente pedidos pendentes podem ser cancelados")
    order.status = "cancelado"
    db.commit()
    db.refresh(order)
    return order


app.mount("/", WSGIMiddleware(frontend))
