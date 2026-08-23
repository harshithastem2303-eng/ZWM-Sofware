import os
import shutil
import tempfile
from io import BytesIO
from PIL import Image as PILImage

import pytest

from app.config import settings


@pytest.mark.usefixtures("client", "user_auth")
def test_predict_with_corrupted_model_returns_503(client, user_auth):
    """If the YOLO model file is empty or corrupted, /api/ml/predict should return 503 (BLOCKED)."""
    model_path = settings.YOLO_MODEL_PATH
    model_dir = os.path.dirname(model_path)
    os.makedirs(model_dir, exist_ok=True)

    backup_path = None
    try:
        # If an existing model is present, back it up so the test doesn't destroy it
        if os.path.exists(model_path):
            fd, tmp_backup = tempfile.mkstemp(prefix="best.pt.backup.")
            os.close(fd)
            os.remove(tmp_backup)
            shutil.move(model_path, tmp_backup)
            backup_path = tmp_backup

        # Create an empty (corrupted) model file to simulate a truncated checkpoint
        with open(model_path, "wb") as f:
            f.truncate(0)

        # Prepare a valid image for prediction
        img = PILImage.new("RGB", (640, 480), color=(0, 255, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        r = client.post(
            "/api/ml/predict",
            headers=user_auth["headers"],
            files={"file": ("predict.jpg", buf, "image/jpeg")},
        )

        assert r.status_code == 503, f"Expected 503 for corrupted model, got {r.status_code}: {r.text}"
        data = r.json()
        assert "BLOCKED" in (data.get("detail", data.get("message", ""))) or "model" in data.get("detail", "").lower()

    finally:
        # Remove the test model file
        try:
            if os.path.exists(model_path):
                os.remove(model_path)
        except Exception:
            pass
        # Restore backup if it existed
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.move(backup_path, model_path)
            except Exception:
                # If restore fails, leave the backup for manual inspection
                pass
