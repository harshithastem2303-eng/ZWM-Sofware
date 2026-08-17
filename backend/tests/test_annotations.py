"""Tests for annotation endpoints: CRUD + ownership checks."""
import uuid


class TestAnnotationCreate:
    def _setup_image_and_category(self, client, user_auth, admin_auth, test_image_file):
        """Helper: upload an image and create a category, return IDs."""
        # Upload image
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("ann_test.jpg", test_image_file, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        # Create category
        cat_name = f"AnnCat_{uuid.uuid4().hex[:6]}"
        cat_code = int(uuid.uuid4().int % 99000) + 1000
        r = client.post("/api/admin/categories", json={
            "class_name": cat_name, "class_code": cat_code
        }, headers=admin_auth["headers"])
        category_id = r.json()["category_id"]

        return image_id, category_id

    def test_create_annotation(self, client, user_auth, admin_auth, test_image_file):
        image_id, category_id = self._setup_image_and_category(
            client, user_auth, admin_auth, test_image_file
        )
        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "category_id": category_id,
        }, headers=user_auth["headers"])
        assert r.status_code == 201
        assert r.json()["image_id"] == image_id

    def test_create_annotation_with_label_data(self, client, user_auth, admin_auth, test_image_file):
        image_id, category_id = self._setup_image_and_category(
            client, user_auth, admin_auth, test_image_file
        )
        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "category_id": category_id,
            "label_data": {"points": [{"x": 10, "y": 20}]},
        }, headers=user_auth["headers"])
        assert r.status_code == 201
        assert r.json()["label_json_path"] is not None

    def test_create_annotation_bad_image(self, client, user_auth):
        r = client.post("/api/annotations/", json={
            "image_id": "nonexistent", "category_id": 1,
        }, headers=user_auth["headers"])
        assert r.status_code == 404

    def test_create_annotation_no_auth(self, client):
        r = client.post("/api/annotations/", json={
            "image_id": "x", "category_id": 1,
        })
        assert r.status_code == 401


class TestAnnotationRead:
    def test_get_annotation(self, client, user_auth, admin_auth, test_image_file):
        # Setup
        r = client.post(
            "/api/images/upload", headers=user_auth["headers"],
            files={"file": ("read_ann.jpg", test_image_file, "image/jpeg")},
        )
        image_id = r.json()["image_id"]
        cat_name = f"ReadCat_{uuid.uuid4().hex[:6]}"
        r = client.post("/api/admin/categories", json={
            "class_name": cat_name, "class_code": int(uuid.uuid4().int % 99000) + 1000
        }, headers=admin_auth["headers"])
        category_id = r.json()["category_id"]

        r = client.post("/api/annotations/", json={
            "image_id": image_id, "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        # Get by ID
        r = client.get(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r.status_code == 200
        assert r.json()["annotation_id"] == ann_id

    def test_get_annotations_for_image(self, client, user_auth, admin_auth, test_image_file):
        r = client.post(
            "/api/images/upload", headers=user_auth["headers"],
            files={"file": ("img_ann.jpg", test_image_file, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        r = client.get(f"/api/annotations/image/{image_id}", headers=user_auth["headers"])
        assert r.status_code == 200
        assert "annotations" in r.json()

    def test_get_annotation_not_found(self, client, user_auth):
        r = client.get("/api/annotations/nonexistent", headers=user_auth["headers"])
        assert r.status_code == 404


class TestAnnotationDelete:
    def test_delete_annotation(self, client, user_auth, admin_auth, test_image_file):
        r = client.post(
            "/api/images/upload", headers=user_auth["headers"],
            files={"file": ("del_ann.jpg", test_image_file, "image/jpeg")},
        )
        image_id = r.json()["image_id"]
        cat_name = f"DelCat_{uuid.uuid4().hex[:6]}"
        r = client.post("/api/admin/categories", json={
            "class_name": cat_name, "class_code": int(uuid.uuid4().int % 99000) + 1000
        }, headers=admin_auth["headers"])
        category_id = r.json()["category_id"]

        r = client.post("/api/annotations/", json={
            "image_id": image_id, "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r = client.delete(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r.status_code == 200

        r = client.get(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r.status_code == 404
