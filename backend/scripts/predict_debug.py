import os, sys
# Ensure backend/ is on path like pytest fixtures do
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from app.main import app
from io import BytesIO
from PIL import Image as PILImage

client = TestClient(app)

# Register user
email = "debug_user@test.com"
password = "TestPassword123!"
resp = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": "Debug User"})
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info('register status %s %s', resp.status_code, resp.text)

# Login
r = client.post("/api/auth/login", json={"email": email, "password": password})
logger.info('login status %s %s', r.status_code, r.text)
if r.status_code != 200:
    raise SystemExit('login failed')
data = r.json()
headers = {"Authorization": f"Bearer {data.get('access_token')}"}

# Prepare image
img = PILImage.new("RGB", (640, 480), color=(0, 255, 0))
buf = BytesIO()
img.save(buf, format="JPEG")
buf.seek(0)

resp = client.post("/api/ml/predict", headers=headers, files={"file": ("predict.jpg", buf, "image/jpeg")})
logger.info('predict status %s', resp.status_code)
try:
    logger.info('predict body: %s', resp.json())
except Exception:
    logger.info('predict text: %s', resp.text)

# If server returned 500 it may have printed details to stdout/stderr; done.
