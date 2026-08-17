import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models.user import User

# Use an in-memory SQLite database for testing, or just use the current DB.
# For simplicity, let's keep it connected to the current DB but maybe we shouldn't wipe it?
# Uses FastAPI TestClient against the current dev database.
# Let's just test against the current dev database like the old script did.

client = TestClient(app)

def run_tests():
    # Make sure tables exist
    from app.database import engine
    Base.metadata.create_all(bind=engine)
    
    from app.database import SessionLocal
    db = SessionLocal()

    results = []

    try:
        # 1. Register User (User)
        resp = client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "password123",
            "full_name": "Test User"
        })
        results.append({"method": "POST", "url": "/api/auth/register", "status": resp.status_code, "response": resp.json()})

        # Register Admin
        resp = client.post("/api/auth/register", json={
            "email": "admin@example.com",
            "password": "password123",
            "full_name": "Admin User"
        })
        
        # Set role to admin manually in DB
        admin_user = db.query(User).filter(User.email == "admin@example.com").first()
        if admin_user:
            admin_user.role = "admin"
            db.commit()

        # 2. Login (Admin)
        resp = client.post("/api/auth/login", json={
            "email": "admin@example.com",
            "password": "password123"
        })
        results.append({"method": "POST", "url": "/api/auth/login", "status": resp.status_code, "response": resp.json()})
        token = resp.json().get("access_token") if resp.status_code == 200 else ""
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        # 4. Profile
        resp = client.get("/api/user/profile", headers=headers)
        results.append({"method": "GET", "url": "/api/user/profile", "status": resp.status_code, "response": resp.json()})

        # 5. Admin Categories
        resp = client.post("/api/admin/categories", json={
            "class_name": "Plastic",
            "class_code": 1
        }, headers=headers)
        results.append({"method": "POST", "url": "/api/admin/categories", "status": resp.status_code, "response": resp.json()})

        # 6. Image Endpoints (Placeholder)
        resp = client.get("/api/images/health")
        results.append({"method": "GET", "url": "/api/images/health", "status": resp.status_code, "response": resp.json()})

        # 7. Annotation Endpoints (Placeholder)
        resp = client.get("/api/annotations/health")
        results.append({"method": "GET", "url": "/api/annotations/health", "status": resp.status_code, "response": resp.json()})

        # 8. Dataset Endpoints (Placeholder)
        resp = client.get("/api/dataset/health")
        results.append({"method": "GET", "url": "/api/dataset/health", "status": resp.status_code, "response": resp.json()})

        # 9. ML Endpoints (Placeholder)
        resp = client.get("/api/ml/health")
        results.append({"method": "GET", "url": "/api/ml/health", "status": resp.status_code, "response": resp.json()})

    finally:
        db.close()

    for r in results:
        print(f"{r['method']} {r['url']} - {r['status']}")
        print(f"Response: {r['response']}")
        print("-" * 40)

if __name__ == "__main__":
    run_tests()
