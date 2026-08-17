"""
End-to-end ZWM workflow test:
register → verify-email → login → profile → upload → validate →
annotate → admin-approve → rewards → stats → analytics
"""
import uuid


class TestEndToEndWorkflow:
    def test_full_workflow(self, client, db):
        # --- 1. Register ---
        email = f"e2e_{uuid.uuid4().hex[:8]}@test.com"
        password = "E2EPass123!"
        r = client.post("/api/auth/register", json={
            "email": email, "password": password, "full_name": "E2E User",
        })
        assert r.status_code == 201
        user_id = r.json()["user_id"]

        # --- 2. Verify email ---
        from app.models.user import User
        user = db.query(User).filter(User.user_id == user_id).first()
        verify_token = user.verification_token
        r = client.post("/api/auth/verify-email", json={"token": verify_token})
        assert r.status_code == 200

        # --- 3. Login ---
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200
        tokens = r.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # --- 4. Profile ---
        r = client.get("/api/user/profile", headers=headers)
        assert r.status_code == 200
        assert r.json()["is_email_verified"] is True

        # --- 5. Upload image ---
        from PIL import Image as PILImage, ImageDraw
        from io import BytesIO
        import random
        img = PILImage.new("RGB", (800, 600), color=(50, 100, 150))
        draw = ImageDraw.Draw(img)
        random.seed(99)
        for _ in range(200):
            x1, y1 = random.randint(0, 799), random.randint(0, 599)
            x2, y2 = random.randint(0, 799), random.randint(0, 599)
            c = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            draw.line([(x1, y1), (x2, y2)], fill=c, width=2)
        buf = BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        r = client.post(
            "/api/images/upload", headers=headers,
            files={"file": ("e2e_test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 201
        image_data = r.json()
        image_id = image_data["image_id"]
        assert image_data["validation"]["valid"] is True
        assert image_data["status"] == "uploaded"

        # --- 6. List images ---
        r = client.get("/api/images/", headers=headers)
        assert r.status_code == 200
        assert r.json()["count"] >= 1

        # --- 7. Create admin for approval ---
        admin_email = f"e2e_admin_{uuid.uuid4().hex[:8]}@test.com"
        client.post("/api/auth/register", json={
            "email": admin_email, "password": "AdminE2E!", "full_name": "E2E Admin",
        })
        from app.database import SessionLocal
        s = SessionLocal()
        admin = s.query(User).filter(User.email == admin_email).first()
        admin.role = "admin"
        s.commit()
        s.close()

        r = client.post("/api/auth/login", json={"email": admin_email, "password": "AdminE2E!"})
        admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # --- 8. Create category ---
        cat_name = f"E2ECat_{uuid.uuid4().hex[:6]}"
        r = client.post("/api/admin/categories", json={
            "class_name": cat_name, "class_code": int(uuid.uuid4().int % 99000) + 1000,
        }, headers=admin_headers)
        assert r.status_code == 201
        category_id = r.json()["category_id"]

        # --- 9. Annotate ---
        r = client.post("/api/annotations/", json={
            "image_id": image_id, "category_id": category_id,
        }, headers=headers)
        assert r.status_code == 201
        annotation_id = r.json()["annotation_id"]

        # --- 10. Validation queue (admin) ---
        r = client.get("/api/admin/validation-queue", headers=admin_headers)
        assert r.status_code == 200

        # --- 11. Approve image (admin) ---
        r = client.post(
            f"/api/admin/images/{image_id}/approve",
            json={"action": "approve"},
            headers=admin_headers,
        )
        assert r.status_code == 200

        # --- 12. Check rewards ---
        r = client.get("/api/user/rewards", headers=headers)
        assert r.status_code == 200
        assert r.json()["reward_points"] >= 10

        # --- 13. Check stats ---
        r = client.get("/api/user/stats", headers=headers)
        assert r.status_code == 200
        assert r.json()["validated_images"] >= 1

        # --- 14. Check history ---
        r = client.get("/api/user/history", headers=headers)
        assert r.status_code == 200

        # --- 15. Analytics (admin) ---
        r = client.get("/api/admin/analytics/overview", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total_users"] >= 2
        assert data["total_images"] >= 1

        # --- 16. Leaderboard ---
        r = client.get("/api/admin/analytics/leaderboard", headers=admin_headers)
        assert r.status_code == 200

        # --- 17. Dataset stats ---
        r = client.get("/api/dataset/stats", headers=admin_headers)
        assert r.status_code == 200

        # --- 18. Dataset readiness ---
        r = client.get("/api/dataset/readiness", headers=admin_headers)
        assert r.status_code == 200

        # --- 19. ML models (empty) ---
        r = client.get("/api/ml/models", headers=admin_headers)
        assert r.status_code == 200

        # --- 20. ML jobs (empty) ---
        r = client.get("/api/ml/jobs", headers=admin_headers)
        assert r.status_code == 200

        # --- 21. YOLO predict — BLOCKED (no model file) ---
        buf2 = BytesIO()
        img2 = PILImage.new("RGB", (640, 480), color=(200, 50, 50))
        img2.save(buf2, format="JPEG")
        buf2.seek(0)
        r = client.post(
            "/api/ml/predict", headers=headers,
            files={"file": ("predict.jpg", buf2, "image/jpeg")},
        )
        assert r.status_code == 503
        assert "BLOCKED" in r.json()["detail"]

        # --- 22. Cleanup: delete annotation ---
        r = client.delete(f"/api/annotations/{annotation_id}", headers=headers)
        assert r.status_code == 200
