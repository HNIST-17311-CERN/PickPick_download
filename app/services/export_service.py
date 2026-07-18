"""导入导出业务逻辑"""
import asyncio
import shutil
import tempfile
import zipfile
from pathlib import Path

from app.repositories.comic_repo import DETAIL_DIR


class ExportService:
    def __init__(self, detail_dir: Path = DETAIL_DIR):
        self._base = detail_dir

    async def export_zip(self, folders: list[str]) -> str:
        """创建临时 ZIP 文件，返回路径"""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.close()
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._create_zip, tmp.name, folders)
        except Exception:
            Path(tmp.name).unlink(missing_ok=True)
            raise
        return tmp.name

    def _create_zip(self, zip_path: str, folders: list[str]) -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder_name in folders:
                src = self._base / folder_name
                if not src.is_dir():
                    continue
                for f in src.rglob("*"):
                    if f.is_file():
                        zf.write(f, f.relative_to(self._base))

    async def import_zip(self, file_content: bytes, filename: str) -> dict:
        """从上传内容导入 ZIP"""
        if not filename.endswith(".zip"):
            return {"ok": False, "error": "只支持 .zip 文件"}

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.write(file_content)
        tmp.close()

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._extract_zip, tmp.name)
            return {"ok": True, "imported": 1}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _extract_zip(self, zip_path: str) -> None:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                dest = (self._base / member).resolve()
                if not str(dest).startswith(str(self._base.resolve())):
                    raise ValueError(f"非法路径: {member}")
            zf.extractall(self._base)

    async def cleanup_temp(self, path: str, delay: int = 120) -> None:
        await asyncio.sleep(delay)
        Path(path).unlink(missing_ok=True)
