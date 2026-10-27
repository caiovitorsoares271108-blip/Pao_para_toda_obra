from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

if __package__ and __package__.startswith("backend."):
    from ..api_schemas import (
        AuthResponse, DemoLoginRequest, LoginRequest, OrderCreate, OrderStatusUpdate,
        ProductCreate, ProductPatch, ProfileAddressUpdate, UserCreate, UserResponse,
        UserUpdate,
    )
    from ..supabase_rest import SupabaseRest, get_supabase
else:
    from api_schemas import (
        AuthResponse, DemoLoginRequest, LoginRequest, OrderCreate, OrderStatusUpdate,
        ProductCreate, ProductPatch, ProfileAddressUpdate, UserCreate, UserResponse,
        UserUpdate,
    )
    from supabase_rest import SupabaseRest, get_supabase


ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))
AUTH_COOKIE_NAME = "pao_session"
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
accounts_router = APIRouter(prefix="/auth", tags=["contas"])
products_router = APIRouter(prefix="/products", tags=["cardapio"])
orders_router = APIRouter(prefix="/orders", tags=["pedidos"])

ORDER_STATUS_TRANSITIONS = {
    "pendente": {"preparando", "saiu_entrega", "entregue", "cancelado"},
    "preparando": {"saiu_entrega", "entregue", "cancelado"},
    "saiu_entrega": {"entregue", "cancelado"},
    "entregue": set(),
    "cancelado": set(),
}


@dataclass
class UserRecord:
    id: int
    name: str
    email: str
    password_hash: str
    address: str
    role: str
    active: bool
    created_at: datetime | None = None


def _user(row: dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=row["id"], name=row["name"], email=row["email"],
        password_hash=row["password_hash"], address=row.get("address") or "",
        role=row["role"], active=row["active"], created_at=row.get("created_at"),
    )


def _find_user(client: SupabaseRest, **filters: str) -> UserRecord | None:
    rows = client.select("users", **filters, limit="1")
    return _user(rows[0]) if rows else None


def _create_token(user: UserRecord) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME, token, max_age=JWT_EXPIRE_MINUTES * 60, httponly=True,
        secure=ENVIRONMENT == "production", samesite="lax", path="/",
    )


def _auth_response(user: UserRecord, response: Response) -> AuthResponse:
    token = _create_token(user)
    _set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> UserRecord:
    token = credentials.credentials if credentials else request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Login necessário")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user = _find_user(client, id=f"eq.{int(payload['sub'])}")
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(401, "Token inválido")
    if not user or not user.active:
        raise HTTPException(401, "Conta indisponível")
    return user


