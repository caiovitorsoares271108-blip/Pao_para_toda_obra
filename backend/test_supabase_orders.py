import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException

with patch.dict(os.environ, {
    "SUPABASE_URL": "https://unit-test.supabase.co",
    "SUPABASE_KEY": "sb_secret_unit_test",
}):
    from backend.API.supabase_routes import UserRecord, create_order
    from backend.api_schemas import OrderCreate
    from backend.supabase_rest import SupabaseRest


MIGRATION = Path(__file__).with_name("migration_supabase_rest_orders.sql")


class SupabaseOrderTestCase(unittest.TestCase):
    def setUp(self):
        self.user = UserRecord(
            id=17, name="Cliente", email="cliente@example.com",
            password_hash="unused", address="", role="user", active=True,
        )
        self.product = {
            "id": 4, "name": "Pão caseiro", "price": "100.00", "active": True,
            "promo": {"active": True, "type": "percent", "value": 25},
        }

    def test_rpc_http_payload_matches_migration_signature(self):
        payload = {
            "p_user_id": 17,
            "p_address": "Rua da Obra, 10",
            "p_notes": "Sem troco",
            "p_items": [{
                "product_id": 4, "name": "Pão caseiro", "price": "75.00", "quantity": 2,
            }],
        }
        observed = {}

        def handler(request):
            observed["method"] = request.method
            observed["path"] = request.url.path
            observed["body"] = request.read().decode()
            return httpx.Response(200, json=31)

        client = SupabaseRest()
        client.client.close()
        client.client = httpx.Client(
            base_url="https://unit-test.supabase.co/rest/v1/",
            transport=httpx.MockTransport(handler),
        )
        try:
            self.assertEqual(client.rpc("create_order_with_items", payload), 31)
        finally:
            client.close()

        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["path"], "/rest/v1/rpc/create_order_with_items")
        self.assertEqual(json.loads(observed["body"]), payload)

        sql = MIGRATION.read_text(encoding="utf-8")
        for argument in (
            "p_user_id INTEGER", "p_address VARCHAR", "p_notes VARCHAR", "p_items JSONB",
        ):
            self.assertIn(argument, sql)
        self.assertIn("RETURNS INTEGER", sql)

    def test_checkout_uses_authenticated_user_and_backend_promotion_price(self):
        class FakeSupabase:
            def __init__(inner_self):
                inner_self.rpc_call = None

            def select(inner_self, table, **filters):
                if table == "products":
                    self.assertEqual(filters.get("active"), "eq.true")
                    return [self.product]
                if table == "orders":
                    return [{
                        "id": 31, "user_id": 17, "address": "Rua da Obra, 10",
                        "notes": "", "status": "pendente", "total": "150.00",
                    }]
                if table == "order_items":
                    return [{
                        "order_id": 31, "product_id": 4, "name": "Pão caseiro",
                        "price": "75.00", "quantity": 2,
                    }]
                if table == "users":
                    return [{
                        "id": 17, "name": "Cliente", "email": "cliente@example.com",
                        "password_hash": "unused", "address": "", "role": "user",
                        "active": True,
                    }]
                self.fail(f"Consulta inesperada: {table}")

            def rpc(inner_self, function, values):
                inner_self.rpc_call = (function, values)
                return 31

        client = FakeSupabase()
        result = create_order(
            OrderCreate(
                address="Rua da Obra, 10",
                items=[{"product_id": 4, "quantity": 1}, {"product_id": 4, "quantity": 1}],
            ),
            self.user,
            client,
        )

        name, payload = client.rpc_call
        self.assertEqual(name, "create_order_with_items")
        self.assertEqual(payload["p_user_id"], self.user.id)
        self.assertNotIn("p_user_id", OrderCreate.model_fields)
        self.assertEqual(payload["p_items"], [{
            "product_id": 4, "name": "Pão caseiro", "price": "75.00", "quantity": 2,
        }])
        self.assertEqual(result["status"], "pendente")
        self.assertEqual(result["items"][0]["price"], "75.00")

    def test_inactive_or_missing_product_is_rejected_before_rpc(self):
        class FakeSupabase:
            rpc_calls = 0

            def select(inner_self, table, **filters):
                return []

            def rpc(inner_self, *_args):
                inner_self.rpc_calls += 1

        client = FakeSupabase()
        with self.assertRaises(HTTPException) as error:
            create_order(
                OrderCreate(address="Rua da Obra, 10", items=[{"product_id": 4, "quantity": 1}]),
                self.user,
                client,
            )
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(client.rpc_calls, 0)

    def test_aggregate_quantity_over_limit_is_rejected_before_rpc(self):
        class FakeSupabase:
            rpc_calls = 0

            def select(inner_self, *_args, **_kwargs):
                self.fail("Produtos não deveriam ser consultados após quantidade inválida")

            def rpc(inner_self, *_args):
                inner_self.rpc_calls += 1

        client = FakeSupabase()
        with self.assertRaises(HTTPException) as error:
            create_order(
                OrderCreate(address="Rua da Obra, 10", items=[
                    {"product_id": 4, "quantity": 60},
                    {"product_id": 4, "quantity": 40},
                ]),
                self.user,
                client,
            )
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(client.rpc_calls, 0)

    def test_rpc_failure_stops_response_reads_and_function_is_atomic(self):
        class FailingSupabase:
            calls = []

            def select(inner_self, table, **_filters):
                inner_self.calls.append(("select", table))
                return [self.product] if table == "products" else []

            def rpc(inner_self, function, values):
                inner_self.calls.append(("rpc", function, values))
                raise HTTPException(500, "falha ao criar item")

        client = FailingSupabase()
        with self.assertRaises(HTTPException):
            create_order(
                OrderCreate(address="Rua da Obra, 10", items=[{"product_id": 4, "quantity": 1}]),
                self.user,
                client,
            )
        self.assertEqual([call[0] for call in client.calls], ["select", "rpc"])

        sql = MIGRATION.read_text(encoding="utf-8").upper()
        function_body = sql.split("AS $$", 1)[1].split("$$;", 1)[0]
        self.assertIn("INSERT INTO PUBLIC.ORDERS", function_body)
        self.assertIn("INSERT INTO PUBLIC.ORDER_ITEMS", function_body)
        self.assertNotIn("COMMIT", function_body)

    def test_rpc_is_private_and_existing_order_history_trigger_is_preserved(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("FROM PUBLIC", sql)
        self.assertIn("FROM anon", sql)
        self.assertIn("FROM authenticated", sql)
        self.assertIn("TO service_role", sql)
        self.assertIn("NOTIFY pgrst, 'reload schema'", sql)
        schema = Path(__file__).with_name("migration_supabase_v3.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE FUNCTION log_order_status()", schema)
        self.assertIn("AFTER INSERT OR UPDATE OF status ON orders", schema)


if __name__ == "__main__":
    unittest.main()