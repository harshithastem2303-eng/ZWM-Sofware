"""
Image Storage Lifecycle Service.

Handles the complete Temporary → Permanent image promotion workflow and the
7-day automatic cleanup of expired temporary images.

Lifecycle state machine
-----------------------
uploaded          (initial — image validated, stored in temporary/)
  ↓  (annotation workflow completes)
annotated
  ↓  (YOLO TXT generated)
yolo_ready
  ↓  (promote_to_permanent called — all conditions met)
permanent

Failure paths:
  uploaded → conversion_failed  (YOLO generation failed)
  uploaded/annotated/conversion_failed → expired_cleaned  (7-day cleanup)

IMPORTANT: This module NEVER modifies annotation logic.
"""
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.image import Image
from app.models.annotation import Annotation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — lifecycle log event tokens
# ---------------------------------------------------------------------------
_EV_UPLOADED = "IMAGE_UPLOADED"
_EV_ANNOTATION_READY = "IMAGE_ANNOTATION_READY"
_EV_YOLO_READY = "YOLO_CONVERSION_READY"
_EV_MOVED = "IMAGE_MOVED_TO_PERMANENT"
_EV_TEMP_DELETED = "TEMPORARY_FILE_DELETED"
_EV_EXPIRED = "TEMPORARY_IMAGE_EXPIRED"
_EV_TRANSFER_FAILED = "PERMANENT_TRANSFER_FAILED"
_EV_CLEANUP_DONE = "CLEANUP_COMPLETED"


# ---------------------------------------------------------------------------
# YOLO TXT validation
# ---------------------------------------------------------------------------

def validate_yolo_txt(txt_path: str) -> bool:
    """
    Validate that a YOLO-format annotation TXT file is structurally correct.

    Each non-empty line must have:
        class_id  x_center  y_center  width  height
    where class_id is a non-negative integer and the four coordinate values
    are floats in the range [0.0, 1.0].

    Returns True if valid (and file is non-empty), False otherwise.
    """
    if not os.path.isfile(txt_path):
        return False

    try:
        with open(txt_path, "r") as fh:
            lines = [l.strip() for l in fh if l.strip()]

        if not lines:
            return False  # empty file is not a valid annotation

        for line in lines:
            parts = line.split()
            if len(parts) < 5:
                return False
            class_id = int(parts[0])  # must be a non-negative integer
            if class_id < 0:
                return False
            coords = [float(p) for p in parts[1:5]]
            for c in coords:
                if not (0.0 <= c <= 1.0):
                    return False
        return True

    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# Safe file operations
# ---------------------------------------------------------------------------

def _safe_copy(src: str, dst: str) -> bool:
    """Copy src → dst, creating parent directories as needed. Returns success."""
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception as exc:
        logger.error("File copy failed: %s → %s | %s", src, dst, exc)
        return False


def _safe_delete(path: str) -> None:
    """Delete a file, logging but not raising if already missing."""
    if path and os.path.exists(path):
        try:
            os.remove(path)
            logger.info("%s | path=%s", _EV_TEMP_DELETED, path)
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path, exc)
    else:
        if path:
            logger.debug("Temp file already absent (skip): %s", path)


# ---------------------------------------------------------------------------
# Permanent promotion
# ---------------------------------------------------------------------------

