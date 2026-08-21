"""
Comprehensive annotation test suite.

Tests:
  1.  Create rectangle annotation
  2.  Create polygon annotation
  3.  Create circle annotation
  4.  Create freehand annotation
  5.  Create AI-generated polygon
  6.  Get annotation by ID
  7.  Get annotations by image
  8.  Update annotation
  9.  Delete annotation
  10. Invalid annotation type -> 422
  11. Invalid points (too few) -> 422
  12. Missing image -> 404
  13. Unauthenticated access -> 401
  14. Cross-user annotation access -> 403
  15. YOLO bounding-box conversion endpoint
  16. Category dropdown listing (existing admin API)
  17. Update with annotation_type change
  18. Circle missing required key -> 422
  19. Negative coordinates -> 422
  20. Rectangle with wrong number of points -> 422

Baseline: all 137 existing tests must continue to pass.
"""
import uuid
import pytest
from io import BytesIO
from PIL import Image as PILImage, ImageDraw
import random


# ---------------------------------------------------------------------------
# Test image factory (same as conftest approach)
# ---------------------------------------------------------------------------

def _make_test_jpeg(seed=42) -> BytesIO:
    img = PILImage.new("RGB", (800, 600), color=(100, 150, 200))
    draw = ImageDraw.Draw(img)
    random.seed(seed)
    for _ in range(200):
        x1, y1 = random.randint(0, 799), random.randint(0, 599)
        x2, y2 = random.randint(0, 799), random.randint(0, 599)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Shared setup helpers
# ---------------------------------------------------------------------------

def _upload_image(client, auth_headers, seed=42) -> str:
    buf = _make_test_jpeg(seed)
    r = client.post(
        "/api/images/upload",
        headers=auth_headers,
        files={"file": (f"ann_{seed}.jpg", buf, "image/jpeg")},
    )
    assert r.status_code == 201, f"Upload failed: {r.json()}"
    return r.json()["image_id"]


def _create_category(client, admin_headers) -> int:
    name = f"TestCat_{uuid.uuid4().hex[:6]}"
    code = int(uuid.uuid4().int % 90000) + 1000
    r = client.post(
        "/api/admin/categories",
        json={"class_name": name, "class_code": code},
        headers=admin_headers,
    )
    assert r.status_code == 201
    return r.json()["category_id"]


# ---------------------------------------------------------------------------
# TC-1: Create rectangle
# ---------------------------------------------------------------------------
class TestCreateRectangle:
    def test_create_rectangle(self, client, user_auth, admin_auth):
        """TC-1: Valid rectangle creates annotation with status 201."""
        image_id = _upload_image(client, user_auth["headers"], seed=101)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 10, "y": 20}, {"x": 100, "y": 150}]},
            "category_id": category_id,
            "image_width": 800,
            "image_height": 600,
        }, headers=user_auth["headers"])

        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["annotation_type"] == "rectangle"
        assert data["image_id"] == image_id
        assert data["category_id"] == category_id
        assert len(data["label_data_json"]["points"]) == 2


# ---------------------------------------------------------------------------
# TC-2: Create polygon
# ---------------------------------------------------------------------------
class TestCreatePolygon:
    def test_create_polygon(self, client, user_auth, admin_auth):
        """TC-2: Valid polygon (3+ points) is stored correctly."""
        image_id = _upload_image(client, user_auth["headers"], seed=102)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [
                    {"x": 12, "y": 30},
                    {"x": 80, "y": 30},
                    {"x": 90, "y": 100},
                    {"x": 50, "y": 140},
                ]
            },
            "category_id": category_id,
        }, headers=user_auth["headers"])

        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["annotation_type"] == "polygon"
        assert len(data["label_data_json"]["points"]) == 4


