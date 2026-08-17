"""Tests for auth endpoints: register, login, verify-email, refresh, logout, forgot/reset password."""
import uuid


class TestRegister:
    def test_register_success(self, client):
        email = f"reg_{uuid.uuid4().hex[:8]}@test.com"
        r = client.post("/api/auth/register", json={
            "email": email, "password": "Pass123!", "full_name": "Reg User"
        })
        assert r.status_code == 201
        assert "user_id" in r.json()

    def test_register_duplicate(self, client, user_auth):
        r = client.post("/api/auth/register", json={
            "email": user_auth["email"], "password": "Pass123!", "full_name": "Dup"
        })
        assert r.status_code == 409

    def test_register_invalid_email(self, client):
        r = client.post("/api/auth/register", json={
            "email": "not-email", "password": "Pass123!"
        })
        assert r.status_code == 422

    def test_register_missing_fields(self, client):
        r = client.post("/api/auth/register", json={})
        assert r.status_code == 422


class TestLogin:
    def test_login_success(self, client, user_auth):
        r = client.post("/api/auth/login", json={
            "email": user_auth["email"], "password": user_auth["password"]
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["role"] in ["user", "admin"]

    def test_login_wrong_password(self, client, user_auth):
        r = client.post("/api/auth/login", json={
            "email": user_auth["email"], "password": "wrong"
        })
        assert r.status_code == 401

    def test_login_nonexistent(self, client):
        r = client.post("/api/auth/login", json={
            "email": "ghost@example.com", "password": "anything"
        })
        assert r.status_code == 401


class TestVerifyEmail:
    def test_verify_email_success(self, client, db):
        # Register a new user
        email = f"verify_{uuid.uuid4().hex[:8]}@test.com"
        client.post("/api/auth/register", json={
            "email": email, "password": "Pass123!", "full_name": "Verify User"
        })
        # Get the token from DB
        from app.models.user import User
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        token = user.verification_token

        r = client.post("/api/auth/verify-email", json={"token": token})
        assert r.status_code == 200

        db.refresh(user)
        assert user.is_email_verified is True
        assert user.verification_token is None

    def test_verify_email_invalid_token(self, client):
        r = client.post("/api/auth/verify-email", json={"token": "invalid-token"})
        assert r.status_code == 400


class TestRefreshLogout:
    def test_refresh(self, client, user_auth):
        r = client.post("/api/auth/refresh", headers=user_auth["headers"])
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_logout(self, client, user_auth):
        r = client.post("/api/auth/logout", headers=user_auth["headers"])
        assert r.status_code == 200


class TestForgotResetPassword:
    def test_forgot_password(self, client, user_auth):
        r = client.post("/api/auth/forgot-password", json={"email": user_auth["email"]})
        assert r.status_code == 200

    def test_forgot_password_nonexistent(self, client):
        r = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
        assert r.status_code == 200  # Always 200 for security

    def test_reset_password(self, client, db):
        email = f"reset_{uuid.uuid4().hex[:8]}@test.com"
        client.post("/api/auth/register", json={
            "email": email, "password": "OldPass123!", "full_name": "Reset User"
        })
        # Trigger forgot password
        client.post("/api/auth/forgot-password", json={"email": email})

        from app.models.user import User
        user = db.query(User).filter(User.email == email).first()
        token = user.verification_token

        # Reset
        r = client.post("/api/auth/reset-password", json={
            "token": token, "new_password": "NewPass456!"
        })
        assert r.status_code == 200

        # Login with new password
        r = client.post("/api/auth/login", json={
            "email": email, "password": "NewPass456!"
        })
        assert r.status_code == 200

    def test_reset_password_invalid_token(self, client):
        r = client.post("/api/auth/reset-password", json={
            "token": "reset:invalid", "new_password": "NewPass!"
        })
        assert r.status_code == 400
