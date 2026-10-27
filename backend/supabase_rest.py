from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import HTTPException


SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
if not SUPABASE_URL:
    raise RuntimeError("Defina SUPABASE_URL com o endereço do projeto Supabase")
if not SUPABASE_KEY:
    raise RuntimeError("Defina SUPABASE_KEY com a chave privada de servidor do Supabase")
if not SUPABASE_URL.startswith("https://"):
    raise RuntimeError("SUPABASE_URL deve usar https://")
if SUPABASE_URL.endswith("/rest/v1"):
    SUPABASE_URL = SUPABASE_URL.removesuffix("/rest/v1")


class SupabaseRest:
    def __init__(self) -> None:
        self.client = httpx.Client(
            base_url=f"{SUPABASE_URL}/rest/v1/",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Accept": "application/json",
            },
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
            message = details.get("message") or details.get("details") or "Falha na API do Supabase"
            if response.status_code in (400, 409) and details.get("code") in ("23505", "23514", "23503"):
                raise HTTPException(409, message)
            if response.status_code in (401, 403):
                raise HTTPException(503, "A chave do Supabase não tem permissão para esta operação")
            if response.status_code == 404:
                raise HTTPException(500, "Recurso ou função exigida não encontrado no Supabase")
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
