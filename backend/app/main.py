from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

from app.routes.auth import router as auth_router
from app.routes.user import router as user_router
from app.routes.admin import router as admin_router
from app.routes.image import router as image_router
from app.routes.ml import router as ml_router
from app.routes.dataset import router as dataset_router
from app.routes.annotation import router as annotation_router

app = FastAPI(title="ZWM Backend API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with actual frontend origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(user_router, prefix="/api/user", tags=["User"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(image_router, prefix="/api/images", tags=["Image"])
app.include_router(ml_router, prefix="/api/ml", tags=["ML"])
app.include_router(dataset_router, prefix="/api/dataset", tags=["Dataset"])
app.include_router(annotation_router, prefix="/api/annotations", tags=["Annotation"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the ZWM API"}
