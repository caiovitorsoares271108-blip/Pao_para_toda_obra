from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if __package__ and __package__.startswith("backend."):
    from ..api_schemas import AuthResponse, DemoLoginRequest, LoginRequest, ProfileAddressUpdate, UserCreate, UserResponse, UserUpdate
    from ..database import ENVIRONMENT, User, get_db
else:
    from api_schemas import AuthResponse, DemoLoginRequest, LoginRequest, ProfileAddressUpdate, UserCreate, UserResponse, UserUpdate
    from database import ENVIRONMENT, User, get_db

router = APIRouter(prefix="/auth", tags=["contas"])
bearer = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "43200"))
AUTH_COOKIE_NAME = "pao_session"


def create_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user.id), "exp": expires}, JWT_SECRET, algorithm="HS256")


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(AUTH_COOKIE_NAME, token, max_age=JWT_EXPIRE_MINUTES * 60,
                        httponly=True, secure=ENVIRONMENT == "production",
                        samesite="lax", path="/")


def current_user(request: Request,
                 credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 db: Annotated[Session, Depends(get_db)]) -> User:
    token = credentials.credentials if credentials else request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Login necessário")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(401, "Token inválido")
    if not user or not user.active:
        raise HTTPException(401, "Conta indisponível")
    return user


def current_user_or_none(request: Request,
                         credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                         db: Annotated[Session, Depends(get_db)]) -> User | None:
    try:
        return current_user(request, credentials, db)
    except HTTPException as error:
        if error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        return None


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Acesso restrito ao administrador")
    return user


def _demo_enabled() -> bool:
    return ENVIRONMENT == "development" and os.getenv("SEED_DEMO_DATA", "false").lower() == "true"


def _quick_admin_enabled() -> bool:
    return ENVIRONMENT == "development" and bool(
        os.getenv("QUICK_ADMIN_EMAIL", "").strip()
        and os.getenv("QUICK_ADMIN_PASSWORD", "")
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: UserCreate, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    user = User(name=data.name.strip(), email=data.email, password_hash=password_hash.hash(data.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este e-mail já está cadastrado")
    db.refresh(user)
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not user.active or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(401, "E-mail ou senha inválidos")
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@router.get("/demo-accounts")
def list_demo_accounts(db: Annotated[Session, Depends(get_db)]) -> dict:
    accounts = []
    email = os.getenv("QUICK_ADMIN_EMAIL", "").strip().lower()
    user = db.scalar(select(User).where(User.email == email)) if email else None
    if user and user.active and user.role == "admin":
        accounts.append({
            "role": "quick-admin",
            "action": "quick-admin",
            "label": "Acessar conta de administrador",
            "email": user.email,
        })
    if not _demo_enabled():
        return {"accounts": accounts}
    configs = {
        "admin": (os.getenv("DEMO_ADMIN_EMAIL", "").strip().lower(), "admin"),
        "customer": (os.getenv("DEMO_CUSTOMER_EMAIL", "").strip().lower(), "user"),
    }
    labels = {"admin": "Entrar como administrador", "customer": "Entrar como cliente"}
    for role, (email, expected_role) in configs.items():
        user = db.scalar(select(User).where(User.email == email)) if email else None
        if user and user.active and user.role == expected_role:
            accounts.append({"role": role, "label": labels[role]})
    return {"accounts": accounts}


@router.post("/quick-admin", response_model=AuthResponse)
def quick_admin(response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    if not _quick_admin_enabled():
        raise HTTPException(404, "Acesso rápido desativado")
    email = os.getenv("QUICK_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("QUICK_ADMIN_PASSWORD", "")
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.active or user.role != "admin" or not password_hash.verify(password, user.password_hash):
        raise HTTPException(401, "Acesso administrativo indisponível")
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@router.post("/demo-login", response_model=AuthResponse)
def demo_login(data: DemoLoginRequest, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthResponse:
    if not _demo_enabled():
        raise HTTPException(404, "Acesso de demonstração desativado")
    email = os.getenv("DEMO_ADMIN_EMAIL" if data.role == "admin" else "DEMO_CUSTOMER_EMAIL", "").strip().lower()
    expected = "admin" if data.role == "admin" else "user"
    user = db.scalar(select(User).where(User.email == email)) if email else None
    if not user or not user.active or user.role != expected:
        raise HTTPException(404, "Conta de demonstração não encontrada")
    token = create_token(user)
    set_auth_cookie(response, token)
    return AuthResponse(access_token=token, user=user)


@router.get("/me", response_model=UserResponse | None)
def get_current_user(user: Annotated[User | None, Depends(current_user_or_none)]) -> User | None:
    return user


@router.patch("/me/address", response_model=UserResponse)
def update_my_address(data: ProfileAddressUpdate,
                      user: Annotated[User, Depends(current_user)],
                      db: Annotated[Session, Depends(get_db)]) -> User:
    user.address = data.address
    db.commit()
    db.refresh(user)
    return user


@router.post("/session", response_model=UserResponse)
def renew_auth_cookie(user: Annotated[User, Depends(current_user)], response: Response) -> User:
    set_auth_cookie(response, create_token(user))
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(AUTH_COOKIE_NAME, httponly=True,
                           secure=ENVIRONMENT == "production", samesite="lax", path="/")
    return {"status": "ok"}


@router.get("/accounts", response_model=list[UserResponse])
def list_accounts(_: Annotated[User, Depends(admin_user)], db: Annotated[Session, Depends(get_db)]) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("/accounts", response_model=UserResponse, status_code=201)
def create_account(data: UserCreate, admin: Annotated[User, Depends(admin_user)],
                   db: Annotated[Session, Depends(get_db)]) -> User:
    del admin
    return _save_account(db, data)


@router.patch("/accounts/{user_id}", response_model=UserResponse)
def update_account(user_id: int, data: UserUpdate, admin: Annotated[User, Depends(admin_user)],
                   db: Annotated[Session, Depends(get_db)]) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Conta não encontrada")
    if user.id == admin.id and data.role is not None and data.role != "admin":
        raise HTTPException(409, "O administrador principal não pode remover o próprio papel")
    if user.id == admin.id and data.active is False:
        raise HTTPException(409, "O administrador principal não pode desativar a própria conta")
    changes = data.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    if password:
        user.password_hash = password_hash.hash(password)
    for key, value in changes.items():
        setattr(user, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Os dados da conta entram em conflito")
    db.refresh(user)
    return user


def _save_account(db: Session, data: UserCreate) -> User:
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    user = User(name=data.name.strip(), email=data.email,
                password_hash=password_hash.hash(data.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este e-mail já está cadastrado")
    db.refresh(user)
    return user
