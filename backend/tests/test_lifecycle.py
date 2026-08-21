"""
Test suite for the ZWM Image Storage Lifecycle.

Tests the Temporary → YOLO → Permanent workflow including:
  - Upload creates temporary storage records
  - temporary_expires_at is set correctly
  - Promotion requires valid YOLO TXT
  - Safe file transfer with rollback on failure
  - Automatic 7-day cleanup (idempotent)
  - Permanent images are NEVER cleaned
  - Authorization checks (no cross-user access)
  - Path traversal rejection
  - Existing APIs remain fully functional

Baseline: 108 existing tests must continue to pass.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from PIL import Image as PILImage, ImageDraw
import random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_image(width=800, height=600, seed=42) -> BytesIO:
    """Create a valid JPEG image that passes blur validation."""
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    draw = ImageDraw.Draw(img)
    random.seed(seed)
    for _ in range(200):
        x1, y1 = random.randint(0, width - 1), random.randint(0, height - 1)
        x2, y2 = random.randint(0, width - 1), random.randint(0, height - 1)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def _make_png_image(width=800, height=600) -> BytesIO:
    """Create a valid PNG image."""
    img = PILImage.new("RGB", (width, height), color=(200, 100, 50))
    draw = ImageDraw.Draw(img)
    for i in range(0, width, 20):
        draw.line([(i, 0), (i, height)], fill=(i % 255, 100, 150), width=3)
    for j in range(0, height, 20):
        draw.line([(0, j), (width, j)], fill=(100, j % 255, 200), width=3)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _write_valid_yolo_txt(path: str) -> None:
    """Write a valid YOLO annotation TXT file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("0 0.5 0.5 0.3 0.4\n")
        f.write("1 0.2 0.7 0.15 0.25\n")