def current_user_or_none(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> UserRecord | None:
    try:
        return current_user(request, credentials, client)
    except HTTPException as error:
        if error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        return None


def admin_user(user: Annotated[UserRecord, Depends(current_user)]) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(403, "Acesso restrito ao administrador")
    return user


def _demo_enabled() -> bool:
    return ENVIRONMENT == "development" and os.getenv("SEED_DEMO_DATA", "false").lower() == "true"


def _profile(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in ("id", "name", "email", "address", "role", "active")}


@accounts_router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    data: UserCreate, response: Response,
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> AuthResponse:
    if _find_user(client, email=f"eq.{data.email}"):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    try:
        row = client.insert("users", {
            "name": data.name.strip(), "email": data.email,
            "password_hash": password_hash.hash(data.password), "role": "user",
        })
    except HTTPException as error:
        if error.status_code == 409:
            raise HTTPException(409, "Este e-mail já está cadastrado") from error
        raise
    return _auth_response(_user(row), response)


@accounts_router.post("/login", response_model=AuthResponse)
def login(
    data: LoginRequest, response: Response,
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> AuthResponse:
    user = _find_user(client, email=f"eq.{data.email}")
    if not user or not user.active or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(401, "E-mail ou senha inválidos")
    return _auth_response(user, response)


@accounts_router.get("/demo-accounts")
def list_demo_accounts(
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, list[dict[str, str]]]:
    accounts: list[dict[str, str]] = []
    email = os.getenv("QUICK_ADMIN_EMAIL", "").strip().lower()
    user = _find_user(client, email=f"eq.{email}", role="eq.admin", active="eq.true") if email else None
    if user:
        accounts.append({
            "role": "quick-admin", "action": "quick-admin",
            "label": "Acessar conta de administrador", "email": user.email,
        })
    if not _demo_enabled():
        return {"accounts": accounts}
    for role, name_key, expected_role, label in (
        ("admin", "DEMO_ADMIN_EMAIL", "admin", "Entrar como administrador"),
        ("customer", "DEMO_CUSTOMER_EMAIL", "user", "Entrar como cliente"),
    ):
        demo_email = os.getenv(name_key, "").strip().lower()
        if demo_email and _find_user(
            client, email=f"eq.{demo_email}", role=f"eq.{expected_role}", active="eq.true"
        ):
            accounts.append({"role": role, "label": label})
    return {"accounts": accounts}


@accounts_router.post("/quick-admin", response_model=AuthResponse)
def quick_admin(
    response: Response, client: Annotated[SupabaseRest, Depends(get_supabase)]
) -> AuthResponse:
    email = os.getenv("QUICK_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("QUICK_ADMIN_PASSWORD", "")
    if ENVIRONMENT != "development" or not email or not password:
        raise HTTPException(404, "Acesso rápido desativado")
    user = _find_user(client, email=f"eq.{email}", role="eq.admin", active="eq.true")
    if not user or not password_hash.verify(password, user.password_hash):
        raise HTTPException(401, "Acesso administrativo indisponível")
    return _auth_response(user, response)


@accounts_router.post("/demo-login", response_model=AuthResponse)
def demo_login(
    data: DemoLoginRequest, response: Response,
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> AuthResponse:
    if not _demo_enabled():
        raise HTTPException(404, "Acesso de demonstração desativado")
    key = "DEMO_ADMIN_EMAIL" if data.role == "admin" else "DEMO_CUSTOMER_EMAIL"
    expected_role = "admin" if data.role == "admin" else "user"
    email = os.getenv(key, "").strip().lower()
    user = _find_user(client, email=f"eq.{email}", role=f"eq.{expected_role}", active="eq.true") if email else None
    if not user:
        raise HTTPException(404, "Conta de demonstração não encontrada")
    return _auth_response(user, response)


@accounts_router.get("/me", response_model=UserResponse | None)
def get_me(user: Annotated[UserRecord | None, Depends(current_user_or_none)]) -> UserRecord | None:
    return user


@accounts_router.patch("/me/address", response_model=UserResponse)
def update_address(
    data: ProfileAddressUpdate, user: Annotated[UserRecord, Depends(current_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    rows = client.update("users", {"id": f"eq.{user.id}"}, {"address": data.address})
    if not rows:
        raise HTTPException(404, "Conta não encontrada")
    return rows[0]


@accounts_router.post("/session", response_model=UserResponse)
def renew_session(
    user: Annotated[UserRecord, Depends(current_user)], response: Response
) -> UserRecord:
    _set_auth_cookie(response, _create_token(user))
    return user


@accounts_router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        AUTH_COOKIE_NAME, httponly=True, secure=ENVIRONMENT == "production",
        samesite="lax", path="/",
    )
    return {"status": "ok"}


@accounts_router.get("/accounts", response_model=list[UserResponse])
def list_accounts(
    _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> list[dict[str, Any]]:
    return [_profile(row) for row in client.select("users", order="id.asc")]


@accounts_router.post("/accounts", response_model=UserResponse, status_code=201)
def create_account(
    data: UserCreate, _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    if _find_user(client, email=f"eq.{data.email}"):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    try:
        row = client.insert("users", {
            "name": data.name.strip(), "email": data.email,
            "password_hash": password_hash.hash(data.password), "role": "user",
        })
    except HTTPException as error:
        if error.status_code == 409:
            raise HTTPException(409, "Este e-mail já está cadastrado") from error
        raise
    return _profile(row)


@accounts_router.patch("/accounts/{user_id}", response_model=UserResponse)
def update_account(
    user_id: int, data: UserUpdate, admin: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    user = _find_user(client, id=f"eq.{user_id}")
    if not user:
        raise HTTPException(404, "Conta não encontrada")
    changes = data.model_dump(exclude_unset=True)
    if user.id == admin.id and changes.get("role") not in (None, "admin"):
        raise HTTPException(409, "O administrador principal não pode remover o próprio papel")
    if user.id == admin.id and changes.get("active") is False:
        raise HTTPException(409, "O administrador principal não pode desativar a própria conta")
    password = changes.pop("password", None)
    if password:
        changes["password_hash"] = password_hash.hash(password)
    rows = client.update("users", {"id": f"eq.{user_id}"}, changes)
    if not rows:
        raise HTTPException(404, "Conta não encontrada")
    return _profile(rows[0])


@products_router.get("", response_model=list[dict[str, Any]])
def list_products(client: Annotated[SupabaseRest, Depends(get_supabase)]) -> list[dict[str, Any]]:
    return client.select("products", active="eq.true", order="id.asc")


@products_router.get("/admin", response_model=list[dict[str, Any]])
def list_products_admin(
    _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> list[dict[str, Any]]:
    return client.select("products", order="id.asc")


@products_router.post("", response_model=dict[str, Any], status_code=201)
def create_product(
    data: ProductCreate, _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    return client.insert("products", data.model_dump(mode="json"))


@products_router.patch("/{product_id}", response_model=dict[str, Any])
def update_product(
    product_id: int, data: ProductPatch, _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    changes = data.model_dump(exclude_unset=True, mode="json")
    if changes.get("promo_starts_at") and changes.get("promo_ends_at"):
        if changes["promo_starts_at"] > changes["promo_ends_at"]:
            raise HTTPException(400, "O início da promoção deve anteceder o fim")
    rows = client.update("products", {"id": f"eq.{product_id}"}, changes)
    if not rows:
        raise HTTPException(404, "Produto não encontrado")
    return rows[0]


@products_router.delete("/{product_id}")
def deactivate_product(
    product_id: int, _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, str]:
    rows = client.update("products", {"id": f"eq.{product_id}"}, {"active": False})
    if not rows:
        raise HTTPException(404, "Produto não encontrado")
    return {"status": "deleted"}


def _effective_price(product: dict[str, Any]) -> Decimal:
    price = Decimal(str(product["price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    promo = product.get("promo") or {}
    now = datetime.now(timezone.utc)
    if not promo.get("active"):
        return price
    for key, is_after in (("promo_starts_at", True), ("promo_ends_at", False)):
        value = product.get(key)
        if value:
            boundary = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if boundary.tzinfo is None:
                boundary = boundary.replace(tzinfo=timezone.utc)
            if (is_after and now < boundary) or (not is_after and now > boundary):
                return price
    discount = Decimal(str(promo.get("value", 0)))
    if discount < 0:
        raise HTTPException(400, "Promoção inválida")
    if promo.get("type") == "percent" and discount <= 100:
        price *= (Decimal("100") - discount) / Decimal("100")
    elif promo.get("type") == "fixed":
        price -= discount
    else:
        raise HTTPException(400, "Promoção inválida")
    return max(price, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _order_response(client: SupabaseRest, order: dict[str, Any]) -> dict[str, Any]:
    items = client.select("order_items", order_id=f"eq.{order['id']}", order="id.asc")
    user = _find_user(client, id=f"eq.{order['user_id']}")
    return {
        **order,
        "user_email": user.email if user else "",
        "items": items,
    }


@orders_router.post("", response_model=dict[str, Any], status_code=201)
def create_order(
    data: OrderCreate, user: Annotated[UserRecord, Depends(current_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    quantities: dict[int, int] = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
        if quantities[item.product_id] > 99:
            raise HTTPException(400, "Quantidade máxima por produto é 99")
    id_filter = "in.(" + ",".join(str(product_id) for product_id in quantities) + ")"
    products = client.select("products", id=id_filter, active="eq.true")
    if len(products) != len(quantities):
        raise HTTPException(400, "Um ou mais produtos não estão disponíveis")
    by_id = {row["id"]: row for row in products}
    order_items: list[dict[str, Any]] = []
    for product_id, quantity in quantities.items():
        product = by_id[product_id]
        price = _effective_price(product)
        order_items.append({
            "product_id": product_id, "name": product["name"],
            "price": str(price), "quantity": quantity,
        })
    order_id = client.rpc("create_order_with_items", {
        "p_user_id": user.id,
        "p_address": data.address.strip(),
        "p_notes": data.notes.strip(),
        "p_items": order_items,
    })
    if not isinstance(order_id, int):
        raise HTTPException(502, "O Supabase não retornou o identificador do pedido")
    orders = client.select("orders", id=f"eq.{order_id}", limit="1")
    if not orders:
        raise HTTPException(502, "O pedido criado não foi encontrado no Supabase")
    return _order_response(client, orders[0])


@orders_router.get("", response_model=list[dict[str, Any]])
def list_orders(
    user: Annotated[UserRecord, Depends(current_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> list[dict[str, Any]]:
    filters = {} if user.role == "admin" else {"user_id": f"eq.{user.id}"}
    rows = client.select("orders", **filters, order="created_at.desc")
    return [_order_response(client, row) for row in rows]


@orders_router.patch("/{order_id}/status", response_model=dict[str, Any])
def update_order_status(
    order_id: int, data: OrderStatusUpdate, _: Annotated[UserRecord, Depends(admin_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    current = client.select("orders", id=f"eq.{order_id}", limit="1")
    if not current:
        raise HTTPException(404, "Pedido não encontrado")
    order = current[0]
    if data.status != order["status"] and data.status not in ORDER_STATUS_TRANSITIONS.get(order["status"], set()):
        raise HTTPException(409, "Mudança de status não permitida para este pedido")
    rows = client.update(
        "orders", {"id": f"eq.{order_id}", "status": f"eq.{order['status']}"},
        {"status": data.status},
    )
    if not rows:
        raise HTTPException(409, "Mudança de status não permitida para este pedido")
    return _order_response(client, rows[0])


@orders_router.post("/{order_id}/cancel", response_model=dict[str, Any])
def cancel_order(
    order_id: int, user: Annotated[UserRecord, Depends(current_user)],
    client: Annotated[SupabaseRest, Depends(get_supabase)],
) -> dict[str, Any]:
    rows = client.update(
        "orders",
        {"id": f"eq.{order_id}", "user_id": f"eq.{user.id}", "status": "eq.pendente"},
        {"status": "cancelado"},
    )
    if rows:
        return _order_response(client, rows[0])
    order = client.select(
        "orders", id=f"eq.{order_id}", user_id=f"eq.{user.id}", limit="1"
    )
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    raise HTTPException(409, "Somente pedidos pendentes podem ser cancelados")
