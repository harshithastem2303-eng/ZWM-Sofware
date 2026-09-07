import os
import sys
import shutil

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, ".env"))

import psycopg2
from app.config import settings

def clear_all_data():
    db_url = os.getenv("DATABASE_URL") or settings.DATABASE_URL
    print(f"Connecting to database...")
    
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    # 1. Truncate all database tables with CASCADE to wipe data while keeping schema
    tables = [
        "annotations",
        "images",
        "categories",
        "training_jobs",
        "model_versions",
        "reward_transactions",
        "users",
        "admins",
    ]
    
    existing_tables = []
    for tbl in tables:
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s);", (tbl,))
        if cur.fetchone()[0]:
            existing_tables.append(tbl)

    if existing_tables:
        tables_str = ", ".join(f'"{t}"' for t in existing_tables)
        print(f"Truncating tables: {tables_str}...")
        cur.execute(f"TRUNCATE TABLE {tables_str} CASCADE;")
        print("Database tables truncated successfully!")
    else:
        print("No matching tables found to truncate.")
        
    cur.close()
    conn.close()

    # 2. Clear all image files from backend/uploads folder
    uploads_dir = settings.UPLOAD_FOLDER
    print(f"Clearing uploads directory: {uploads_dir}...")
    
    if os.path.exists(uploads_dir):
        for item in os.listdir(uploads_dir):
            item_path = os.path.join(uploads_dir, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                    print(f"Deleted file: {item_path}")
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"Deleted directory: {item_path}")
            except Exception as e:
                print(f"Error deleting {item_path}: {e}")

    # Re-create empty temporary and permanent subdirectories
    os.makedirs(os.path.join(uploads_dir, "temporary"), exist_ok=True)
    os.makedirs(os.path.join(uploads_dir, "permanent"), exist_ok=True)
    print("Uploads folder cleared and clean directory structure re-created!")

    print("\n--- ALL DATABASE DATA & UPLOADS CLEARED SUCCESSFULLY ---")

if __name__ == "__main__":
    clear_all_data()
