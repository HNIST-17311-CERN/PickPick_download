"""认证 + 系统路由"""
import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Body, UploadFile, File, Depends
from fastapi.responses import FileResponse

from app.dependencies import get_auth_service, get_export_service
from app.services.auth_service import AuthService
from app.services.export_service import ExportService

router = APIRouter(prefix="/api", tags=["auth", "system"])


@router.post("/login")
def api_login(data: dict = Body(...), auth_svc: AuthService = Depends(get_auth_service)):
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(400, "邮箱和密码不能为空")
    api_base = data.get("api_base")
    nonce = data.get("nonce")
    try:
        return auth_svc.login(email, password, api_base, nonce)
    except RuntimeError as e:
        raise HTTPException(502, f"API 请求失败: {e}")
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/logout")
def api_logout():
    from app.repositories.config_repo import ConfigRepo
    cfg = ConfigRepo().read()
    cfg["token"] = ""
    cfg["nonce"] = ""
    ConfigRepo().write(cfg)
    return {"ok": True}


@router.post("/pick-directory")
def api_pick_directory(data: dict = Body(...)):
    from tkinter import Tk, filedialog
    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial = data.get("initial", str(Path.cwd()))
        result = filedialog.askdirectory(initialdir=initial, title="选择文件夹")
        root.destroy()
        if result:
            return {"ok": True, "path": result}
        return {"ok": False, "error": "未选择文件夹"}
    except Exception as e:
        return {"ok": False, "error": f"无法打开文件选择器: {e}"}


@router.post("/comics/export")
async def api_export(data: dict = Body(...), export_svc: ExportService = Depends(get_export_service)):
    folders = data.get("folders", [])
    if not folders:
        raise HTTPException(400, "请选择要导出的漫画")

    zip_path = await export_svc.export_zip(folders)
    asyncio.create_task(export_svc.cleanup_temp(zip_path))
    return FileResponse(zip_path, media_type="application/zip", filename="comics_export.zip")


@router.post("/comics/import")
async def api_import(file: UploadFile = File(...), export_svc: ExportService = Depends(get_export_service)):
    if not file.filename:
        raise HTTPException(400, "请选择文件")
    content = await file.read()
    result = await export_svc.import_zip(content, file.filename)
    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "导入失败"))
    return result
