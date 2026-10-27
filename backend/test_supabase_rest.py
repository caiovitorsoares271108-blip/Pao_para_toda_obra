import os
import unittest
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

    def test_rest_permissions_error_is_reported_without_fallback(self):
        client = self.make_client(
            lambda _: httpx.Response(403, json={"message": "permission denied"})
        )
        with self.assertRaises(HTTPException) as error:
            client.select("users")
        self.assertEqual(error.exception.status_code, 503)
        self.assertIn("permissão", error.exception.detail)
