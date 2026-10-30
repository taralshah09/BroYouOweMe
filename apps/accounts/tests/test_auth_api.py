import json

from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User


@override_settings(SECURE_SSL_REDIRECT=False, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ApiTests(TestCase):
    def post(self, path, data):
        return self.client.post(path, json.dumps(data), content_type="application/json")

    def signup(self, username="Mohit", email="mohit@example.com"):
        return self.post("/users", {"username": username, "email": email, "password": "a-good-password-123"})

    def test_signup_hashes_password_and_starts_session(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get()
        self.assertTrue(user.check_password("a-good-password-123"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)
        self.assertEqual(self.client.get("/users").json(), [{"id": user.id, "username": "Mohit"}])
        self.assertNotIn("email", self.client.get("/users").json()[0])

    def test_case_insensitive_uniqueness_and_validation(self):
        self.assertEqual(self.signup().status_code, 201)
        for data in [
            {"username": "mOhIt", "email": "other@example.com", "password": "a-good-password-123"},
            {"username": "other", "email": "MOHIT@example.com", "password": "a-good-password-123"},
            {"username": "other", "email": "bad", "password": "short"},
            {"username": "email@example.com", "email": "other@example.com", "password": "a-good-password-123"},
        ]:
            self.assertEqual(self.post("/signup", data).status_code, 400)
        self.assertEqual(User.objects.count(), 1)
        for field in ["username", "email"]:
            data = {"username": "new", "email": "new@example.com"}
            data[field] = getattr(User.objects.get(), field).upper()
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.create_user(**data)

    def test_email_and_username_login_and_post_only_logout(self):
        self.signup()
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.post("/logout", {}).status_code, 200)
        for identity in ["mOhIt", "MOHIT@example.com"]:
            self.assertEqual(self.post("/login", {"username": identity, "password": "wrong"}).status_code, 400)
            self.assertEqual(self.post("/login", {"username": identity, "password": "a-good-password-123"}).status_code, 200)
            self.post("/logout", {})

    def test_api_assignment_end_to_end(self):
        mohit_id = self.signup().json()["id"]
        rahul_id = self.signup("Rahul", "rahul@example.com").json()["id"]
        ankit_id = self.signup("Ankit", "ankit@example.com").json()["id"]
        self.post("/login", {"username": "Mohit", "password": "a-good-password-123"})
        response = self.post("/groups", {"name": "Goa Trip"})
        self.assertEqual(response.status_code, 201)
        group_id = response.json()["id"]
        for pk in [rahul_id, ankit_id]:
            self.assertEqual(self.post(f"/groups/{group_id}/members", {"user_id": pk}).status_code, 201)
        self.assertEqual(len(self.client.get(f"/groups/{group_id}/members").json()), 3)
        response = self.post("/expenses", {"group_id": group_id, "paid_by": mohit_id, "amount": 1200, "description": "Dinner"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.get(f"/groups/{group_id}/balances").json(), {"Rahul": {"owes": {"Mohit": 400}}, "Ankit": {"owes": {"Mohit": 400}}})
        self.assertEqual(self.client.get(f"/groups/{group_id}/expenses").json()[0]["paid_by"], "Mohit")
        splits = self.client.get(f"/expenses/{response.json()['id']}").json()["splits"]
        self.assertEqual(len(splits), 3)
        self.assertEqual({split["username"] for split in splits}, {"Mohit", "Rahul", "Ankit"})
        self.assertEqual(len(self.client.get("/groups").json()), 1)

    def test_json_decimals_remain_exact_and_future_features_rejected(self):
        mohit_id = self.signup().json()["id"]
        group_id = self.post("/groups", {"name": "Solo"}).json()["id"]
        response = self.client.post("/expenses", f'{{"group_id": {group_id}, "paid_by": {mohit_id}, "amount": 1.01, "description": "Tea"}}', content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["amount"], "1.01")
        self.assertEqual(self.post("/expenses", {"participants": [mohit_id]}).status_code, 400)

    def test_auth_membership_and_admin_checks(self):
        for path in ["/users", "/groups", "/groups/1/members", "/groups/1/expenses", "/groups/1/balances", "/balances", "/expenses/1"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.signup()
        group_id = self.post("/groups", {"name": "Private"}).json()["id"]
        outsider_id = self.signup("Outsider", "outsider@example.com").json()["id"]
        self.assertEqual(self.client.get("/groups").json(), [])
        for suffix in ["", "/members", "/expenses", "/balances"]:
            self.assertEqual(self.client.get(f"/groups/{group_id}{suffix}").status_code, 403)
        self.assertEqual(self.post("/expenses", {"group_id": group_id, "paid_by": outsider_id, "amount": 12, "description": "No"}).status_code, 403)

    def test_bad_payloads_and_missing_groups(self):
        self.signup()
        for body in ["{", "[]", "null", '{"name":1.2e1}']:
            self.assertEqual(self.client.post("/groups", body, content_type="application/json").status_code, 400)
        for value in [True, -1, "1.0", 1.5, "999999999999999999999"]:
            self.assertEqual(self.post("/expenses", {"group_id": value}).status_code, 400)
        self.assertEqual(self.client.get("/groups/999999").status_code, 404)
        self.assertEqual(self.client.get("/groups/999999999999999999999").status_code, 400)

    def test_html_pages_and_form_workflow(self):
        for path in ["/", "/signup", "/login"]:
            self.assertEqual(self.client.get(path, HTTP_ACCEPT="text/html").status_code, 200)
        response = self.client.post("/signup", {"username": "Mohit", "email": "mohit@example.com", "password1": "a-good-password-123", "password2": "a-good-password-123"}, HTTP_ACCEPT="text/html")
        self.assertRedirects(response, "/groups", fetch_redirect_response=False)
        self.client.post("/groups", {"name": "Goa"}, HTTP_ACCEPT="text/html")
        group_id = self.client.get("/groups").json()[0]["id"]
        self.client.post("/expenses", {"group_id": group_id, "paid_by": User.objects.get().id, "amount": "5.00", "description": "Tea"}, HTTP_ACCEPT="text/html")
        expense_id = self.client.get(f"/groups/{group_id}/expenses").json()[0]["id"]
        for path in ["/groups", "/users", "/balances", f"/groups/{group_id}", f"/groups/{group_id}/members", f"/groups/{group_id}/expenses", f"/groups/{group_id}/balances", f"/expenses/{expense_id}"]:
            self.assertEqual(self.client.get(path, HTTP_ACCEPT="text/html").status_code, 200, path)

    def test_csrf_is_required_for_json_and_html(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/signup", {"username": "unsafe"}).status_code, 403)
        self.assertEqual(client.post("/login", "{}", content_type="application/json").status_code, 403)
        client.get("/signup", HTTP_ACCEPT="text/html")
        response = client.post("/signup", json.dumps({"username": "safe", "email": "safe@example.com", "password": "a-good-password-123"}), content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 201, response.content)
