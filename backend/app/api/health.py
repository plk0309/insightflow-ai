from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "insightflow-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }