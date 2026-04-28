"""
engine.py — 負載引擎
針對同機測試優化：
  - 每個 user 獨立 Session，但 pool_size 對齊 num_users
  - spawn_rate 預設可以很大，同機不需要暖機斜坡
  - think_time = 0 時跳過 sleep，不浪費 CPU
  - max_requests：打完 N 筆就自動停止
"""
import time
import threading
import itertools
from concurrent.futures import ThreadPoolExecutor
from typing import Type

from .user import HttpUser, _make_session
from .stats import StatsCollector


class LoadEngine:
    """
    負載引擎：按 spawn_rate 逐步啟動虛擬使用者，
    每位使用者在自己的執行緒中持續跑 task loop 直到停止訊號。
    """

    def __init__(
        self,
        user_class: Type[HttpUser],
        stats: StatsCollector,
        num_users: int,
        spawn_rate: float,      # users per second
        run_time: float,        # 總執行秒數，0 = 無限
        max_requests: int = 0,  # 打完 N 筆就停，0 = 不限制
    ):
        self.user_class = user_class
        self.stats = stats
        self.num_users = num_users
        self.spawn_rate = spawn_rate
        self.run_time = run_time
        self.max_requests = max_requests

        self._stop_event = threading.Event()
        self._active_users = 0
        self._users_lock = threading.Lock()
        self._request_count = 0       # 已完成請求數（含失敗）
        self._request_lock = threading.Lock()
        self._executor: ThreadPoolExecutor = None

    # ── 公開介面 ──────────────────────────────────────────────

    def start(self):
        self.stats.start()
        self._executor = ThreadPoolExecutor(max_workers=self.num_users + 10)

        spawner = threading.Thread(target=self._spawn_loop, daemon=True)
        spawner.start()

        if self.run_time > 0:
            timer = threading.Thread(
                target=self._run_timer, args=(self.run_time,), daemon=True
            )
            timer.start()

    def stop(self):
        self._stop_event.set()
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=False)
        self.stats.stop()

    def wait(self):
        """阻塞直到停止訊號"""
        self._stop_event.wait()

    @property
    def active_users(self) -> int:
        with self._users_lock:
            return self._active_users

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    def _increment_request(self) -> bool:
        """
        每次請求完成後呼叫，回傳是否已達 max_requests。
        執行緒安全，達上限時自動觸發停止。
        """
        if self.max_requests == 0:
            return False
        with self._request_lock:
            self._request_count += 1
            if self._request_count >= self.max_requests:
                self._stop_event.set()
                return True
        return False

    # ── 內部 ──────────────────────────────────────────────────

    def _spawn_loop(self):
        interval = 1.0 / self.spawn_rate
        for _ in itertools.repeat(None):
            if self._stop_event.is_set():
                break
            with self._users_lock:
                if self._active_users >= self.num_users:
                    break
                self._active_users += 1
            self._executor.submit(self._user_loop)
            time.sleep(interval)

    def _user_loop(self):
        """單一虛擬使用者的生命週期"""
        pool_size = max(self.num_users, self.user_class.pool_size)
        session = _make_session(pool_size=pool_size, timeout=self.user_class.timeout)
        user = self.user_class(self.stats, session)

        try:
            user.on_start()
            while not self._stop_event.is_set():
                task_fn = user._pick_task()
                try:
                    task_fn()
                except Exception:
                    pass  # 錯誤已在 _request 內記錄，繼續跑

                # 每打完一筆檢查是否達到 max_requests
                self._increment_request()

                think = user._think_time()
                if think > 0:
                    deadline = time.time() + think
                    while time.time() < deadline and not self._stop_event.is_set():
                        time.sleep(min(0.05, deadline - time.time()))
        finally:
            try:
                user.on_stop()
            except Exception:
                pass
            session.close()
            with self._users_lock:
                self._active_users -= 1

    def _run_timer(self, seconds: float):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._stop_event.is_set():
                return
            time.sleep(0.5)
        self._stop_event.set()