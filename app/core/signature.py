"""哔咔漫画 API 签名算法 — 从 JS bundle 逆向工程"""
import base64
import hashlib
import hmac


def _oe_decode(s: str, seed: str) -> str:
    """Fisher-Yates deshuffle — 从 JS Oe 函数复现"""
    n = len(s)
    arr = list(range(n))
    t = sum(ord(c) for c in seed)
    for i in range(n - 1, 0, -1):
        t = (9301 * t + 49297) % 233280
        j = t % (i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    result = [''] * n
    for i in range(n):
        result[i] = s[arr[i]]
    return ''.join(result)


def _ue(encoded: str) -> str:
    """从 JS Ue 函数复现 — 解码混淆字符串"""
    step1 = base64.b64decode(encoded).decode('latin-1')
    step2 = _oe_decode(step1, 'PicaWeb2025')
    step3 = ''.join(chr(ord(c) ^ 42) for c in step2)
    step4 = base64.b64decode(step3).decode('latin-1')
    return step4


# 从 JS bundle 中提取的密钥（不可变常量，不需要也不应该从配置文件读取）
_API_KEY = _ue('b397e2wXZHtgb2RvUBh7bnB+bnt8bEEfZ2xSQUFtY0F4G3h4bWhzeA==')
_SIGN_KEY = _ue('aGh+G0dwfHpGUGRmYGxrGUFsZmRyGUMZa19kfUxfRxMfXGAaGxNBbmBhZRpMQUFma20Bbn58YElIYGQTbGdsQkxrfEd8X3xueBocH1JQf2RpSG9B')


def compute_signature(path: str, timestamp: str, nonce: str, method: str) -> str:
    """计算 API 请求签名（与浏览器端完全一致）"""
    p = path.lstrip('/')
    msg = (p + timestamp + nonce + method + _API_KEY).lower()
    return hmac.new(_SIGN_KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
