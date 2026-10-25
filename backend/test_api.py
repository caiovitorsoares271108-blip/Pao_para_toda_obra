import os
import tempfile
import unittest

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
os.environ["ENVIRONMENT"] = "test"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from backend.main import SessionLocal, app, _seed_catalog
from backend.database import Product, User


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        os.unlink(_db_file.name)

    def test_registration_login_and_duplicate_email(self):
        response = self.client_context.post(
            "/auth/register",
            json={"name": "Cliente", "email": "test@example.com", "password": "secret123"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("httponly", response.headers.get("set-cookie", "").lower())
        self.assertEqual(self.client_context.get("/auth/me").json()["email"], "test@example.com")
        self.assertEqual(self.client_context.post(
            "/auth/register",
            json={"name": "Outro", "email": "test@example.com", "password": "secret123"},
        ).status_code, 409)
        self.assertEqual(self.client_context.post(
            "/auth/login", json={"email": "test@example.com", "password": "wrong"}
        ).status_code, 401)
        self.assertEqual(self.client_context.post("/auth/logout").status_code, 200)
        self.assertEqual(self.client_context.get("/auth/me").status_code, 401)

    def test_admin_manages_accounts_and_customer_cannot_escalate(self):
        admin = self.client_context.post("/auth/register", json={
            "name": "Administrador", "email": "root@example.com", "password": "secret123"
        }).json()
        customer = self.client_context.post("/auth/register", json={
            "name": "Cliente", "email": "managed@example.com", "password": "secret123"
        }).json()
        customer_headers = {"Authorization": f"Bearer {customer['access_token']}"}
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        with SessionLocal() as db:
            db.get(User, admin["user"]["id"]).role = "admin"
            db.commit()
        self.assertEqual(self.client_context.get("/auth/accounts", headers=customer_headers).status_code, 403)
        self.assertEqual(self.client_context.patch(
            f"/auth/accounts/{customer['user']['id']}", headers=customer_headers,
            json={"role": "admin"}
        ).status_code, 403)
        updated = self.client_context.patch(
            f"/auth/accounts/{customer['user']['id']}", headers=admin_headers,
            json={"name": "Cliente Atualizado", "active": False}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["active"])
        self.assertEqual(self.client_context.get("/auth/me", headers=customer_headers).status_code, 401)

    def test_demo_quick_login_is_disabled_outside_development(self):
        self.assertEqual(
            self.client_context.get("/auth/demo-accounts").json(), {"accounts": []}
        )
        self.assertEqual(
            self.client_context.post("/auth/demo-login", json={"role": "admin"}).status_code,
            404,
        )

    def test_seed_is_idempotent_and_does_not_overwrite_admin_changes(self):
        with SessionLocal() as db:
            _seed_catalog(db)
            _seed_catalog(db)
            count = db.query(Product).filter(Product.seed_key.is_not(None)).count()
            frances = db.scalar(db.query(Product).filter(Product.seed_key == "pao-frances").statement)
            frances.price = 1.25
            db.commit()
        with SessionLocal() as db:
            _seed_catalog(db)
            self.assertEqual(db.query(Product).filter(Product.seed_key.is_not(None)).count(), 21)
            self.assertEqual(db.query(Product).filter(Product.seed_key.is_not(None)).count(), count)
            frances = db.scalar(db.query(Product).filter(Product.seed_key == "pao-frances").statement)
            self.assertEqual(float(frances.price), 1.25)

    def test_promotion_period_is_applied_by_backend_only_when_active(self):
        admin = self.client_context.post("/auth/register", json={
            "name": "Administrador", "email": "promo-admin@example.com", "password": "secret123"
        }).json()
        customer = self.client_context.post("/auth/register", json={
            "name": "Cliente", "email": "promo-client@example.com", "password": "secret123"
        }).json()
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        customer_headers = {"Authorization": f"Bearer {customer['access_token']}"}
        with SessionLocal() as db:
            db.get(User, admin["user"]["id"]).role = "admin"
            db.commit()
        product = self.client_context.post("/products", headers=admin_headers, json={
            "name": "Produto promocional", "description": "Teste", "price": 100,
            "category": "Outros", "promo": {"active": True, "type": "percent", "value": 25},
            "promo_starts_at": "2020-01-01T00:00:00Z", "promo_ends_at": "2020-01-02T00:00:00Z"
        })
        self.assertEqual(product.status_code, 201)
        order = self.client_context.post("/orders", headers=customer_headers, json={
            "address": "Rua Promocional, 1", "items": [{"product_id": product.json()["id"], "quantity": 1}]
        })
        self.assertEqual(order.status_code, 201)
        self.assertEqual(order.json()["total"], 100)
        self.assertEqual(order.json()["items"][0]["price"], 100)

    def test_admin_product_order_total_and_inactive_rejection(self):
        customer = self.client_context.post(
            "/auth/register",
            json={"name": "Cliente Dois", "email": "two@example.com", "password": "secret123"},
        ).json()
        admin = self.client_context.post(
            "/auth/register",
            json={"name": "Admin", "email": "admin@example.com", "password": "secret123"},
        ).json()
        with SessionLocal() as db:
            db.get(User, admin["user"]["id"]).role = "admin"
            db.commit()
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        customer_headers = {"Authorization": f"Bearer {customer['access_token']}"}
        product = self.client_context.post(
            "/products",
            headers=admin_headers,
            json={
                "name": "Produto", "description": "Teste", "price": 10,
                "category": "Pães", "promo": {"active": True, "type": "percent", "value": 10},
            },
        )
        self.assertEqual(product.status_code, 201)
        product_id = product.json()["id"]
        unavailable = {**product.json(), "active": False}
        self.assertEqual(self.client_context.patch(
            f"/products/{product_id}", headers=admin_headers, json=unavailable
        ).status_code, 200)
        self.assertEqual(self.client_context.get("/products").json(), [])
        available = {**product.json(), "active": True}
        self.assertEqual(self.client_context.patch(
            f"/products/{product_id}", headers=admin_headers, json=available
        ).status_code, 200)
        order = self.client_context.post(
            "/orders",
            headers=customer_headers,
            json={"address": "Rua Teste, 1", "items": [{"product_id": product_id, "quantity": 2}]},
        )
        self.assertEqual(order.status_code, 201)
        self.assertEqual(order.json()["total"], 18.0)
        self.assertEqual(self.client_context.patch(
            f"/orders/{order.json()['id']}/status",
            headers=customer_headers,
            json={"status": "entregue"},
        ).status_code, 403)
        self.assertEqual(self.client_context.delete(
            f"/products/{product_id}", headers=admin_headers
        ).status_code, 200)
        self.assertEqual(self.client_context.get("/products").json(), [])

    def test_orders_are_private_and_keep_product_price_snapshot(self):
        admin = self.client_context.post("/auth/register", json={
            "name": "Administrador", "email": "orders-admin@example.com", "password": "secret123"
        }).json()
        customer = self.client_context.post("/auth/register", json={
            "name": "Cliente", "email": "orders-customer@example.com", "password": "secret123"
        }).json()
        other_customer = self.client_context.post("/auth/register", json={
            "name": "Outro Cliente", "email": "orders-other@example.com", "password": "secret123"
        }).json()
        admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
        customer_headers = {"Authorization": f"Bearer {customer['access_token']}"}
        other_headers = {"Authorization": f"Bearer {other_customer['access_token']}"}
        with SessionLocal() as db:
            db.get(User, admin["user"]["id"]).role = "admin"
            db.commit()

        product = self.client_context.post("/products", headers=admin_headers, json={
            "name": "Pão para snapshot", "price": 8.50, "category": "Pães"
        })
        self.assertEqual(product.status_code, 201)
        self.assertEqual(self.client_context.patch(
            f"/products/{product.json()['id']}", headers=customer_headers,
            json={"price": 0.01},
        ).status_code, 403)
        order_response = self.client_context.post("/orders", headers=customer_headers, json={
            "address": "Rua do Cliente, 123",
            "items": [{"product_id": product.json()["id"], "quantity": 2}],
        })
        self.assertEqual(order_response.status_code, 201)
        order = order_response.json()
        self.assertIn("updated_at", order)
        self.assertEqual(order["items"][0]["price"], 8.5)
        self.assertEqual(order["total"], 17.0)

        self.assertEqual(self.client_context.get("/orders", headers=other_headers).json(), [])
        self.assertEqual(
            self.client_context.get("/orders", headers=customer_headers).json()[0]["address"],
            "Rua do Cliente, 123",
        )
        admin_orders = self.client_context.get("/orders", headers=admin_headers).json()
        self.assertIn(order["id"], [item["id"] for item in admin_orders])

        self.assertEqual(self.client_context.patch(
            f"/products/{product.json()['id']}", headers=admin_headers,
            json={"price": 12.0},
        ).status_code, 200)
        saved_order = self.client_context.get("/orders", headers=customer_headers).json()[0]
        self.assertEqual(saved_order["items"][0]["name"], "Pão para snapshot")
        self.assertEqual(saved_order["items"][0]["price"], 8.5)
        self.assertEqual(saved_order["total"], 17.0)

        updated = self.client_context.patch(
            f"/orders/{order['id']}/status", headers=admin_headers,
            json={"status": "preparando"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "preparando")
        self.assertGreaterEqual(updated.json()["updated_at"], order["updated_at"])
        self.assertEqual(self.client_context.patch(
            f"/orders/{order['id']}/status", headers=admin_headers,
            json={"status": "pendente"},
        ).status_code, 409)


if __name__ == "__main__":
    unittest.main()
