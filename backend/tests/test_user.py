"""Tests for user endpoints: profile, stats, history, rewards."""


class TestUserProfile:
    def test_get_profile(self, client, user_auth):
        r = client.get("/api/user/profile", headers=user_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == user_auth["user_id"]
        assert "email" in data
        assert "reward_points" in data

    def test_get_profile_no_auth(self, client):
        r = client.get("/api/user/profile")
        assert r.status_code == 401


class TestUserStats:
    def test_get_stats(self, client, user_auth):
        r = client.get("/api/user/stats", headers=user_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "total_uploads" in data
        assert "validated_images" in data
        assert "pending_images" in data
        assert "reward_points" in data


class TestUserHistory:
    def test_get_history(self, client, user_auth):
        r = client.get("/api/user/history", headers=user_auth["headers"])
        assert r.status_code == 200
        assert "history" in r.json()


class TestUserRewards:
    def test_get_rewards(self, client, user_auth):
        r = client.get("/api/user/rewards", headers=user_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "reward_points" in data
        assert "total_images_contributed" in data
