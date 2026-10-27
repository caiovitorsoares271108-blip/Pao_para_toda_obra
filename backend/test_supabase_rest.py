import os
import unittest
import base64
import json
from unittest.mock import patch

import httpx
from fastapi import HTTPException

with patch.dict(os.environ, {
    "SUPABASE_URL": "https://unit-test.supabase.co",
    "SUPABASE_KEY": "unit-test-private-key",
}):
    from backend.supabase_rest import SupabaseRest


class SupabaseRestTestCase(unittest.TestCase):
    def make_client(self, handler):
        client = SupabaseRest()
        client.client.close()
        client.client = httpx.Client(
            base_url="https://unit-test.supabase.co/rest/v1/",
            headers={
                "apikey": "unit-test-private-key",
                "Accept": "application/json",
            },
            transport=httpx.MockTransport(handler),
        )
        return client

    def test_select_uses_supabase_rest_and_private_auth_headers(self):
        def handler(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/rest/v1/users")
            self.assertEqual(request.url.params["select"], "*")
            self.assertEqual(request.url.params["email"], "eq.user@example.com")
            self.assertEqual(request.headers["apikey"], "unit-test-private-key")
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(200, json=[{"id": 8, "email": "user@example.com"}])

        self.assertEqual(
            self.make_client(handler).select("users", email="eq.user@example.com"),
            [{"id": 8, "email": "user@example.com"}],
        )

    def test_rest_permissions_error_preserves_supabase_diagnostic(self):
        client = self.make_client(
            lambda _: httpx.Response(
                403,
                json={"code": "42501", "message": "permission denied for table users"},
            )
        )
        with self.assertRaises(HTTPException) as error:
            client.select("users")
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("HTTP 403", error.exception.detail)
        self.assertIn("42501", error.exception.detail)
        self.assertIn("permission denied for table users", error.exception.detail)
        self.assertIn("secret/service_role", error.exception.detail)

    def test_authentication_error_preserves_supabase_diagnostic(self):
        client = self.make_client(
            lambda _: httpx.Response(
                401,
                json={"code": "PGRST301", "message": "JWT expired"},
            )
        )
        with self.assertRaises(HTTPException) as error:
            client.select("users")
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("HTTP 401", error.exception.detail)
        self.assertIn("PGRST301", error.exception.detail)
        self.assertIn("JWT expired", error.exception.detail)

    def test_legacy_service_role_jwt_is_sent_in_authorization_header(self):
        payload = base64.urlsafe_b64encode(
            json.dumps({"role": "service_role"}).encode()
        ).decode().rstrip("=")
        token = f"header.{payload}.signature"
        with patch("backend.supabase_rest.SUPABASE_KEY", token), patch(
            "backend.supabase_rest.IS_LEGACY_JWT_KEY", True
        ):
            client = SupabaseRest()
        try:
            self.assertEqual(client.client.headers["apikey"], token)
            self.assertEqual(client.client.headers["Authorization"], f"Bearer {token}")
        finally:
            client.close()

    def test_legacy_anon_jwt_is_not_accepted_as_server_key(self):
        from backend.supabase_rest import _legacy_jwt_role

        payload = base64.urlsafe_b64encode(
            json.dumps({"role": "anon"}).encode()
        ).decode().rstrip("=")
        self.assertEqual(_legacy_jwt_role(f"header.{payload}.signature"), "anon")

    def test_secret_key_uses_apikey_without_authorization_header(self):
        with patch("backend.supabase_rest.SUPABASE_KEY", "sb_secret_private"):
            client = SupabaseRest()
        try:
            self.assertEqual(client.client.headers["apikey"], "sb_secret_private")
            self.assertNotIn("Authorization", client.client.headers)
        finally:
            client.close()

    def test_environment_uses_only_supabase_key_without_public_fallback(self):
        from backend.supabase_rest import _server_key_from_env

        with self.assertRaisesRegex(RuntimeError, "SUPABASE_KEY"):
            _server_key_from_env({
                "SUPABASE_SECRET_KEY": "private",
                "SUPABASE_SERVICE_ROLE_KEY": "private",
                "SUPABASE_PUBLISHABLE_KEY": "public",
            })
        self.assertEqual(
            _server_key_from_env({
                "SUPABASE_KEY": "  private  ",
                "SUPABASE_SECRET_KEY": "ignored",
            }),
            "private",
        )

    def test_table_not_found_preserves_postgrest_code(self):
        client = self.make_client(
            lambda _: httpx.Response(
                404,
                json={"code": "PGRST205", "message": "Could not find table public.users"},
            )
        )
        with self.assertRaises(HTTPException) as error:
            client.select("users")
        self.assertEqual(error.exception.status_code, 500)
        self.assertIn("PGRST205", error.exception.detail)
        self.assertIn("Could not find table public.users", error.exception.detail)

    def test_missing_column_preserves_postgrest_code(self):
        client = self.make_client(
            lambda _: httpx.Response(
                400,
                json={"code": "PGRST204", "message": "Column missing from schema cache"},
            )
        )
        with self.assertRaises(HTTPException) as error:
            client.select("users", select="missing_column")
        self.assertEqual(error.exception.status_code, 500)
        self.assertIn("PGRST204", error.exception.detail)
        self.assertIn("Column missing from schema cache", error.exception.detail)
