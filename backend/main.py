from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from flask import Flask, abort, send_from_directory
from starlette.middleware.wsgi import WSGIMiddleware

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
if ENVIRONMENT == "test":
    from sqlalchemy import select
    if __package__:
        from .API import cardapio, contas, pedidos
        from .database import Base, Product, SessionLocal, User, engine, get_db, init_sqlite_schema
    else:
        from API import cardapio, contas, pedidos
        from database import Base, Product, SessionLocal, User, engine, get_db, init_sqlite_schema
else:
    if __package__:
        from .API.supabase_routes import accounts_router as contas_router
        from .API.supabase_routes import orders_router as pedidos_router
        from .API.supabase_routes import password_hash as supabase_password_hash
        from .API.supabase_routes import products_router as cardapio_router
        from .supabase_rest import SupabaseRest, get_supabase
    else:
        from API.supabase_routes import accounts_router as contas_router
        from API.supabase_routes import orders_router as pedidos_router
        from API.supabase_routes import password_hash as supabase_password_hash
        from API.supabase_routes import products_router as cardapio_router
        from supabase_rest import SupabaseRest, get_supabase

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
if JWT_SECRET == "dev-secret-change-me" and ENVIRONMENT == "production":
    raise RuntimeError("Defina JWT_SECRET antes de executar em produção")

CORS_ORIGINS = [item.strip() for item in os.getenv(
    "CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500"
).split(",") if item.strip()]


def _seed_catalog(db) -> None:
    seed_file = Path(__file__).with_name("products_seed.json")
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    if ENVIRONMENT != "test":
        existing = db.select("products", select="seed_key,name")
        seed_keys = {row["seed_key"] for row in existing if row.get("seed_key")}
        product_names = {row["name"] for row in existing}
        for item in seed:
            if item["seed_key"] in seed_keys or item["name"] in product_names:
                continue
            db.insert("products", item)
            seed_keys.add(item["seed_key"])
            product_names.add(item["name"])
        return
    for item in seed:
        if db.scalar(select(Product).where(Product.seed_key == item["seed_key"])):
            continue
        if db.scalar(select(Product).where(Product.name == item["name"])):
            continue
        product_data = {**item, "price": Decimal(str(item["price"]))}
        db.add(Product(**product_data))
    db.commit()


def _provision_initial_accounts(db) -> None:
    configs = (
        ("INITIAL_ADMIN_NAME", "INITIAL_ADMIN_EMAIL", "INITIAL_ADMIN_PASSWORD", "Administrador", "admin"),
        ("INITIAL_CUSTOMER_NAME", "INITIAL_CUSTOMER_EMAIL", "INITIAL_CUSTOMER_PASSWORD", "Cliente", "user"),
    )
    for name_key, email_key, password_key, default_name, role in configs:
        email = os.getenv(email_key, "").strip().lower()
        password = os.getenv(password_key, "")
        if not email or len(password) < 6:
            continue
        if ENVIRONMENT != "test":
            if role == "admin" and db.select("users", role="eq.admin", limit="1"):
                continue
            if db.select("users", email=f"eq.{email}", limit="1"):
                continue
            db.insert("users", {
                "name": os.getenv(name_key, default_name).strip() or default_name,
                "email": email, "password_hash": supabase_password_hash.hash(password), "role": role,
            })
        else:
            if role == "admin" and db.scalar(select(User.id).where(User.role == "admin")):
                continue
            if db.scalar(select(User).where(User.email == email)):
                continue
            db.add(User(name=os.getenv(name_key, default_name).strip() or default_name,
                        email=email, password_hash=contas.password_hash.hash(password), role=role))
    if ENVIRONMENT == "test":
        db.commit()


def initialize_database() -> None:
    if ENVIRONMENT != "test":
        client = get_supabase()
        client.select("users", select="id", limit="1")
        _provision_initial_accounts(client)
        _seed_catalog(client)
        return
    init_sqlite_schema()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _provision_initial_accounts(db)
        if ENVIRONMENT != "test":
            _seed_catalog(db)


app = FastAPI(title="Pão para Toda Obra API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*-5500\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if ENVIRONMENT == "test":
    app.include_router(contas.router)
    app.include_router(cardapio.router)
    app.include_router(pedidos.router)
else:
    app.include_router(contas_router)
    app.include_router(cardapio_router)
    app.include_router(pedidos_router)

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


@app.on_event("shutdown")
def shutdown() -> None:
    if ENVIRONMENT != "test":
        get_supabase().close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def health_db() -> dict[str, str]:
    try:
        if ENVIRONMENT == "test":
            from sqlalchemy import text
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "reachable", "engine": engine.dialect.name}
        get_supabase().select("users", select="id", limit="1")
        return {"status": "ok", "database": "reachable", "engine": "supabase-rest"}
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Banco de dados indisponível")


app.mount("/", WSGIMiddleware(frontend))