# ---------------------------------------------------------------------------
# TC-3: Create circle
# ---------------------------------------------------------------------------
class TestCreateCircle:
    def test_create_circle(self, client, user_auth, admin_auth):
        """TC-3: Circle annotation stored with cx, cy, r."""
        image_id = _upload_image(client, user_auth["headers"], seed=103)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "circle",
            "label_data": {"cx": 200, "cy": 150, "r": 50},
            "category_id": category_id,
        }, headers=user_auth["headers"])

        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["annotation_type"] == "circle"
        assert data["label_data_json"]["cx"] == 200
        assert data["label_data_json"]["cy"] == 150
        assert data["label_data_json"]["r"] == 50


# ---------------------------------------------------------------------------
# TC-4: Create freehand
# ---------------------------------------------------------------------------
class TestCreateFreehand:
    def test_create_freehand(self, client, user_auth, admin_auth):
        """TC-4: Freehand annotation with 2+ points."""
        image_id = _upload_image(client, user_auth["headers"], seed=104)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "freehand",
            "label_data": {
                "points": [
                    {"x": 10, "y": 20},
                    {"x": 15, "y": 24},
                    {"x": 20, "y": 30},
                    {"x": 25, "y": 38},
                ]
            },
            "category_id": category_id,
        }, headers=user_auth["headers"])

        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["annotation_type"] == "freehand"
        assert len(data["label_data_json"]["points"]) == 4


# ---------------------------------------------------------------------------
# TC-5: AI-generated polygon
# ---------------------------------------------------------------------------
class TestAiGeneratedAnnotation:
    def test_create_ai_polygon(self, client, user_auth, admin_auth):
        """TC-5: ai_generated=True is stored and returned correctly."""
        image_id = _upload_image(client, user_auth["headers"], seed=105)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [
                    {"x": 50, "y": 50},
                    {"x": 200, "y": 50},
                    {"x": 200, "y": 200},
                ]
            },
            "category_id": category_id,
            "ai_generated": True,
        }, headers=user_auth["headers"])

        assert r.status_code == 201, r.json()
        data = r.json()
        assert data["ai_generated"] is True


# ---------------------------------------------------------------------------
# TC-6: Get annotation
# ---------------------------------------------------------------------------
class TestGetAnnotation:
    def test_get_annotation_by_id(self, client, user_auth, admin_auth):
        """TC-6: Created annotation is retrievable by ID."""
        image_id = _upload_image(client, user_auth["headers"], seed=106)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 50, "y": 50}]},
            "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.get(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r2.status_code == 200
        assert r2.json()["annotation_id"] == ann_id
        assert r2.json()["annotation_type"] == "rectangle"

    def test_get_nonexistent_annotation(self, client, user_auth):
        """TC-6b: Non-existent annotation returns 404."""
        r = client.get("/api/annotations/does-not-exist", headers=user_auth["headers"])
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# TC-7: Get annotations by image
# ---------------------------------------------------------------------------
class TestGetAnnotationsByImage:
    def test_get_annotations_for_image(self, client, user_auth, admin_auth):
        """TC-7: GET /image/{id} returns all annotations for that image."""
        image_id = _upload_image(client, user_auth["headers"], seed=107)
        category_id = _create_category(client, admin_auth["headers"])

        # Create two annotations
        for _ in range(2):
            client.post("/api/annotations/", json={
                "image_id": image_id,
                "annotation_type": "polygon",
                "label_data": {
                    "points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}]
                },
                "category_id": category_id,
            }, headers=user_auth["headers"])

        r = client.get(f"/api/annotations/image/{image_id}", headers=user_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "annotations" in data
        assert data["count"] >= 2

    def test_get_annotations_missing_image(self, client, user_auth):
        """TC-7b: Returns 404 for missing image_id."""
        r = client.get("/api/annotations/image/no-such-image", headers=user_auth["headers"])
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# TC-8: Update annotation
# ---------------------------------------------------------------------------
class TestUpdateAnnotation:
    def test_update_annotation_label_data(self, client, user_auth, admin_auth):
        """TC-8: Updating label_data replaces the shape coordinates."""
        image_id = _upload_image(client, user_auth["headers"], seed=108)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]
            },
            "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        # Update with new points
        r2 = client.put(f"/api/annotations/{ann_id}", json={
            "label_data": {
                "points": [{"x": 50, "y": 60}, {"x": 100, "y": 60}, {"x": 100, "y": 120}]
            }
        }, headers=user_auth["headers"])
        assert r2.status_code == 200
        updated_pts = r2.json()["label_data_json"]["points"]
        assert updated_pts[0]["x"] == 50

    def test_update_annotation_type(self, client, user_auth, admin_auth):
        """TC-17: Annotation type can be changed (e.g. polygon -> freehand)."""
        image_id = _upload_image(client, user_auth["headers"], seed=117)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}]
            },
            "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.put(f"/api/annotations/{ann_id}", json={
            "annotation_type": "freehand",
            "label_data": {
                "points": [{"x": 5, "y": 5}, {"x": 10, "y": 10}]
            }
        }, headers=user_auth["headers"])
        assert r2.status_code == 200
        assert r2.json()["annotation_type"] == "freehand"


