from fastapi import APIRouter

from app.deps import SettingsDep
from app.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def health(settings: SettingsDep) -> HealthStatus:
    return HealthStatus(status="ok", supabase_configured=settings.supabase_configured)
