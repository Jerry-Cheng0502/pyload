"""
engine.py — 負載引擎
使用 ThreadPoolExecutor 模擬多使用者並發，支援 spawn rate
"""
import time
import threading
import itertools
from concurrent.futures import ThreadPoolExecutor
from typing import Type

from .user import HttpUser
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
        spawn_rate: float,       # users per second
        run_time: float,         # 總執行秒數，0 = 無限
    ):
        self.user_class = user_class
        self.stats = stats
        self.num_users = num_users
        self.spawn_rate = spawn_rate
        self.run_time = run_time

        self._stop_event = threading.Event()
        self._active_users = 0
        self._users_lock = threading.Lock()
        self._executor: ThreadPoolExecutor = None

    # ── 公開介面 ──────────────────────────────────────────────

    def start(self):
        self.stats.start()
        self._executor = ThreadPoolExecutor(max_workers=self.num_users + 10)

        # Spawn 執行緒：依 spawn_rate 逐漸加入使用者
        spawner = threading.Thread(target=self._spawn_loop, daemon=True)
        spawner.start()

        # 若有 run_time，計時結束後停止
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

    # ── 內部 ──────────────────────────────────────────────────

    def _spawn_loop(self):
        interval = 1.0 / self.spawn_rate  # 每隔多少秒產生一個 user
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
        import requests
        session = requests.Session()
        user = self.user_class(self.stats, session)

        try:
            user.on_start()
            while not self._stop_event.is_set():
                task_fn = user._pick_task()
                try:
                    task_fn()
                except Exception:
                    pass  # 錯誤已在 _request 內記錄，繼續跑
                think = user._think_time()
                if think > 0:
                    # 分段 sleep，讓 stop_event 能及時中斷
                    deadline = time.time() + think
                    while time.time() < deadline and not self._stop_event.is_set():
                        time.sleep(min(0.1, deadline - time.time()))
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
