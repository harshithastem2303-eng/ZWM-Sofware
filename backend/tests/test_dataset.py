"""Tests for dataset endpoints: stats, readiness."""


class TestDatasetStats:
    def test_get_stats(self, client, admin_auth):
        r = client.get("/api/dataset/stats", headers=admin_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "total_images" in data
        assert "categories" in data
        assert "threshold" in data

    def test_stats_non_admin(self, client, user_auth):
        r = client.get("/api/dataset/stats", headers=user_auth["headers"])
        assert r.status_code == 403


class TestDatasetReadiness:
    def test_get_readiness(self, client, admin_auth):
        r = client.get("/api/dataset/readiness", headers=admin_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "ready" in data
        assert "threshold" in data
        assert "categories" in data

    def test_readiness_non_admin(self, client, user_auth):
        r = client.get("/api/dataset/readiness", headers=user_auth["headers"])
        assert r.status_code == 403
