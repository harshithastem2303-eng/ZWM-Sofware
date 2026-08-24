import os
import pytest
import datetime
from sqlalchemy import text
from app.models.user import User, RewardTransaction
from app.models.image import Image
from app.models.category import Category
from app.models.annotation import Annotation

def test_image_approval_and_automatic_rewards(client, admin_auth, db):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    import uuid
    cat = Category(class_name=f"cat_{uuid.uuid4().hex[:6]}", class_code=101)
    db.add(cat)
    db.commit()

    user_id = str(uuid.uuid4())
    user = User(
        user_id=user_id,
        email=f"user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
        reward_points=0,
        image_count=0
    )
    db.add(user)
    db.commit()

    image_id = str(uuid.uuid4())
    img = Image(
        image_id=image_id,
        user_id=user_id,
        original_filename="test.jpg",
        status="uploaded",
        is_validated=False
    )
    db.add(img)
    db.commit()

    try:
        r = client.post(
            f"/api/admin/images/{image_id}/approve",
            headers=admin_auth["headers"],
            json={"action": "approve"}
        )
        assert r.status_code == 200
        
        db.refresh(user)
        db.refresh(img)
        assert user.reward_points == 10
        assert user.image_count == 1
        assert img.status == "approved"
        assert img.is_validated is True
        assert img.reward_given is True
        assert img.credits_awarded == 10
        
        tx = db.query(RewardTransaction).filter(RewardTransaction.image_id == image_id).first()
        assert tx is not None
        assert tx.points == 10
        assert tx.user_id == user_id
        
        r_dup = client.post(
            f"/api/admin/images/{image_id}/approve",
            headers=admin_auth["headers"],
            json={"action": "approve"}
        )
        assert r_dup.status_code == 200
        
        db.refresh(user)
        assert user.reward_points == 10
        assert user.image_count == 1
        txs_count = db.query(RewardTransaction).filter(RewardTransaction.image_id == image_id).count()
        assert txs_count == 1

        from app.dependencies.auth import create_access_token
        access_token = create_access_token(identity=user_id)
        user_headers = {"Authorization": f"Bearer {access_token}"}
        
        r_history = client.get("/api/user/rewards/history", headers=user_headers)
        assert r_history.status_code == 200
        data_hist = r_history.json()
        assert len(data_hist["history"]) == 1
        assert data_hist["history"][0]["points"] == 10
        assert data_hist["history"][0]["image_id"] == image_id
        
    finally:
        txs = db.query(RewardTransaction).filter(RewardTransaction.user_id == user_id).all()
        for t in txs:
            db.delete(t)
        db.delete(img)
        db.delete(user)
        db.delete(cat)
        db.commit()


def test_rejected_image_does_not_receive_rewards(client, admin_auth, db):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    import uuid
    user_id = str(uuid.uuid4())
    user = User(
        user_id=user_id,
        email=f"user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
        reward_points=0,
        image_count=0
    )
    db.add(user)
    db.commit()

    image_id = str(uuid.uuid4())
    img = Image(
        image_id=image_id,
        user_id=user_id,
        original_filename="test_reject.jpg",
        status="uploaded",
        is_validated=False
    )
    db.add(img)
    db.commit()

    try:
        r = client.post(
            f"/api/admin/images/{image_id}/approve",
            headers=admin_auth["headers"],
            json={"action": "reject"}
        )
        assert r.status_code == 200
        
        db.refresh(user)
        db.refresh(img)
        assert user.reward_points == 0
        assert user.image_count == 0
        assert img.status == "rejected"
        assert img.is_validated is True
        assert img.reward_given is None or img.reward_given is False
        
        tx = db.query(RewardTransaction).filter(RewardTransaction.image_id == image_id).first()
        assert tx is None
        
    finally:
        db.delete(img)
        db.delete(user)
        db.commit()


def test_advanced_analytics_and_date_filtering(client, admin_auth, db):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    import uuid
    user_id = str(uuid.uuid4())
    user = User(
        user_id=user_id,
        email=f"user_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="fake",
        image_count=5
    )
    db.add(user)
    db.commit()

    image_id_1 = str(uuid.uuid4())
    image_id_2 = str(uuid.uuid4())
    
    img1 = Image(
        image_id=image_id_1,
        user_id=user_id,
        original_filename="img1.jpg",
        status="approved",
        is_validated=True,
        uploaded_at=datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc),
        validated_at=datetime.datetime(2026, 8, 2, tzinfo=datetime.timezone.utc)
    )
    img2 = Image(
        image_id=image_id_2,
        user_id=user_id,
        original_filename="img2.jpg",
        status="approved",
        is_validated=True,
        uploaded_at=datetime.datetime(2026, 8, 20, tzinfo=datetime.timezone.utc),
        validated_at=datetime.datetime(2026, 8, 21, tzinfo=datetime.timezone.utc)
    )
    db.add_all([img1, img2])
    db.commit()

    try:
        r = client.get("/api/admin/analytics/details", headers=admin_auth["headers"])
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "daily_uploads" in data
        assert "dataset_growth" in data
        assert "top_contributors" in data
        
        r_filtered = client.get(
            "/api/admin/analytics/details",
            headers=admin_auth["headers"],
            params={"start_date": "2026-08-15"}
        )
        assert r_filtered.status_code == 200
        data_filtered = r_filtered.json()
        assert data_filtered["summary"]["total_images"] == 1
        
    finally:
        db.delete(img1)
        db.delete(img2)
        db.delete(user)
        db.commit()