# ---------------------------------------------------------------------------
# TC-9: Delete annotation
# ---------------------------------------------------------------------------
class TestDeleteAnnotation:
    def test_delete_annotation(self, client, user_auth, admin_auth):
        """TC-9: Deleted annotation is no longer retrievable."""
        image_id = _upload_image(client, user_auth["headers"], seed=109)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 10, "y": 10}, {"x": 50, "y": 50}]},
            "category_id": category_id,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.delete(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r2.status_code == 200

        r3 = client.get(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r3.status_code == 404

    def test_delete_nonexistent(self, client, user_auth):
        r = client.delete("/api/annotations/ghost-id", headers=user_auth["headers"])
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# TC-10: Invalid annotation type
# ---------------------------------------------------------------------------
class TestInvalidAnnotationType:
    def test_invalid_type_rejected(self, client, user_auth, admin_auth):
        """TC-10: Unknown annotation_type returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=110)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "unknown_type",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        }, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_empty_type_rejected(self, client, user_auth, admin_auth):
        """TC-10b: Empty annotation_type returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1101)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "  ",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]},
        }, headers=user_auth["headers"])
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# TC-11: Invalid points
# ---------------------------------------------------------------------------
class TestInvalidPoints:
    def test_polygon_too_few_points(self, client, user_auth, admin_auth):
        """TC-11a: Polygon with < 3 points returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1110)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}]},
        }, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_rectangle_wrong_point_count(self, client, user_auth, admin_auth):
        """TC-20: Rectangle with 3 points returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1120)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}, {"x": 20, "y": 20}]
            },
        }, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_freehand_single_point_rejected(self, client, user_auth, admin_auth):
        """TC-11b: Freehand with only 1 point returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1113)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "freehand",
            "label_data": {"points": [{"x": 5, "y": 5}]},
        }, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_negative_coordinates_rejected(self, client, user_auth, admin_auth):
        """TC-19: Points with negative x/y values return 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1114)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [{"x": -1, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]
            },
        }, headers=user_auth["headers"])
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# TC-12: Missing image
# ---------------------------------------------------------------------------
class TestMissingImage:
    def test_missing_image_returns_404(self, client, user_auth):
        """TC-12: Annotation on non-existent image returns 404."""
        r = client.post("/api/annotations/", json={
            "image_id": "no-such-image-id",
            "annotation_type": "polygon",
            "label_data": {
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}]
            },
        }, headers=user_auth["headers"])
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# TC-13: Unauthenticated access
# ---------------------------------------------------------------------------
class TestUnauthenticatedAccess:
    def test_create_no_auth(self, client):
        """TC-13: Creating annotation without token returns 401."""
        r = client.post("/api/annotations/", json={
            "image_id": "any",
            "annotation_type": "polygon",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}]},
        })
        assert r.status_code == 401

    def test_get_no_auth(self, client):
        """TC-13b: Getting annotation without token returns 401."""
        r = client.get("/api/annotations/some-id")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# TC-14: Cross-user access
