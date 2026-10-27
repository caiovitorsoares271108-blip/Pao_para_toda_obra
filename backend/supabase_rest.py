from __future__ import annotations

import base64
import json
import os
from typing import Any, Mapping

import httpx
from fastapi import HTTPException


SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _server_key_from_env(environ: Mapping[str, str]) -> str:
    key = environ.get("SUPABASE_KEY", "").strip()
    if not key:
        raise RuntimeError("Defina SUPABASE_KEY com a chave privada de servidor do Supabase")
    return key


SUPABASE_KEY = _server_key_from_env(os.environ)


def _legacy_jwt_role(key: str) -> str | None:
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    role = claims.get("role")
    return role if isinstance(role, str) else None


LEGACY_JWT_ROLE = _legacy_jwt_role(SUPABASE_KEY)
IS_LEGACY_JWT_KEY = LEGACY_JWT_ROLE == "service_role"
if not SUPABASE_URL:
    raise RuntimeError("Defina SUPABASE_URL com o endereço do projeto Supabase")
if SUPABASE_KEY.startswith("sb_publishable_"):
    raise RuntimeError(
        "SUPABASE_KEY é publishable; use uma chave secret/service_role privada no backend"
    )
if SUPABASE_KEY.startswith("eyJ") and not IS_LEGACY_JWT_KEY:
    raise RuntimeError(
        "SUPABASE_KEY é um JWT sem role service_role; use uma chave secret/service_role privada no backend"
    )
if not SUPABASE_URL.startswith("https://"):
    raise RuntimeError("SUPABASE_URL deve usar https://")
if SUPABASE_URL.endswith("/rest/v1"):
    SUPABASE_URL = SUPABASE_URL.removesuffix("/rest/v1")


class SupabaseRest:
    def __init__(self) -> None:
        headers = {"apikey": SUPABASE_KEY, "Accept": "application/json"}
        if IS_LEGACY_JWT_KEY:
            headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
        self.client = httpx.Client(
            base_url=f"{SUPABASE_URL}/rest/v1/",
            headers=headers,
            timeout=15,
        )

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {"Prefer": prefer} if prefer else {}
        try:
            response = self.client.request(
                method, path, params=params, json=body, headers=headers
            )
        except httpx.RequestError as error:
            raise HTTPException(503, "Não foi possível conectar à API do Supabase") from error
        if not response.is_success:
            try:
                details = response.json()
            except ValueError:
                details = {}
            if not isinstance(details, dict):
                details = {}
            code = details.get("code")
            message = details.get("message") or details.get("details") or "Falha na API do Supabase"
            if response.status_code in (400, 409) and details.get("code") in ("23505", "23514", "23503"):
                raise HTTPException(409, message)
            if response.status_code == 401:
                raise HTTPException(
                    503,
                    "Supabase recusou SUPABASE_KEY (HTTP 401"
                    f"{f', código {code}' if code else ''}): {message}. "
                    "Confirme que a chave é privada e pertence ao mesmo projeto que SUPABASE_URL.",
                )
            if response.status_code == 403:
                hint = details.get("hint")
                diagnostic = f"{message}; dica: {hint}" if hint else message
                raise HTTPException(
                    503,
                    "Supabase negou acesso (HTTP 403"
                    f"{f', código {code}' if code else ''}): {diagnostic}. "
                    "Se SUPABASE_KEY for secret/service_role, verifique os grants da role nas tabelas.",
                )
            if response.status_code == 404:
                raise HTTPException(
                    500,
                    "Recurso Supabase não encontrado (HTTP 404"
                    f"{f', código {code}' if code else ''}): {message}",
                )
            if code in ("PGRST204", "42703"):
                raise HTTPException(
                    500,
                    "Coluna ausente no schema Supabase"
                    f" (código {code}): {message}",
                )
            raise HTTPException(response.status_code if response.status_code < 500 else 503, message)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise HTTPException(502, "O Supabase retornou uma resposta inválida") from error

    def select(self, table: str, **params: str) -> list[dict[str, Any]]:
        result = self.request("GET", table, params={"select": "*", **params})
        if not isinstance(result, list):
            raise HTTPException(502, "Resposta inesperada do Supabase")
        return result

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        result = self.request(
            "POST", table, params={"select": "*"}, body=values, prefer="return=representation"
        )
        if not isinstance(result, list) or not result:
            raise HTTPException(502, "O Supabase não retornou o registro criado")
        return result[0]

    def update(
        self, table: str, filters: dict[str, str], values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        result = self.request(
            "PATCH", table, params={"select": "*", **filters}, body=values,
            prefer="return=representation",
        )
        if not isinstance(result, list):
            raise HTTPException(502, "Resposta inesperada do Supabase")
        return result

    def rpc(self, function: str, values: dict[str, Any]) -> Any:
        return self.request("POST", f"rpc/{function}", body=values)


_client: SupabaseRest | None = None


def get_supabase() -> SupabaseRest:
    global _client
    if _client is None:
        _client = SupabaseRest()
    return _client
