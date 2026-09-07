import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
import random

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, ".env"))

from app.database import SessionLocal
from app.models.user import User
from app.models.category import Category
from app.models.image import Image
from app.models.annotation import Annotation
from app.routes.auth import get_password_hash

def seed():
    db = SessionLocal()
    try:
        print("Cleaning old data...")
        db.query(Annotation).delete()
        db.query(Image).delete()
        
        # Delete users except our main admin
        db.query(User).filter(User.email != "zwm123@gmail.com").delete()
        db.query(Category).delete()
        db.commit()

        print("Seeding categories...")
        categories_data = [
            {"category_id": 1, "class_name": "Plastic", "class_code": 1001, "validated_count": 450},
            {"category_id": 2, "class_name": "Metal", "class_code": 1002, "validated_count": 280},
            {"category_id": 3, "class_name": "Paper", "class_code": 1003, "validated_count": 270},
        ]
        for cat_dict in categories_data:
            cat = Category(**cat_dict)
            db.add(cat)
        db.commit()

        print("Ensuring main admin user exists...")
        admin_user = db.query(User).filter(User.email == "admin@gmail.com").first()
        if not admin_user:
            admin_user = User(
                email="admin@gmail.com",
                password_hash=get_password_hash("user123"),
                full_name="System Admin",
                role="admin",
                is_email_verified=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        admin_user_alt = db.query(User).filter(User.email == "zwm123@gmail.com").first()
        if not admin_user_alt:
            admin_user_alt = User(
                email="zwm123@gmail.com",
                password_hash=get_password_hash("ZWMUSER123"),
                full_name="Admin User",
                role="admin",
                is_email_verified=True,
            )
            db.add(admin_user_alt)
            db.commit()

        demo_user = db.query(User).filter(User.email == "demo@zwm.eco").first()
        if not demo_user:
            demo_user = User(
                email="demo@zwm.eco",
                password_hash=get_password_hash("User123!"),
                full_name="Demo User",
                role="user",
                is_email_verified=True,
                reward_points=250,
                image_count=15,
            )
            db.add(demo_user)
            db.commit()

        print("Seeding remaining users to reach 2,450 total users...")
        existing_users_count = db.query(User).count()
        users_to_create = 2450 - existing_users_count
        
        user_mappings = []
        for i in range(users_to_create):
            uid = str(uuid.uuid4())
            user_mappings.append({
                "user_id": uid,
                "email": f"user_{i}_{uuid.uuid4().hex[:6]}@zwm.com",
                "password_hash": "dummy_hash",
                "full_name": f"Regular User {i}",
                "role": "user",
                "is_email_verified": True,
                "reward_points": random.randint(10, 500),
                "image_count": random.randint(1, 20),
                "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180)),
            })
            
            # Bulk commit in chunks of 500
            if len(user_mappings) >= 500:
                db.bulk_insert_mappings(User, user_mappings)
                db.commit()
                user_mappings = []
                
        if user_mappings:
            db.bulk_insert_mappings(User, user_mappings)
            db.commit()

        # Fetch some user IDs to associate with images
        all_user_ids = [row[0] for row in db.query(User.user_id).limit(100).all()]

        print("Seeding images to reach 12,840 total images...")
        # 11950 approved, 320 pending, 570 rejected
        # Total = 12,840
        total_images = 12840
        approved_count = 11950
        pending_count = 320
        rejected_count = 570

        image_mappings = []
        
        # Distribute uploads over months: March to August 2024
        # Target upload distributions per month (approx):
        # March: 250, April: 450, May: 800, June: 1200, July: 2140, August: 8000
        start_date = datetime(2024, 3, 1, tzinfo=timezone.utc)
        
        def get_random_date_in_month(month_idx):
            # month_idx: 3 (March) to 8 (August)
            year = 2024
            day = random.randint(1, 28)
            hour = random.randint(0, 23)
            return datetime(year, month_idx, day, hour, 0, 0, tzinfo=timezone.utc)

        # Create Approved Images
        for i in range(approved_count):
            # Select month based on distribution
            r = random.random()
            if r < 0.02:   # 2% March
                m = 3
            elif r < 0.06: # 4% April
                m = 4
            elif r < 0.12: # 6% May
                m = 5
            elif r < 0.22: # 10% June
                m = 6
            elif r < 0.38: # 16% July
                m = 7
            else:          # 62% August
                m = 8

            uploaded_at = get_random_date_in_month(m)
            validated_at = uploaded_at + timedelta(days=random.randint(1, 3))
            
            image_mappings.append({
                "image_id": str(uuid.uuid4()),
                "user_id": random.choice(all_user_ids),
                "original_filename": f"img_approved_{i}.jpg",
                "status": "approved",
                "is_validated": True,
                "reward_given": True,
                "credits_awarded": 10,
                "uploaded_at": uploaded_at,
                "validated_at": validated_at,
            })

            if len(image_mappings) >= 1000:
                db.bulk_insert_mappings(Image, image_mappings)
                db.commit()
                image_mappings = []

        # Create Pending Images
        for i in range(pending_count):
            uploaded_at = get_random_date_in_month(8) # August
            image_mappings.append({
                "image_id": str(uuid.uuid4()),
                "user_id": random.choice(all_user_ids),
                "original_filename": f"img_pending_{i}.jpg",
                "status": "uploaded",
                "is_validated": False,
                "reward_given": False,
                "uploaded_at": uploaded_at,
            })

            if len(image_mappings) >= 1000:
                db.bulk_insert_mappings(Image, image_mappings)
                db.commit()
                image_mappings = []

        # Create Rejected Images
        for i in range(rejected_count):
            uploaded_at = get_random_date_in_month(random.randint(6, 8)) # June to August
            image_mappings.append({
                "image_id": str(uuid.uuid4()),
                "user_id": random.choice(all_user_ids),
                "original_filename": f"img_rejected_{i}.jpg",
                "status": "rejected",
                "is_validated": True,
                "reward_given": False,
                "uploaded_at": uploaded_at,
                "validated_at": uploaded_at + timedelta(days=1),
            })

            if len(image_mappings) >= 1000:
                db.bulk_insert_mappings(Image, image_mappings)
                db.commit()
                image_mappings = []

        if image_mappings:
            db.bulk_insert_mappings(Image, image_mappings)
            db.commit()

        # Let's seed Annotations for the validated category counts (450 Plastic, 280 Metal, 270 Paper)
        print("Seeding annotations linked to categories...")
        # Fetch some approved image IDs to link annotations to
        approved_image_ids = [row[0] for row in db.query(Image.image_id).filter(Image.status == "approved").limit(1000).all()]
        
        annotation_mappings = []
        
        # Plastic (Category ID 1) -> 450
        for i in range(450):
            annotation_mappings.append({
                "annotation_id": str(uuid.uuid4()),
                "image_id": approved_image_ids[i % len(approved_image_ids)],
                "category_id": 1,
                "annotated_by": admin_user.user_id,
                "annotated_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
            })
            
        # Metal (Category ID 2) -> 280
        for i in range(280):
            annotation_mappings.append({
                "annotation_id": str(uuid.uuid4()),
                "image_id": approved_image_ids[(i + 450) % len(approved_image_ids)],
                "category_id": 2,
                "annotated_by": admin_user.user_id,
                "annotated_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
            })

        # Paper (Category ID 3) -> 270
        for i in range(270):
            annotation_mappings.append({
                "annotation_id": str(uuid.uuid4()),
                "image_id": approved_image_ids[(i + 730) % len(approved_image_ids)],
                "category_id": 3,
                "annotated_by": admin_user.user_id,
                "annotated_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
            })

        db.bulk_insert_mappings(Annotation, annotation_mappings)
        db.commit()

        print("Database seeded successfully!")
        print("Total Users:", db.query(User).count())
        print("Total Images:", db.query(Image).count())
        print("Approved Images:", db.query(Image).filter(Image.status == "approved").count())
        print("Pending Images:", db.query(Image).filter(Image.status == "uploaded").count())
        print("Annotations Count:", db.query(Annotation).count())

    finally:
        db.close()

if __name__ == "__main__":
    seed()