# ---------------------------------------------------------------------------
class TestCrossUserAccess:
    def test_other_user_cannot_delete(self, client, user_auth, admin_auth):
        """TC-14: User B cannot delete User A's annotation."""
        # Admin uploads an image and creates annotation
        image_id = _upload_image(client, admin_auth["headers"], seed=1140)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}]},
            "category_id": category_id,
        }, headers=admin_auth["headers"])
        ann_id = r.json()["annotation_id"]

        # Regular user tries to delete admin's annotation
        r2 = client.delete(f"/api/annotations/{ann_id}", headers=user_auth["headers"])
        assert r2.status_code == 403

    def test_other_user_cannot_update(self, client, user_auth, admin_auth):
        """TC-14b: User B cannot update User A's annotation."""
        image_id = _upload_image(client, admin_auth["headers"], seed=1141)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 10, "y": 10}]},
            "category_id": category_id,
        }, headers=admin_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.put(f"/api/annotations/{ann_id}", json={
            "label_data": {"points": [{"x": 99, "y": 99}, {"x": 200, "y": 200}]}
        }, headers=user_auth["headers"])
        assert r2.status_code == 403


# ---------------------------------------------------------------------------
# TC-15: YOLO bounding-box endpoint
# ---------------------------------------------------------------------------
class TestYoloBbox:
    def test_yolo_bbox_rectangle(self, client, user_auth, admin_auth):
        """TC-15a: Rectangle annotation returns correct bbox and YOLO line."""
        image_id = _upload_image(client, user_auth["headers"], seed=1150)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 0, "y": 0}, {"x": 200, "y": 100}]},
            "category_id": category_id,
            "image_width": 400,
            "image_height": 400,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.get(f"/api/annotations/{ann_id}/yolo-bbox", headers=user_auth["headers"])
        assert r2.status_code == 200
        data = r2.json()
        assert "bbox" in data
        assert data["bbox"]["x_min"] == 0
        assert data["bbox"]["x_max"] == 200
        assert data["yolo_line"] is not None
        # YOLO line should start with the class_code integer
        parts = data["yolo_line"].split()
        assert len(parts) == 5

    def test_yolo_bbox_circle(self, client, user_auth, admin_auth):
        """TC-15b: Circle bbox is computed from cx, cy, r."""
        image_id = _upload_image(client, user_auth["headers"], seed=1151)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "circle",
            "label_data": {"cx": 100, "cy": 100, "r": 50},
            "category_id": category_id,
            "image_width": 400,
            "image_height": 400,
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.get(f"/api/annotations/{ann_id}/yolo-bbox", headers=user_auth["headers"])
        assert r2.status_code == 200
        data = r2.json()
        # Circle r=50 -> x_min=50, y_min=50, x_max=150, y_max=150
        assert data["bbox"]["x_min"] == 50
        assert data["bbox"]["x_max"] == 150

    def test_yolo_bbox_no_dimensions(self, client, user_auth, admin_auth):
        """TC-15c: Without image dimensions, yolo_line is None (bbox still returned)."""
        image_id = _upload_image(client, user_auth["headers"], seed=1152)
        category_id = _create_category(client, admin_auth["headers"])

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "polygon",
            "label_data": {
                "points": [{"x": 10, "y": 10}, {"x": 50, "y": 10}, {"x": 50, "y": 50}]
            },
            "category_id": category_id,
            # No image_width / image_height
        }, headers=user_auth["headers"])
        ann_id = r.json()["annotation_id"]

        r2 = client.get(f"/api/annotations/{ann_id}/yolo-bbox", headers=user_auth["headers"])
        assert r2.status_code == 200
        data = r2.json()
        assert data["bbox"] is not None
        assert data["yolo_line"] is None  # no dimensions -> no YOLO line


