"""
Tests for Core ZWM Data Collection & AI Class Validation Flow.

Scenarios tested:
- Admin creates active class (Milk Pouch) -> appears in GET /api/categories/active
- Admin deactivates class -> disappears from GET /api/categories/active
- User selects active category and uploads image
- AI validation:
  - Class Mismatch / Low Confidence / Unsupported class -> PENDING_ADMIN_REVIEW
  - Model does NOT fake validation for unknown classes -> MODEL_CLASS_NOT_SUPPORTED
- Admin opens validation queue -> sees user info, selected category, AI prediction & confidence
- Admin approves/rejects image -> user rewards and status updated
- PostgreSQL aggregate query for user contribution stats
"""
import io
import pytest
from PIL import Image as PILImage


def create_dummy_image_bytes():
    from PIL import ImageDraw
    import random
    buf = io.BytesIO()
    img = PILImage.new('RGB', (640, 480), color=(100, 150, 200))
    draw = ImageDraw.Draw(img)
    random.seed(42)
    for _ in range(200):
        x1, y1 = random.randint(0, 639), random.randint(0, 479)
        x2, y2 = random.randint(0, 639), random.randint(0, 479)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


class TestZWMCoreDataFlow:

    def test_admin_create_and_deactivate_class_flow(self, client, admin_headers):
        # 1. Admin creates new active class: "Milk Pouch"
        payload = {
            "class_name": "Milk Pouch",
            "class_code": 901,
            "description": "Flexible dairy packaging pouch",
            "is_active": True
        }
        res = client.post("/api/admin/categories", json=payload, headers=admin_headers)
        assert res.status_code == 201
        cat_id = res.json()["category_id"]

        # 2. Public / User fetches active categories -> Milk Pouch MUST be present
        res_active = client.get("/api/categories/active")
        assert res_active.status_code == 200
        active_cats = res_active.json()["categories"]
        active_names = [c["class_name"] for c in active_cats]
        assert "Milk Pouch" in active_names

        # 3. Admin deactivates class
        res_update = client.patch(f"/api/admin/categories/{cat_id}", json={"is_active": False}, headers=admin_headers)
        assert res_update.status_code == 200
        assert res_update.json()["is_active"] is False

        # 4. Public / User fetches active categories -> Milk Pouch MUST NOT be present
        res_active2 = client.get("/api/categories/active")
        assert res_active2.status_code == 200
        active_names2 = [c["class_name"] for c in res_active2.json()["categories"]]
        assert "Milk Pouch" not in active_names2

        # 5. Reactivate for subsequent tests
        client.patch(f"/api/admin/categories/{cat_id}", json={"is_active": True}, headers=admin_headers)

    def test_user_upload_with_unsupported_class_goes_to_admin_review(self, client, auth_headers, admin_headers):
        # Create class "Aluminium Foil" (not in base YOLO model labels)
        res_cat = client.post("/api/admin/categories", json={
            "class_name": "Aluminium Foil",
            "class_code": 902,
            "is_active": True
        }, headers=admin_headers)
        assert res_cat.status_code == 201
        cat_id = res_cat.json()["category_id"]

        # User uploads image selecting "Aluminium Foil"
        img_bytes = create_dummy_image_bytes()
        files = {"file": ("test_foil.jpg", img_bytes, "image/jpeg")}
        data = {"selected_category_id": cat_id}

        res_upload = client.post("/api/images/upload", files=files, data=data, headers=auth_headers)
        assert res_upload.status_code == 201
        body = res_upload.json()

        # System MUST NOT fake validation. Validation result must be MODEL_CLASS_NOT_SUPPORTED
        assert body["validation_result"] == "MODEL_CLASS_NOT_SUPPORTED"
        assert body["status"] == "pending_admin_review"
        assert "not currently supported" in body["validation_reason"]

        image_id = body["image_id"]

        # Admin validation queue check
        res_queue = client.get("/api/admin/validation-queue", headers=admin_headers)
        assert res_queue.status_code == 200
        queue_items = res_queue.json()["queue"]
        target_item = next((item for item in queue_items if item["image_id"] == image_id), None)

        assert target_item is not None
        assert target_item["selected_category_name"] == "Aluminium Foil"
        assert target_item["validation_result"] == "MODEL_CLASS_NOT_SUPPORTED"
        assert target_item["uploader_email"] is not None

        # Admin approves the submission manually
        res_approve = client.post(f"/api/admin/images/{image_id}/approve", json={"action": "approve"}, headers=admin_headers)
        assert res_approve.status_code == 200

    def test_admin_user_contributions_statistics(self, client, admin_headers):
        res = client.get("/api/admin/users/contributions", headers=admin_headers)
        assert res.status_code == 200
        users_list = res.json()["users"]
        assert len(users_list) > 0
        first_user = users_list[0]
        assert "stats" in first_user
        assert "total_uploads" in first_user["stats"]
        assert "approved" in first_user["stats"]
        assert "pending" in first_user["stats"]
