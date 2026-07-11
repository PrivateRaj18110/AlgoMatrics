"""Settings router."""

from fastapi import APIRouter

from app.schemas.settings import AppSettings
from app.services.settings_service import get_settings_doc, save_settings_doc

router = APIRouter(tags=["settings"])


@router.get("", response_model=AppSettings, summary="Get application settings")
def get_settings() -> AppSettings:
    return get_settings_doc()


@router.put("", response_model=AppSettings, summary="Update application settings")
def update_settings(settings: AppSettings) -> AppSettings:
    return save_settings_doc(settings)
