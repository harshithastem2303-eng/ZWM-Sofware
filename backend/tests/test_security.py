"""Security / negative tests: auth guards, invalid tokens, RBAC, bad requests."""


class TestMissingAuth:
    def test_profile_no_token(self, client):
        assert client.get("/api/user/profile").status_code == 401

    def test_stats_no_token(self, client):
        assert client.get("/api/user/stats").status_code == 401

    def test_upload_no_token(self, client):
        from io import BytesIO
        buf = BytesIO(b"data")
        r = client.post("/api/images/upload", files={"file": ("t.jpg", buf, "image/jpeg")})
        assert r.status_code == 401

    def test_annotations_no_token(self, client):
        r = client.post("/api/annotations/", json={"image_id": "x", "category_id": 1})
        assert r.status_code == 401

    def test_admin_users_no_token(self, client):
        assert client.get("/api/admin/users").status_code == 401

    def test_dataset_no_token(self, client):
        assert client.get("/api/dataset/stats").status_code == 401

    def test_ml_jobs_no_token(self, client):
        assert client.get("/api/ml/jobs").status_code == 401


class TestInvalidToken:
    def test_bad_token(self, client):
        headers = {"Authorization": "Bearer invalid-garbage-token"}
        assert client.get("/api/user/profile", headers=headers).status_code == 401

    def test_refresh_token_as_access(self, client, user_auth):
        headers = {"Authorization": f"Bearer {user_auth['refresh_token']}"}
        assert client.get("/api/user/profile", headers=headers).status_code == 401


class TestRBAC:
    def test_user_cannot_list_admin_users(self, client, user_auth):
        assert client.get("/api/admin/users", headers=user_auth["headers"]).status_code == 403

    def test_user_cannot_create_category(self, client, user_auth):
        r = client.post("/api/admin/categories", json={
            "class_name": "Blocked", "class_code": 999
        }, headers=user_auth["headers"])
        assert r.status_code == 403

    def test_user_cannot_view_analytics(self, client, user_auth):
        assert client.get("/api/admin/analytics/overview", headers=user_auth["headers"]).status_code == 403

    def test_user_cannot_train(self, client, user_auth):
        assert client.post("/api/ml/train", headers=user_auth["headers"]).status_code == 403

    def test_user_cannot_view_dataset(self, client, user_auth):
        assert client.get("/api/dataset/stats", headers=user_auth["headers"]).status_code == 403


class TestBadRequests:
    def test_register_empty_body(self, client):
        assert client.post("/api/auth/register", json={}).status_code == 422

    def test_login_empty_body(self, client):
        assert client.post("/api/auth/login", json={}).status_code == 422

    def test_annotation_missing_fields(self, client, user_auth):
        r = client.post("/api/annotations/", json={}, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_category_missing_fields(self, client, admin_auth):
        r = client.post("/api/admin/categories", json={}, headers=admin_auth["headers"])
        assert r.status_code == 422


class TestNotFound:
    def test_unknown_route(self, client):
        assert client.get("/api/nonexistent").status_code == 404

    def test_image_not_found(self, client, user_auth):
        assert client.get("/api/images/fake-id", headers=user_auth["headers"]).status_code == 404

    def test_annotation_not_found(self, client, user_auth):
        assert client.get("/api/annotations/fake-id", headers=user_auth["headers"]).status_code == 404

    def test_job_not_found(self, client, admin_auth):
        assert client.get("/api/ml/jobs/fake-id", headers=admin_auth["headers"]).status_code == 404

    def test_model_not_found(self, client, admin_auth):
        assert client.get("/api/ml/models/fake-id", headers=admin_auth["headers"]).status_code == 404


class TestWrongMethod:
    def test_delete_on_login(self, client):
        assert client.delete("/api/auth/login").status_code == 405

    def test_put_on_register(self, client):
        assert client.put("/api/auth/register").status_code == 405
