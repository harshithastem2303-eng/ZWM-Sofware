"""Tests for image endpoints: upload, list, get, delete."""
import os


class TestImageUpload:
    def test_upload_valid_image(self, client, user_auth, test_image_file):
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("test.jpg", test_image_file, "image/jpeg")},
        )
        assert r.status_code == 201
        data = r.json()
        assert "image_id" in data
        assert data["status"] == "uploaded"
        assert data["validation"]["valid"] is True

    def test_upload_small_image_rejected(self, client, user_auth, small_image_file):
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("small.jpg", small_image_file, "image/jpeg")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "rejected"
        assert data["validation"]["valid"] is False

    def test_upload_invalid_extension(self, client, user_auth):
        from io import BytesIO
        buf = BytesIO(b"not a real image")
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("test.txt", buf, "text/plain")},
        )
        assert r.status_code == 400

    def test_upload_no_auth(self, client, test_image_file):
        r = client.post(
            "/api/images/upload",
            files={"file": ("test.jpg", test_image_file, "image/jpeg")},
        )
        assert r.status_code == 401


class TestImageList:
    def test_list_images(self, client, user_auth):
        r = client.get("/api/images/", headers=user_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "images" in data
        assert "count" in data


class TestImageGet:
    def test_get_image(self, client, user_auth, test_image_file):
        # Upload first
        upload_r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("get_test.jpg", test_image_file, "image/jpeg")},
        )
        image_id = upload_r.json()["image_id"]

        r = client.get(f"/api/images/{image_id}", headers=user_auth["headers"])
        assert r.status_code == 200
        assert r.json()["image_id"] == image_id

    def test_get_image_not_found(self, client, user_auth):
        r = client.get("/api/images/nonexistent-id", headers=user_auth["headers"])
        assert r.status_code == 404


class TestImageDelete:
    def test_delete_image(self, client, user_auth, test_image_file):
        upload_r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("del_test.jpg", test_image_file, "image/jpeg")},
        )
        image_id = upload_r.json()["image_id"]

        r = client.delete(f"/api/images/{image_id}", headers=user_auth["headers"])
        assert r.status_code == 200

        # Verify deleted
        r = client.get(f"/api/images/{image_id}", headers=user_auth["headers"])
        assert r.status_code == 404

    def test_delete_not_found(self, client, user_auth):
        r = client.delete("/api/images/nonexistent-id", headers=user_auth["headers"])
        assert r.status_code == 404
