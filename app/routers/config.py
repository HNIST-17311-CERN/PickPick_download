"""配置路由"""
from fastapi import APIRouter, HTTPException, Depends

from app.dependencies import get_config_service, get_auth_service
from app.services.config_service import ConfigService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def api_get_config(cfg_svc: ConfigService = Depends(get_config_service)):
    return cfg_svc.get_masked()


@router.post("/config")
def api_save_config(data: dict, cfg_svc: ConfigService = Depends(get_config_service)):
    cfg_svc.update(data)
    return {"ok": True}


@router.get("/progress")
def api_progress():
    from app.repositories.download_repo import DownloadProgressRepo
    return DownloadProgressRepo().load()


@router.post("/config/test-token")
def api_test_token(data: dict, auth_svc: AuthService = Depends(get_auth_service)):
    return auth_svc.test_token(
        token=(data.get("token") or "").strip(),
        nonce=(data.get("nonce") or "").strip(),
        api_base=data.get("api_base", ""),
    )