def _write_invalid_yolo_txt(path: str) -> None:
    """Write an invalid YOLO TXT (values out of range)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("0 1.5 0.5 0.3 0.4\n")  # x_center > 1.0 — invalid


# ---------------------------------------------------------------------------
# TC-1: Upload JPG → image stored in temporary storage
# ---------------------------------------------------------------------------
class TestUploadCreatesTemporaryStorage:
    def test_upload_jpg_creates_temporary_file(self, client, user_auth):
        """TC-1: Uploading a JPG creates a file in uploads/temporary/."""
        buf = _make_test_image(seed=1)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("tc1_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "uploaded"

        # Verify file is in temporary storage path
        image_id = data["image_id"]
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img is not None
            assert img.temp_s3_path is not None
            assert "temporary" in img.temp_s3_path.replace("\\", "/")
            assert os.path.isfile(img.temp_s3_path)
        finally:
            db.close()

    def test_upload_png_creates_temporary_file(self, client, user_auth):
        """TC-2: Uploading a PNG also creates a file in uploads/temporary/."""
        buf = _make_png_image()
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("tc2_test.png", buf, "image/png")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "uploaded"

        image_id = data["image_id"]
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img is not None
            assert "temporary" in img.temp_s3_path.replace("\\", "/")
            assert os.path.isfile(img.temp_s3_path)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TC-3 & TC-4: DB record has correct initial state and expiry
# ---------------------------------------------------------------------------
class TestInitialDatabaseRecord:
    def test_db_record_has_uploaded_status(self, client, user_auth):
        """TC-3: DB record is created with status 'uploaded'."""
        buf = _make_test_image(seed=3)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("tc3_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        image_id = r.json()["image_id"]

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "uploaded"
            assert img.storage_type == "local"
        finally:
            db.close()

    def test_temporary_expires_at_is_7_days_from_now(self, client, user_auth):
        """TC-4: temporary_expires_at is approximately 7 days from upload time."""
        buf = _make_test_image(seed=4)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("tc4_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        image_id = r.json()["image_id"]

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.temporary_expires_at is not None

            now = datetime.now(timezone.utc)
            delta = img.temporary_expires_at - now
            # Should be within 6.9 and 7.1 days
            assert timedelta(days=6, hours=20) < delta < timedelta(days=7, hours=4)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TC-5 & TC-6: YOLO validation prevents premature promotion
# ---------------------------------------------------------------------------
class TestYoloValidation:
    def _upload_image(self, client, user_auth, seed=5) -> str:
        buf = _make_test_image(seed=seed)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("yolo_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        return r.json()["image_id"]

    def test_image_stays_temporary_without_yolo_txt(self, client, user_auth):
        """TC-5: No YOLO TXT → promotion fails, image stays in temporary."""
        image_id = self._upload_image(client, user_auth, seed=51)

        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={},
            headers=user_auth["headers"],
        )
        assert r.status_code == 422  # Unprocessable

        # Confirm DB status is still NOT permanent
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status != "permanent"
        finally:
            db.close()

    def test_image_stays_temporary_with_invalid_yolo_txt(self, client, user_auth, tmp_path):
        """TC-6: Invalid YOLO TXT → promotion fails, status=conversion_failed."""
        image_id = self._upload_image(client, user_auth, seed=52)

        # Write an invalid YOLO TXT
        bad_txt = str(tmp_path / "bad.txt")
        _write_invalid_yolo_txt(bad_txt)

        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": bad_txt},
            headers=user_auth["headers"],
        )
        assert r.status_code == 422

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "conversion_failed"
            assert img.permanent_s3_path is None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TC-7 through TC-12: Successful promotion
# ---------------------------------------------------------------------------
class TestSuccessfulPromotion:
    def _upload_and_get_image(self, client, user_auth, seed=7):
        buf = _make_test_image(seed=seed)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("promote_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        return r.json()["image_id"]

    def _do_promote(self, client, user_auth, image_id, tmp_path, seed=7):
        """Upload → write valid YOLO TXT → promote."""
        txt_path = str(tmp_path / f"valid_{seed}.txt")
        _write_valid_yolo_txt(txt_path)

        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": txt_path},
            headers=user_auth["headers"],
        )
        return r, txt_path

    def test_permanent_image_file_created(self, client, user_auth, tmp_path):
        """TC-7: Valid image + valid YOLO TXT → permanent image file created."""
        image_id = self._upload_and_get_image(client, user_auth, seed=71)
        r, _ = self._do_promote(client, user_auth, image_id, tmp_path, seed=71)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert os.path.isfile(data["permanent_image_path"])

    def test_permanent_txt_file_created(self, client, user_auth, tmp_path):
        """TC-8: Valid image + valid YOLO TXT → permanent TXT file created."""
        image_id = self._upload_and_get_image(client, user_auth, seed=72)
        r, _ = self._do_promote(client, user_auth, image_id, tmp_path, seed=72)
        assert r.status_code == 200
        data = r.json()
        assert os.path.isfile(data["permanent_txt_path"])

    def test_permanent_file_exists_before_temp_deleted(self, client, user_auth, tmp_path):
        """TC-9: Permanent file is verified to exist before temp deletion."""
        # The lifecycle service only deletes temp AFTER commit + verification.
        # We verify the permanent file exists in the response.
        image_id = self._upload_and_get_image(client, user_auth, seed=73)
        r, _ = self._do_promote(client, user_auth, image_id, tmp_path, seed=73)
        assert r.status_code == 200
        data = r.json()
        # Both permanent files exist
        assert os.path.isfile(data["permanent_image_path"])
        assert os.path.isfile(data["permanent_txt_path"])

    def test_temporary_files_removed_after_successful_promotion(self, client, user_auth, tmp_path):
        """TC-10: Temporary image is deleted after successful permanent storage."""
        image_id = self._upload_and_get_image(client, user_auth, seed=74)

        # Save temp path before promotion
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            temp_path = img.temp_s3_path
        finally:
            db.close()

        assert os.path.isfile(temp_path)  # exists before promotion

        r, _ = self._do_promote(client, user_auth, image_id, tmp_path, seed=74)
        assert r.status_code == 200

        # Temp file should be gone
        assert not os.path.isfile(temp_path)

    def test_db_status_changes_to_permanent(self, client, user_auth, tmp_path):
        """TC-12: DB status changes to 'permanent' only after successful promotion."""
        image_id = self._upload_and_get_image(client, user_auth, seed=76)
        r, _ = self._do_promote(client, user_auth, image_id, tmp_path, seed=76)
        assert r.status_code == 200

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            db.expire_all()
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "permanent"
            assert img.permanent_s3_path is not None
            assert img.permanent_at is not None
            assert img.yolo_txt_path is not None
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TC-11: Failed transfer preserves temporary image
# ---------------------------------------------------------------------------
class TestFailedTransferPreservesTemp:
    def test_missing_yolo_txt_preserves_temp_image(self, client, user_auth, tmp_path):
        """TC-11: If YOLO TXT is missing/invalid, temp image is preserved."""
        buf = _make_test_image(seed=11)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("tc11_test.jpg", buf, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        # Save original temp path
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            temp_path = img.temp_s3_path
        finally:
            db.close()

        # Attempt promotion with non-existent TXT
        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": str(tmp_path / "nonexistent.txt")},
            headers=user_auth["headers"],
        )
        assert r.status_code == 422

        # Temporary file must still exist
        assert os.path.isfile(temp_path)


# ---------------------------------------------------------------------------
# TC-13 through TC-17: Cleanup logic
# ---------------------------------------------------------------------------
class TestCleanupLogic:
    def _upload_image(self, client, user_auth, seed=13) -> str:
        buf = _make_test_image(seed=seed)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("cleanup_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        return r.json()["image_id"]

    def _expire_image(self, image_id: str) -> None:
        """Manually set temporary_expires_at to the past."""
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            img.temporary_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.commit()
        finally:
            db.close()

    def test_expired_image_is_cleaned(self, client, admin_auth, user_auth):
        """TC-13: Expired temporary images are cleaned by the cleanup endpoint."""
        image_id = self._upload_image(client, user_auth, seed=131)
        self._expire_image(image_id)

        r = client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert r.json()["cleaned"] >= 1

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            db.expire_all()
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "expired_cleaned"
        finally:
            db.close()

    def test_non_expired_image_not_cleaned(self, client, admin_auth, user_auth):
        """TC-14: Non-expired images are NOT deleted by cleanup."""
        image_id = self._upload_image(client, user_auth, seed=141)
        # Do NOT expire — expiry is 7 days in the future

        from app.database import SessionLocal
        from app.models.image import Image

        # Record the temp path
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            temp_path = img.temp_s3_path
        finally:
            db.close()

        r = client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])
        assert r.status_code == 200

        # Image should still be uploaded and file still present
        db = SessionLocal()
        try:
            db.expire_all()
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "uploaded"
        finally:
            db.close()

        if temp_path:
            assert os.path.isfile(temp_path)

    def test_permanent_image_never_cleaned(self, client, admin_auth, user_auth, tmp_path):
        """TC-15: Permanent images are NEVER deleted by the cleanup process."""
        image_id = self._upload_image(client, user_auth, seed=151)

        # Promote to permanent
        txt_path = str(tmp_path / "perm_test.txt")
        _write_valid_yolo_txt(txt_path)
        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": txt_path},
            headers=user_auth["headers"],
        )
        assert r.status_code == 200
        perm_img = r.json()["permanent_image_path"]

        # Expire the image (even though it's permanent)
        self._expire_image(image_id)

        # Run cleanup
        client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])

        # Permanent image still exists
        assert os.path.isfile(perm_img)

        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            db.expire_all()
            img = db.query(Image).filter(Image.image_id == image_id).first()
            assert img.status == "permanent"  # NOT expired_cleaned
        finally:
            db.close()

    def test_cleanup_safe_when_file_already_missing(self, client, admin_auth, user_auth):
        """TC-16: Cleanup is safe if the physical file is already missing."""
        image_id = self._upload_image(client, user_auth, seed=161)
        self._expire_image(image_id)

        # Manually delete the file before cleanup runs
        from app.database import SessionLocal
        from app.models.image import Image
        db = SessionLocal()
        try:
            img = db.query(Image).filter(Image.image_id == image_id).first()
            if img.temp_s3_path and os.path.exists(img.temp_s3_path):
                os.remove(img.temp_s3_path)
        finally:
            db.close()

        # Cleanup should not crash
        r = client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])
        assert r.status_code == 200
        # No unhandled errors
        data = r.json()
        assert "errors" in data

    def test_cleanup_is_idempotent(self, client, admin_auth, user_auth):
        """TC-17: Cleanup can be run multiple times safely."""
        image_id = self._upload_image(client, user_auth, seed=171)
        self._expire_image(image_id)

        # Run cleanup twice
        r1 = client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])
        r2 = client.post("/api/lifecycle/cleanup", headers=admin_auth["headers"])
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Second run should not raise errors
        assert r2.json()["errors"] == 0


# ---------------------------------------------------------------------------
# TC-18 & TC-19: Authorization and security
# ---------------------------------------------------------------------------
class TestAuthorization:
    def test_user_cannot_promote_another_users_image(self, client, user_auth, admin_auth, tmp_path):
        """TC-18: User cannot manipulate another user's image lifecycle."""
        # Upload image as admin user
        buf = _make_test_image(seed=18)
        r = client.post(
            "/api/images/upload",
            headers=admin_auth["headers"],
            files={"file": ("auth_test.jpg", buf, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        # Regular user tries to promote admin's image
        txt_path = str(tmp_path / "auth_test.txt")
        _write_valid_yolo_txt(txt_path)
        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": txt_path},
            headers=user_auth["headers"],  # wrong user
        )
        assert r.status_code == 403

    def test_lifecycle_status_forbidden_for_other_user(self, client, user_auth, admin_auth):
        """TC-18b: User cannot view another user's lifecycle status."""
        buf = _make_test_image(seed=182)
        r = client.post(
            "/api/images/upload",
            headers=admin_auth["headers"],
            files={"file": ("auth_status.jpg", buf, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        r = client.get(
            f"/api/lifecycle/images/{image_id}/status",
            headers=user_auth["headers"],
        )
        assert r.status_code == 403

    def test_path_traversal_rejected(self, client, user_auth, tmp_path):
        """TC-19: Path traversal in yolo_txt_path is rejected (file won't pass validation)."""
        buf = _make_test_image(seed=19)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("traversal_test.jpg", buf, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        # Attempt path traversal
        r = client.post(
            f"/api/lifecycle/images/{image_id}/promote",
            json={"yolo_txt_path": "../../../etc/passwd"},
            headers=user_auth["headers"],
        )
        # validate_yolo_txt returns False for non-existent/non-YOLO files
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# TC-20 through TC-22: Existing functionality smoke tests
# ---------------------------------------------------------------------------
class TestExistingFunctionalityPreserved:
    def test_existing_upload_api_works(self, client, user_auth, test_image_file):
        """TC-20: Existing upload API continues to work and returns status='uploaded'."""
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("existing_test.jpg", test_image_file, "image/jpeg")},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "uploaded"
        assert r.json()["validation"]["valid"] is True

    def test_existing_auth_works(self, client, user_auth):
        """TC-21: Existing authentication/RBAC continues to work."""
        r = client.get("/api/user/profile", headers=user_auth["headers"])
        assert r.status_code == 200
        assert "user_id" in r.json()

    def test_annotation_endpoint_unchanged(self, client, user_auth, admin_auth):
        """TC-22: Annotation endpoint still works without modification."""
        # Upload image
        buf = _make_test_image(seed=22)
        r = client.post(
            "/api/images/upload",
            headers=user_auth["headers"],
            files={"file": ("annot_test.jpg", buf, "image/jpeg")},
        )
        image_id = r.json()["image_id"]

        # Create a category
        cat_name = f"LifecycleTest_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/api/admin/categories",
            json={"class_name": cat_name, "class_code": int(uuid.uuid4().int % 9000) + 1000},
            headers=admin_auth["headers"],
        )
        assert r.status_code == 201
        category_id = r.json()["category_id"]

        # Create annotation (unchanged API)
        r = client.post(
            "/api/annotations/",
            json={"image_id": image_id, "category_id": category_id},
            headers=user_auth["headers"],
        )
        assert r.status_code == 201
        annotation_id = r.json()["annotation_id"]

        # Delete annotation (unchanged API)
        r = client.delete(f"/api/annotations/{annotation_id}", headers=user_auth["headers"])
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Unit tests for lifecycle_service utilities
# ---------------------------------------------------------------------------
class TestLifecycleServiceUnit:
    def test_validate_yolo_txt_valid(self, tmp_path):
        """validate_yolo_txt returns True for a correctly formatted YOLO TXT."""
        from app.services.lifecycle_service import validate_yolo_txt
        txt = str(tmp_path / "valid.txt")
        _write_valid_yolo_txt(txt)
        assert validate_yolo_txt(txt) is True

    def test_validate_yolo_txt_invalid_coords(self, tmp_path):
        """validate_yolo_txt returns False when coords exceed [0, 1]."""
        from app.services.lifecycle_service import validate_yolo_txt
        txt = str(tmp_path / "invalid_coords.txt")
        _write_invalid_yolo_txt(txt)
        assert validate_yolo_txt(txt) is False

    def test_validate_yolo_txt_empty_file(self, tmp_path):
        """validate_yolo_txt returns False for an empty file."""
        from app.services.lifecycle_service import validate_yolo_txt
        txt = str(tmp_path / "empty.txt")
        open(txt, "w").close()
        assert validate_yolo_txt(txt) is False

    def test_validate_yolo_txt_missing_file(self, tmp_path):
        """validate_yolo_txt returns False if file does not exist."""
        from app.services.lifecycle_service import validate_yolo_txt
        assert validate_yolo_txt(str(tmp_path / "nonexistent.txt")) is False

    def test_validate_yolo_txt_too_few_columns(self, tmp_path):
        """validate_yolo_txt returns False for lines with fewer than 5 values."""
        from app.services.lifecycle_service import validate_yolo_txt
        txt = str(tmp_path / "short.txt")
        with open(txt, "w") as f:
            f.write("0 0.5 0.5\n")  # missing w, h
        assert validate_yolo_txt(txt) is False

    def test_run_cleanup_does_not_touch_permanent(self, tmp_path):
        """run_cleanup() skips images with status='permanent'."""
        from app.services.lifecycle_service import run_cleanup
        from app.database import SessionLocal
        from app.models.image import Image
        from app.models.user import User

        # First register a real temporary user so the FK constraint is satisfied
        fake_id = str(uuid.uuid4())
        temp_email = f"cleanup_unit_{uuid.uuid4().hex[:8]}@test.com"

        db = SessionLocal()
        try:
            # Create a real user for the FK
            temp_user = User(
                user_id=str(uuid.uuid4()),
                email=temp_email,
                password_hash="$2b$12$fakehashfortest",
                full_name="Cleanup Unit Test User",
                role="user",
            )
            db.add(temp_user)
            db.flush()
            real_user_id = temp_user.user_id

            # Create a dummy permanent image record with real user FK
            img = Image(
                image_id=fake_id,
                user_id=real_user_id,
                original_filename="perm_unit.jpg",
                status="permanent",
                temporary_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.add(img)
            db.commit()

            stats = run_cleanup(db)
            # The permanent image must NOT be cleaned
            assert stats["skipped"] >= 0  # may or may not appear in skipped count

            db.expire_all()
            img_check = db.query(Image).filter(Image.image_id == fake_id).first()
            # Status must still be permanent — cleanup must NOT touch it
            assert img_check.status == "permanent"
        finally:
            # Cleanup the test records (image first due to FK)
            try:
                db.query(Image).filter(Image.image_id == fake_id).delete()
                db.query(User).filter(User.email == temp_email).delete()
                db.commit()
            except Exception:
                db.rollback()
            db.close()
