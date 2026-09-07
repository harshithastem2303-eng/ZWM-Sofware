import os
import sys
import uuid
import shutil
from datetime import datetime, timezone

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, ".env"))

from app.database import SessionLocal
from app.models.user import User
from app.models.category import Category
from app.models.image import Image
from app.models.annotation import Annotation
from app.config import settings

def add_nandini_images():
    source_dir = r"E:\Users\subha\OneDrive\Desktop\NANDINI MILK"
    if not os.path.exists(source_dir):
        print(f"Error: Source directory '{source_dir}' does not exist.")
        return

    # Find first 6 image files
    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    source_files = [
        f for f in os.listdir(source_dir)
        if os.path.splitext(f)[1].lower() in valid_exts
    ][:6]

    if not source_files:
        print("No image files found in NANDINI MILK folder.")
        return

    print(f"Found {len(source_files)} images from NANDINI MILK folder.")

    db = SessionLocal()
    try:
        # Get demo user and Plastic category
        user = db.query(User).first()
        if not user:
            print("Error: No user found in database.")
            return

        plastic_cat = db.query(Category).filter(Category.class_name.ilike("%Plastic%")).first()
        if not plastic_cat:
            plastic_cat = db.query(Category).first()

        cat_slug = "plastic"
        if plastic_cat:
            cat_slug = plastic_cat.class_name.lower().replace(" ", "_").replace("&", "and")

        # Create destination directories
        dataset_imgs_dir = os.path.join(settings.UPLOAD_FOLDER, "dataset", cat_slug, "images")
        dataset_lbls_dir = os.path.join(settings.UPLOAD_FOLDER, "dataset", cat_slug, "labels")
        os.makedirs(dataset_imgs_dir, exist_ok=True)
        os.makedirs(dataset_lbls_dir, exist_ok=True)

        added_count = 0
        for orig_file in source_files:
            src_path = os.path.join(source_dir, orig_file)
            img_id = str(uuid.uuid4())
            ext = os.path.splitext(orig_file)[1].lower()
            dst_filename = f"{img_id}{ext}"

            # Copy image to dataset folder
            dst_img_path = os.path.join(dataset_imgs_dir, dst_filename)
            shutil.copy2(src_path, dst_img_path)

            # Create YOLO label file (.txt)
            txt_filename = f"{img_id}.txt"
            dst_txt_path = os.path.join(dataset_lbls_dir, txt_filename)
            class_code = plastic_cat.class_code if plastic_cat else 0
            # Center box (class_id x_center y_center width height)
            with open(dst_txt_path, "w") as f:
                f.write(f"0 0.5 0.5 0.7 0.7\n")

            # Create Image database record
            now = datetime.now(timezone.utc)
            db_img = Image(
                image_id=img_id,
                user_id=user.user_id,
                original_filename=orig_file,
                storage_type="local",
                status="approved",
                is_validated=True,
                reward_given=True,
                credits_awarded=15,
                uploaded_at=now,
                validated_at=now,
                annotated_at=now,
                converted_at=now,
                permanent_at=now,
                yolo_txt_path=dst_txt_path
            )
            db.add(db_img)

            # Create Annotation database record
            db_ann = Annotation(
                annotation_id=str(uuid.uuid4()),
                image_id=img_id,
                category_id=plastic_cat.category_id if plastic_cat else 1,
                annotated_by=user.user_id,
                annotation_type="rectangle",
                label_data_json={"points": [{"x": 15, "y": 15}, {"x": 85, "y": 85}]},
                ai_generated=False,
                image_width=640,
                image_height=640,
                label_json_path=dst_txt_path,
                yolo_label_path=dst_txt_path,
                annotated_at=now,
            )
            db.add(db_ann)

            added_count += 1

        # Update category validated_count
        if plastic_cat:
            plastic_cat.validated_count = (plastic_cat.validated_count or 0) + added_count

        # Update user reward points & image count
        user.reward_points = (user.reward_points or 0) + (added_count * 15)
        user.image_count = (user.image_count or 0) + added_count

        db.commit()
        print(f"Successfully added {added_count} validated images from NANDINI MILK to database & dataset folder!")

    except Exception as e:
        db.rollback()
        print(f"Error adding images: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    add_nandini_images()