# ---------------------------------------------------------------------------
# TC-16: Category (label dropdown) listing
# ---------------------------------------------------------------------------
class TestCategoryDropdown:
    def test_categories_accessible_to_admin(self, client, admin_auth):
        """TC-16: Admin can list categories for the label dropdown."""
        r = client.get("/api/admin/categories", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "categories" in r.json()


# ---------------------------------------------------------------------------
# TC-18: Circle missing required key
# ---------------------------------------------------------------------------
class TestCircleValidation:
    def test_circle_missing_r_rejected(self, client, user_auth, admin_auth):
        """TC-18: Circle without 'r' key returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1180)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "circle",
            "label_data": {"cx": 100, "cy": 100},  # missing r
        }, headers=user_auth["headers"])
        assert r.status_code == 422

    def test_circle_zero_radius_rejected(self, client, user_auth, admin_auth):
        """TC-18b: Circle with r=0 returns 422."""
        image_id = _upload_image(client, user_auth["headers"], seed=1181)

        r = client.post("/api/annotations/", json={
            "image_id": image_id,
            "annotation_type": "circle",
            "label_data": {"cx": 100, "cy": 100, "r": 0},
        }, headers=user_auth["headers"])
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Unit tests — annotation_converter
# ---------------------------------------------------------------------------
class TestAnnotationConverter:
    def test_rectangle_bbox(self):
        from app.services.annotation_converter import shape_to_bbox
        bbox = shape_to_bbox("rectangle", {"points": [{"x": 10, "y": 20}, {"x": 110, "y": 120}]})
        assert bbox == (10, 20, 110, 120)

    def test_polygon_bbox(self):
        from app.services.annotation_converter import shape_to_bbox
        bbox = shape_to_bbox("polygon", {
            "points": [{"x": 5, "y": 5}, {"x": 50, "y": 5}, {"x": 50, "y": 80}, {"x": 5, "y": 80}]
        })
        assert bbox == (5, 5, 50, 80)

    def test_circle_bbox(self):
        from app.services.annotation_converter import shape_to_bbox
        bbox = shape_to_bbox("circle", {"cx": 100, "cy": 100, "r": 40})
        assert bbox == (60, 60, 140, 140)

    def test_yolo_line_format(self):
        from app.services.annotation_converter import bbox_to_yolo
        line = bbox_to_yolo((0, 0, 200, 100), 400, 400, class_id=2)
        parts = line.split()
        assert parts[0] == "2"
        assert len(parts) == 5
        # x_center = (0+200)/2 / 400 = 0.25
        assert abs(float(parts[1]) - 0.25) < 1e-4

    def test_missing_points_returns_none(self):
        from app.services.annotation_converter import shape_to_bbox
        assert shape_to_bbox("polygon", {}) is None
        assert shape_to_bbox("rectangle", {"points": []}) is None


# ---------------------------------------------------------------------------
# Unit tests — annotation_service
# ---------------------------------------------------------------------------
class TestAnnotationService:
    def test_validate_type_normalises_case(self):
        from app.services.annotation_service import validate_annotation_type
        assert validate_annotation_type("POLYGON") == "polygon"
        assert validate_annotation_type("  Rectangle  ") == "rectangle"

    def test_validate_type_rejects_unknown(self):
        from fastapi import HTTPException
        from app.services.annotation_service import validate_annotation_type
        with pytest.raises(HTTPException) as exc:
            validate_annotation_type("square")
        assert exc.value.status_code == 422

    def test_validate_circle_ok(self):
        from app.services.annotation_service import validate_label_data
        result = validate_label_data("circle", {"cx": 50, "cy": 50, "r": 20})
        assert result["r"] == 20

    def test_validate_polygon_normalises_floats(self):
        from app.services.annotation_service import validate_label_data
        result = validate_label_data("polygon", {
            "points": [{"x": "10", "y": "20"}, {"x": "30", "y": "40"}, {"x": "50", "y": "60"}]
        })
        assert result["points"][0]["x"] == 10.0