def promote_to_permanent(
    db: Session,
    image_id: str,
    yolo_txt_path: Optional[str] = None,
) -> dict:
    """
    Move an image from temporary storage to permanent storage.

    Parameters
    ----------
    db             : SQLAlchemy session
    image_id       : UUID of the image to promote
    yolo_txt_path  : Explicit path to the YOLO TXT file.
                     If None, the service looks for the TXT on the most
                     recent annotation for this image (annotation.yolo_label_path).

    Returns
    -------
    dict with keys: success (bool), message (str), [permanent_image_path, permanent_txt_path]
    """
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if image is None:
        return {"success": False, "message": "Image not found"}

    # Guard: already permanent
    if image.status == "permanent":
        return {
            "success": True,
            "message": "Image is already in permanent storage",
            "permanent_image_path": image.permanent_s3_path,
            "permanent_txt_path": image.yolo_txt_path,
        }

    # --- 1. Locate temporary image file ------------------------------------
    temp_img_path = image.temp_s3_path
    if not temp_img_path or not os.path.isfile(temp_img_path):
        logger.error(
            "%s | image_id=%s | temp file missing: %s",
            _EV_TRANSFER_FAILED, image_id, temp_img_path,
        )
        return {"success": False, "message": "Temporary image file not found on disk"}

    # --- 2. Locate YOLO TXT ------------------------------------------------
    # Caller may supply a path; otherwise fall back to annotation record.
    if yolo_txt_path is None:
        annotation = (
            db.query(Annotation)
            .filter(Annotation.image_id == image_id, Annotation.yolo_label_path.isnot(None))
            .order_by(Annotation.annotated_at.desc())
            .first()
        )
        if annotation:
            yolo_txt_path = annotation.yolo_label_path

    if not yolo_txt_path:
        return {"success": False, "message": "No YOLO TXT path available for this image"}

    # --- 3. Validate YOLO TXT ----------------------------------------------
    if not validate_yolo_txt(yolo_txt_path):
        logger.warning(
            "%s | image_id=%s | YOLO TXT invalid: %s",
            _EV_TRANSFER_FAILED, image_id, yolo_txt_path,
        )
        # Mark conversion failed, keep image in temp
        image.status = "conversion_failed"
        db.commit()
        return {"success": False, "message": "YOLO TXT validation failed; image remains in temporary storage"}

    # --- 4. Build permanent destination paths ------------------------------
    _, ext = os.path.splitext(temp_img_path)
    user_id = image.user_id

    # Derive the root uploads folder from temp_s3_path
    # Expected pattern: .../uploads/temporary/{user_id}/{uuid}{ext}
    temp_root = temp_img_path  # walk up to find uploads/
    for _ in range(4):  # safety limit
        temp_root = os.path.dirname(temp_root)
        if os.path.basename(temp_root) == "uploads":
            break

    perm_dir = os.path.join(temp_root, "permanent", user_id)
    perm_img_path = os.path.join(perm_dir, f"{image_id}{ext}")
    perm_txt_path = os.path.join(perm_dir, f"{image_id}.txt")

    # --- 5. Copy image to permanent ----------------------------------------
    if not _safe_copy(temp_img_path, perm_img_path):
        logger.error("%s | image_id=%s | image copy failed", _EV_TRANSFER_FAILED, image_id)
        return {"success": False, "message": "Failed to copy image to permanent storage"}

    # --- 6. Copy TXT to permanent ------------------------------------------
    if not _safe_copy(yolo_txt_path, perm_txt_path):
        # Image copy succeeded but TXT failed — roll back: delete the partial permanent image
        _safe_delete(perm_img_path)
        logger.error("%s | image_id=%s | TXT copy failed; rolled back image copy", _EV_TRANSFER_FAILED, image_id)
        return {"success": False, "message": "Failed to copy YOLO TXT to permanent storage; rolled back"}

    # --- 7. Verify both permanent files exist ------------------------------
    if not os.path.isfile(perm_img_path) or not os.path.isfile(perm_txt_path):
        # Unexpected: copies reported success but files missing
        _safe_delete(perm_img_path)
        _safe_delete(perm_txt_path)
        logger.error("%s | image_id=%s | permanent file verification failed", _EV_TRANSFER_FAILED, image_id)
        return {"success": False, "message": "Permanent file verification failed; rolled back"}

    # --- 8. Update DB in a transaction ------------------------------------
    try:
        now = datetime.now(timezone.utc)
        image.status = "permanent"
        image.permanent_s3_path = perm_img_path
        image.yolo_txt_path = perm_txt_path
        image.permanent_at = now
        image.is_validated = True
        db.commit()
        db.refresh(image)
    except Exception as exc:
        db.rollback()
        # DB update failed — roll back permanent files so state is consistent
        _safe_delete(perm_img_path)
        _safe_delete(perm_txt_path)
        logger.error(
            "%s | image_id=%s | DB commit failed: %s; rolled back files",
            _EV_TRANSFER_FAILED, image_id, exc,
        )
        return {"success": False, "message": f"Database update failed: {exc}"}

    # --- 9. Delete temporary files only AFTER successful DB commit ----------
    _safe_delete(temp_img_path)
    # Also remove the source TXT from its original location (labels/) if it differs
    if yolo_txt_path != perm_txt_path:
        _safe_delete(yolo_txt_path)

    logger.info(
        "%s | image_id=%s | perm_img=%s | perm_txt=%s",
        _EV_MOVED, image_id, perm_img_path, perm_txt_path,
    )

    return {
        "success": True,
        "message": "Image successfully promoted to permanent storage",
        "permanent_image_path": perm_img_path,
        "permanent_txt_path": perm_txt_path,
    }


# ---------------------------------------------------------------------------
# 7-day automatic cleanup
# ---------------------------------------------------------------------------

# Statuses that qualify an image as "still in temporary" (not permanent)
_TEMPORARY_STATUSES = {"uploaded", "annotated", "conversion_failed", "rejected"}


def run_cleanup(db: Session) -> dict:
    """
    Find and delete expired temporary images.

    An image qualifies for cleanup when:
      - status is in _TEMPORARY_STATUSES  (i.e. NOT permanent)
      - temporary_expires_at < now()

    Idempotent: safe to run multiple times or if files are already missing.

    Returns
    -------
    dict with: cleaned (int), errors (int), skipped (int)
    """
    now = datetime.now(timezone.utc)

    expired = (
        db.query(Image)
        .filter(
            Image.status.in_(_TEMPORARY_STATUSES),
            Image.temporary_expires_at.isnot(None),
            Image.temporary_expires_at < now,
        )
        .all()
    )

    cleaned = 0
    errors = 0
    skipped = 0

    for image in expired:
        image_id = image.image_id

        # Safety guard: never clean a permanent image
        if image.status == "permanent":
            logger.warning("Cleanup skipping permanent image %s (should not happen)", image_id)
            skipped += 1
            continue

        # Safety guard: check permanent_s3_path is not populated
        if image.permanent_s3_path and os.path.isfile(image.permanent_s3_path):
            logger.warning(
                "Cleanup skipping image %s: permanent file exists at %s",
                image_id, image.permanent_s3_path,
            )
            skipped += 1
            continue

        try:
            logger.info("%s | image_id=%s", _EV_EXPIRED, image_id)

            # Delete temporary image file (idempotent — ok if missing)
            _safe_delete(image.temp_s3_path)

            # Mark DB record as cleaned
            image.status = "expired_cleaned"
            db.commit()
            cleaned += 1

        except Exception as exc:
            db.rollback()
            logger.error("Cleanup error for image %s: %s", image_id, exc)
            errors += 1

    logger.info(
        "%s | cleaned=%d | errors=%d | skipped=%d",
        _EV_CLEANUP_DONE, cleaned, errors, skipped,
    )
    return {"cleaned": cleaned, "errors": errors, "skipped": skipped}
