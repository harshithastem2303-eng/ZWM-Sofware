from fastapi import APIRouter
from app.schemas.schemas import MessageResponse

router = APIRouter()

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "annotation"}
