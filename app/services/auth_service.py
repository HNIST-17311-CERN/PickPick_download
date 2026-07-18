"""认证业务逻辑"""
import base64
import json
import random
import string
import time

from app.repositories.config_repo import ConfigRepo


class AuthService:
    def __init__(self, config_repo: ConfigRepo):
        self._repo = config_repo

    def login(
        self, email: str, password: str, api_base: str | None = None, nonce: str | None = None
    ) -> dict:
        """同步登录（调用 CLI 或路由层）。返回完整响应 dict"""
        from app.core.pica_client import AsyncPicaClient
        import asyncio

        cfg = self._repo.read()
        base = api_base or cfg.get("api_base", "https://picaapi.go2778.com")
        if not nonce or "..." in nonce:
            nonce = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))

        async def _do():
            client = AsyncPicaClient({"token": "", "nonce": nonce, "api_base": base})
            try:
                return await client.login(email, password)
            finally:
                await client.close()

        try:
            resp = asyncio.run(_do())
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}
        code = resp.get("code", -1)
        if code != 200:
            return {
                "ok": False,
                "error": resp.get("message", f"未知错误 code={code}"),
            }

        token = (
            resp.get("data", {}).get("token")
            or resp.get("token")
            or ""
        )
        if isinstance(token, dict):
            token = token.get("token") or token.get("jwt") or ""
        if not token:
            return {"ok": False, "error": "响应中未找到 token", "debug": json.dumps(resp, indent=2, ensure_ascii=False)[:2000]}
        if token.count(".") != 2:
            return {"ok": False, "error": f"返回的 token 不是 JWT 格式: {token[:50]}...", "debug": str(resp)[:1000]}

        cfg = self._repo.read()
        cfg["token"] = token
        cfg["nonce"] = nonce
        self._repo.write(cfg)

        user, email_saved, exp_str, remaining = "?", "?", "?", 0
        try:
            parts = token.split(".")
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==="))
            user = payload.get("name", "?")
            email_saved = payload.get("email", "?")
            exp_ts = payload.get("exp", 0)
            exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp_ts))
            remaining = round((exp_ts - time.time()) / 3600, 1)
        except Exception:
            pass

        return {
            "ok": True, "user": user, "email": email_saved,
            "expires": exp_str, "remaining_hours": remaining,
            "debug": json.dumps(resp, indent=2, ensure_ascii=False)[:2000],
        }

    def test_token(self, token: str, nonce: str, api_base: str) -> dict:
        import asyncio
        from app.core.pica_client import AsyncPicaClient

        cfg = self._repo.read()
        # 前端发空值 → 用 config.yaml 的 token/nonce；只有明确传了非空值才覆盖
        if not token or "..." in token:
            token = cfg.get("token", "")
        if not nonce or "..." in nonce:
            nonce = cfg.get("nonce", "")
        base = api_base or cfg.get("api_base", "https://picaapi.go2778.com")

        if not token or not nonce:
            return {"ok": False, "error": "token 或 nonce 为空"}

        # 解析 JWT
        user, email_saved, exp_str, remaining = "?", "?", "?", 0
        try:
            parts = token.split(".")
            if len(parts) == 3:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==="))
                user = payload.get("name", "?")
                email_saved = payload.get("email", "?")
                exp_ts = payload.get("exp", 0)
                exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp_ts))
                remaining = round((exp_ts - time.time()) / 3600, 1)
        except Exception:
            pass

        async def _do():
            client = AsyncPicaClient({"token": token, "nonce": nonce, "api_base": base})
            try:
                data = await client.get_favourites(page=1, limit=1)
                code = data.get("code", -1)
                if code == 200:
                    fav_total = data.get("data", {}).get("comics", {}).get("total", 0)
                    return {
                        "ok": True, "user": user, "email": email_saved,
                        "expires": exp_str, "remaining_hours": remaining,
                        "favourites_total": fav_total,
                    }
                return {
                    "ok": False, "error": data.get("message", f"code={code}"),
                    "user": user, "email": email_saved,
                    "expires": exp_str, "remaining_hours": remaining,
                }
            finally:
                await client.close()

        try:
            return asyncio.run(_do())
        except Exception as e:
            return {
                "ok": False, "error": str(e),
                "user": user, "email": email_saved,
                "expires": exp_str, "remaining_hours": remaining,
            }
