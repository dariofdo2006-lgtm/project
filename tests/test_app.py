import importlib
import os
import re
import sys
import tempfile
import unittest


class BudgetCalendarAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_file = tempfile.NamedTemporaryFile(delete=False)
        cls.db_file.close()

        os.environ["DISABLE_FIREBASE"] = "1"
        os.environ["SQLITE_DB_NAME"] = cls.db_file.name
        os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
        os.environ["SHOW_BACKEND_BADGE"] = "0"

        if "app" in sys.modules:
            old_db = getattr(sys.modules["app"], "db", None)
            old_conn = getattr(old_db, "conn", None)
            if old_conn is not None:
                old_conn.close()
            cls.app_module = importlib.reload(sys.modules["app"])
        else:
            import app
            cls.app_module = app
        cls.client = cls.app_module.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db = getattr(cls.app_module, "db", None)
        conn = getattr(db, "conn", None)
        if conn is not None:
            conn.close()
        try:
            os.unlink(cls.db_file.name)
        except FileNotFoundError:
            pass

    def csrf_token(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf-token" content="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode("utf-8")

    def register_and_login(self, username="dario", password="safe-pass-123"):
        token = self.csrf_token()
        response = self.client.post(
            "/register",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            "/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        return token

    def test_health_reports_sqlite_when_firebase_disabled(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["backend"], "sqlite")
        self.assertFalse(data["firebase"])

    def test_register_login_and_add_expense(self):
        token = self.register_and_login("expense-user", "safe-pass-123")
        response = self.client.post(
            "/api/expense",
            json={
                "date": "2026-05-15",
                "amount": "42.50",
                "category": "Food",
                "name": "Lunch",
            },
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_plaintext_passwords_are_rejected(self):
        db = self.app_module.db
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("plain-user", "secret"))

        token = self.csrf_token()
        response = self.client.post(
            "/login",
            json={"username": "plain-user", "password": "secret"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["success"])

    def test_mutating_routes_require_csrf(self):
        self.register_and_login("csrf-user", "safe-pass-123")
        response = self.client.post(
            "/api/expense",
            json={
                "date": "2026-05-15",
                "amount": "10",
                "category": "Food",
                "name": "No token",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_logout_requires_post_and_csrf(self):
        token = self.register_and_login("logout-user", "safe-pass-123")

        get_response = self.client.get("/logout")
        self.assertEqual(get_response.status_code, 405)

        post_without_csrf = self.client.post("/logout")
        self.assertEqual(post_without_csrf.status_code, 403)

        post_with_csrf = self.client.post("/logout", data={"csrf_token": token})
        self.assertEqual(post_with_csrf.status_code, 302)
        self.assertIn("/login", post_with_csrf.headers["Location"])

    def test_invalid_transaction_payloads_are_rejected(self):
        token = self.register_and_login("validation-user", "safe-pass-123")

        invalid_date = self.client.post(
            "/api/expense",
            json={
                "date": "not-a-date",
                "amount": "10",
                "category": "Food",
                "name": "Bad date",
            },
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(invalid_date.status_code, 400)

        invalid_amount = self.client.post(
            "/api/expense",
            json={
                "date": "2026-05-15",
                "amount": "-10",
                "category": "Food",
                "name": "Bad amount",
            },
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(invalid_amount.status_code, 400)


if __name__ == "__main__":
    unittest.main()
