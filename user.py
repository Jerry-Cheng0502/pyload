"""
user.py — 使用者基底類別
團隊繼承此類別定義自己的測試情境
"""
import time
import random
import inspect
import requests
from typing import Optional, Callable
from .stats import StatsCollector, RequestResult


def task(weight: int = 1):
    """
    裝飾器，標記方法為負載測試 Task。
    weight 越高，被隨機選中的機率越大。

    範例：
        @task(weight=3)
        def search(self):
            self.get("/search?q=hello")
    """
    def decorator(fn: Callable) -> Callable:
        fn._is_task = True
        fn._weight = weight
        return fn
    return decorator


class HttpUser:
    """
    負載測試使用者基底類別。
    繼承後定義 host、wait_time，並用 @task 標記測試方法。

    範例：
        class MyUser(HttpUser):
            host = "https://api.example.com"
            wait_time = (1, 3)   # 每次 task 後隨機等 1~3 秒

            @task(weight=2)
            def get_users(self):
                self.get("/users")

            @task(weight=1)
            def create_user(self):
                self.post("/users", json={"name": "test"})
    """

    host: str = ""
    wait_time: tuple[float, float] = (1, 1)  # (min_sec, max_sec)

    def __init__(self, stats: StatsCollector, session: Optional[requests.Session] = None):
        self._stats = stats
        self._session = session or requests.Session()
        self._tasks: list[Callable] = []

        # 收集所有 @task 標記的方法（依 weight 展開）
        for _, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if getattr(method, "_is_task", False):
                for _ in range(method._weight):
                    self._tasks.append(method)

        if not self._tasks:
            raise ValueError(f"{self.__class__.__name__} 沒有任何 @task 方法")

    # ── HTTP 便利方法 ──────────────────────────────────────────

    def _request(self, method: str, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        """發送請求並記錄統計，name 可覆寫統計顯示名稱"""
        url = self.host.rstrip("/") + "/" + path.lstrip("/")
        task_name = name or f"{method.upper()} {path}"
        start = time.perf_counter()
        error = None
        status_code = None
        try:
            resp = self._session.request(method, url, **kwargs)
            status_code = resp.status_code
            return resp
        except Exception as e:
            error = type(e).__name__
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._stats.record(RequestResult(
                task_name=task_name,
                method=method.upper(),
                url=url,
                status_code=status_code,
                response_time_ms=elapsed_ms,
                error=error,
            ))

    def get(self, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        return self._request("GET", path, name=name, **kwargs)

    def post(self, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        return self._request("POST", path, name=name, **kwargs)

    def put(self, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        return self._request("PUT", path, name=name, **kwargs)

    def patch(self, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        return self._request("PATCH", path, name=name, **kwargs)

    def delete(self, path: str, name: Optional[str] = None, **kwargs) -> requests.Response:
        return self._request("DELETE", path, name=name, **kwargs)

    # ── 生命週期 hooks（子類別可覆寫）────────────────────────

    def on_start(self):
        """每個虛擬使用者啟動前呼叫，可做登入、取 token 等初始化"""
        pass

    def on_stop(self):
        """每個虛擬使用者結束後呼叫，可做登出、清理等"""
        pass

    # ── 內部執行 ─────────────────────────────────────────────

    def _pick_task(self) -> Callable:
        return random.choice(self._tasks)

    def _think_time(self) -> float:
        lo, hi = self.wait_time
        return random.uniform(lo, hi)
