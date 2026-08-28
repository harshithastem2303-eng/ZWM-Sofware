"""Tests for admin endpoints: users, categories, validation, analytics."""
import uuid


class TestAdminUsers:
    def test_list_users(self, client, admin_auth):
        r = client.get("/api/admin/users", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "users" in r.json()

    def test_list_users_non_admin(self, client, user_auth):
        r = client.get("/api/admin/users", headers=user_auth["headers"])
        assert r.status_code == 403


class TestAdminCategories:
    def test_create_category(self, client, admin_auth):
        name = f"Cat_{uuid.uuid4().hex[:6]}"
        code = int(uuid.uuid4().int % 99000) + 1000
        r = client.post("/api/admin/categories", json={
            "class_name": name, "class_code": code
        }, headers=admin_auth["headers"])
        assert r.status_code == 201
        assert "category_id" in r.json()

    def test_create_category_duplicate(self, client, admin_auth):
        name = f"DupCat_{uuid.uuid4().hex[:6]}"
        code = int(uuid.uuid4().int % 99000) + 1000
        client.post("/api/admin/categories", json={
            "class_name": name, "class_code": code
        }, headers=admin_auth["headers"])
        r = client.post("/api/admin/categories", json={
            "class_name": name, "class_code": code + 1
        }, headers=admin_auth["headers"])
        assert r.status_code == 409

    def test_list_categories(self, client, admin_auth):
        r = client.get("/api/admin/categories", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "categories" in r.json()


class TestAdminValidation:
    def test_validation_queue(self, client, admin_auth):
        r = client.get("/api/admin/validation-queue", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "queue" in r.json()

    def test_approve_nonexistent(self, client, admin_auth):
        r = client.post(
            "/api/admin/images/fake-id/approve",
            json={"action": "approve"},
            headers=admin_auth["headers"],
        )
        assert r.status_code == 404

    def test_approve_invalid_action(self, client, admin_auth, user_auth, test_image_file):
        # Upload an image first
        upload_r = client.post(
            "/api/images/upload", headers=user_auth["headers"],
            files={"file": ("admin_test.jpg", test_image_file, "image/jpeg")},
        )
        if upload_r.status_code == 201:
            image_id = upload_r.json()["image_id"]
            r = client.post(
                f"/api/admin/images/{image_id}/approve",
                json={"action": "maybe"},
                headers=admin_auth["headers"],
            )
            assert r.status_code == 400


class TestAdminAnalytics:
    def test_analytics_overview(self, client, admin_auth):
        r = client.get("/api/admin/analytics/overview", headers=admin_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "total_users" in data
        assert "total_images" in data
        assert "total_annotations" in data

    def test_analytics_leaderboard(self, client, admin_auth):
        r = client.get("/api/admin/analytics/leaderboard", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "leaderboard" in r.json()

    def test_analytics_no_auth(self, client):
        r = client.get("/api/admin/analytics/overview")
        assert r.status_code == 401

    def test_analytics_non_admin(self, client, user_auth):
        r = client.get("/api/admin/analytics/overview", headers=user_auth["headers"])
        assert r.status_code == 403


class TestAdminAuth:
    def test_admin_login_success(self, client):
        r = client.post("/api/admin/login", json={
            "email": "admin@gmail.com",
            "password": "user123"
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["role"] == "admin"

        # Verify token works for a protected admin endpoint
        headers = {"Authorization": f"Bearer {data['access_token']}"}
        users_r = client.get("/api/admin/users", headers=headers)
        assert users_r.status_code == 200

    def test_admin_login_wrong_email(self, client):
        r = client.post("/api/admin/login", json={
            "email": "wrongadmin@gmail.com",
            "password": "user123"
        })
        assert r.status_code == 401

    def test_admin_login_wrong_password(self, client):
        r = client.post("/api/admin/login", json={
            "email": "admin@gmail.com",
            "password": "WrongPassword123"
        })
        assert r.status_code == 401

    def test_create_admin_success(self, client, admin_auth):
        r = client.post("/api/admin/create", json={
            "admin_id": "New Admin User",
            "email": "newadmin@gmail.com",
            "role": "Super Admin"
        }, headers=admin_auth["headers"])
        assert r.status_code == 201
        data = r.json()
        assert data["message"] == "Admin created successfully"
        assert data["email"] == "newadmin@gmail.com"
        assert "temp_password" in data

    def test_create_admin_duplicate(self, client, admin_auth):
        # Create it first (might be created in the previous test, but let's be sure or let it use the existing one)
        client.post("/api/admin/create", json={
            "admin_id": "Dup Admin User",
            "email": "dupadmin@gmail.com",
            "role": "Super Admin"
        }, headers=admin_auth["headers"])
        
        r = client.post("/api/admin/create", json={
            "admin_id": "Dup Admin User",
            "email": "dupadmin@gmail.com",
            "role": "Super Admin"
        }, headers=admin_auth["headers"])
        assert r.status_code == 409

    def test_create_admin_no_auth(self, client):
        r = client.post("/api/admin/create", json={
            "admin_id": "Unauth Admin",
            "email": "unauth@gmail.com",
            "role": "Admin"
        })
        assert r.status_code == 401

    def test_create_admin_non_admin(self, client, user_auth):
        r = client.post("/api/admin/create", json={
            "admin_id": "NonAdmin creator",
            "email": "nonadmin@gmail.com",
            "role": "Admin"
        }, headers=user_auth["headers"])
        assert r.status_code == 403


