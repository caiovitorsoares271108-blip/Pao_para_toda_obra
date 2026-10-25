from __future__ import annotations

import os
from datetime import datetime, timezone

from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
DATABASE_URL = (os.getenv("DATABASE_URL", "") or os.getenv("SUPABASE_DB_URL", "")).strip()

if SUPABASE_URL:
    SUPABASE_URL = SUPABASE_URL.rstrip("/")
    if not SUPABASE_URL.startswith("https://"):
        raise RuntimeError("SUPABASE_URL deve usar https://")
    if SUPABASE_URL.endswith("/rest/v1"):
        SUPABASE_URL = SUPABASE_URL.removesuffix("/rest/v1")
    if len(SUPABASE_URL.split("/")) < 3 or not SUPABASE_URL.split("/")[2]:
        raise RuntimeError("SUPABASE_URL deve incluir um hostname válido")

if DATABASE_URL:
    if not DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+psycopg://", "sqlite:")):
        raise RuntimeError("DATABASE_URL deve ser uma conexão PostgreSQL ou SQLite")
elif ENVIRONMENT == "production":
    raise RuntimeError("Defina DATABASE_URL/SUPABASE_DB_URL para conectar ao banco PostgreSQL")
else:
    DATABASE_URL = "sqlite:///./pao.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgres://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgresql://")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_options.update(pool_size=5, max_overflow=5, pool_recycle=1800)
engine = create_engine(DATABASE_URL, **engine_options)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        # SQLite ignora FOREIGN KEY por padrão; WAL permite leitura durante escrita
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.close()


def init_sqlite_schema() -> None:
    """Banco SQLite vazio: aplica schema.sql (constraints, triggers, views). No-op nos demais casos."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        raw = conn.connection.driver_connection
        has_users = raw.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        if not has_users:
            schema_file = Path(__file__).with_name("schema.sql")
            if schema_file.is_file():
                raw.executescript(schema_file.read_text(encoding="utf-8"))


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    seed_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(String(500), default="")
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    category: Mapped[str] = mapped_column(String(80), default="Outros")
    image: Mapped[str] = mapped_column(String(500), default="")
    promo: Mapped[dict] = mapped_column(JSON, nullable=True)
    promo_starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    promo_ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                 onupdate=lambda: datetime.now(timezone.utc))
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()