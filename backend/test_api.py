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

from backend.main import SessionLocal, User, app


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
        self.assertEqual(self.client_context.post(
            "/auth/register",
            json={"name": "Outro", "email": "test@example.com", "password": "secret123"},
        ).status_code, 409)
        self.assertEqual(self.client_context.post(
            "/auth/login", json={"email": "test@example.com", "password": "wrong"}
        ).status_code, 401)

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


if __name__ == "__main__":
    unittest.main()
