"""
PyLoad — Python 輕量級 API 負載測試工具
純標準庫 + requests，類 Locust 設計
"""
from .user import HttpUser, task
from .stats import StatsCollector, RequestResult
from .engine import LoadEngine
from .reporter import save_html, save_json

__all__ = ["HttpUser", "task", "StatsCollector", "RequestResult", "LoadEngine", "save_html", "save_json"]
__version__ = "1.0.0"
