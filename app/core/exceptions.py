"""自定义异常"""

class PicaAPIError(Exception):
    """PicaWeb API 返回非成功响应"""
    pass


class DownloadError(Exception):
    """下载失败"""
    pass


class ConfigError(Exception):
    """配置错误"""
    pass
