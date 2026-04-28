"""
stats.py — 統計收集器
執行緒安全，收集每次請求的延遲、狀態碼、錯誤
"""
import time
import threading
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestResult:
    task_name: str
    method: str
    url: str
    status_code: Optional[int]
    response_time_ms: float
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


class TaskStats:
    """單一 Task 的統計"""

    def __init__(self, name: str):
        self.name = name
        self._lock = threading.Lock()
        self.total = 0
        self.failures = 0
        self.response_times: deque = deque(maxlen=10000)
        self.status_codes: dict[int, int] = defaultdict(int)
        self.errors: dict[str, int] = defaultdict(int)
        self._window: deque = deque()  # (timestamp, 1) for RPS window

    def record(self, result: RequestResult):
        with self._lock:
            self.total += 1
            self.response_times.append(result.response_time_ms)
            self._window.append(result.timestamp)
            # 清理 >10s 的舊資料
            cutoff = result.timestamp - 10
            while self._window and self._window[0] < cutoff:
                self._window.popleft()

            if result.success:
                self.status_codes[result.status_code] += 1
            else:
                self.failures += 1
                if result.error:
                    self.errors[result.error] += 1
                if result.status_code:
                    self.status_codes[result.status_code] += 1

    def rps(self, window_sec: float = 10) -> float:
        with self._lock:
            now = time.time()
            cutoff = now - window_sec
            count = sum(1 for t in self._window if t >= cutoff)
            return count / window_sec

    def percentile(self, p: float) -> float:
        with self._lock:
            if not self.response_times:
                return 0.0
            sorted_times = sorted(self.response_times)
            idx = int(len(sorted_times) * p / 100)
            idx = min(idx, len(sorted_times) - 1)
            return sorted_times[idx]

    def avg(self) -> float:
        with self._lock:
            if not self.response_times:
                return 0.0
            return statistics.mean(self.response_times)

    def min_rt(self) -> float:
        with self._lock:
            return min(self.response_times) if self.response_times else 0.0

    def max_rt(self) -> float:
        with self._lock:
            return max(self.response_times) if self.response_times else 0.0

    def error_rate(self) -> float:
        with self._lock:
            if self.total == 0:
                return 0.0
            return self.failures / self.total * 100

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "total": self.total,
            "failures": self.failures,
            "error_rate": round(self.error_rate(), 2),
            "rps": round(self.rps(), 2),
            "avg_ms": round(self.avg(), 2),
            "min_ms": round(self.min_rt(), 2),
            "max_ms": round(self.max_rt(), 2),
            "p50_ms": round(self.percentile(50), 2),
            "p95_ms": round(self.percentile(95), 2),
            "p99_ms": round(self.percentile(99), 2),
            "status_codes": dict(self.status_codes),
            "errors": dict(self.errors),
        }


class StatsCollector:
    """全域統計收集器，管理所有 Task 的統計"""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskStats] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()

    def record(self, result: RequestResult):
        with self._lock:
            if result.task_name not in self._tasks:
                self._tasks[result.task_name] = TaskStats(result.task_name)
        self._tasks[result.task_name].record(result)

    def total_rps(self, window_sec: float = 10) -> float:
        return sum(t.rps(window_sec) for t in self._tasks.values())

    def total_requests(self) -> int:
        return sum(t.total for t in self._tasks.values())

    def total_failures(self) -> int:
        return sum(t.failures for t in self._tasks.values())

    def overall_error_rate(self) -> float:
        total = self.total_requests()
        if total == 0:
            return 0.0
        return self.total_failures() / total * 100

    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

    def snapshot(self) -> dict:
        return {
            "elapsed_sec": round(self.elapsed(), 2),
            "total_requests": self.total_requests(),
            "total_failures": self.total_failures(),
            "overall_error_rate": round(self.overall_error_rate(), 2),
            "total_rps": round(self.total_rps(), 2),
            "tasks": [t.snapshot() for t in self._tasks.values()],
        }


class TimeSeriesCollector:
    """
    每隔固定秒數記錄一筆快照，供報告畫折線圖用。
    由 ConsoleReporter 在每次更新時呼叫 record_tick()。
    """

    def __init__(self):
        self._lock = threading.Lock()
        # 每筆: {"t": elapsed_sec, "rps": float, "failures_per_sec": float, "p50": float, "p95": float, "users": int}
        self.ticks: list[dict] = []

    def record_tick(self, stats: "StatsCollector", users: int):
        with self._lock:
            elapsed = round(stats.elapsed(), 1)
            total = stats.total_requests()
            failures = stats.total_failures()

            # failures/s：用最近兩筆差值算，避免累積值造成圖形誤導
            prev_failures = self.ticks[-1]["_raw_failures"] if self.ticks else 0
            prev_t = self.ticks[-1]["t"] if self.ticks else 0
            dt = elapsed - prev_t or 1
            failures_per_sec = round((failures - prev_failures) / dt, 2)

            # P50 / P95 取所有 task 的加權平均（簡化：取全部 response_times 合併）
            all_times = []
            for task in stats._tasks.values():
                all_times.extend(list(task.response_times))

            def pct(times, p):
                if not times:
                    return 0.0
                s = sorted(times)
                idx = min(int(len(s) * p / 100), len(s) - 1)
                return round(s[idx], 1)

            self.ticks.append({
                "t": elapsed,
                "rps": round(stats.total_rps(), 2),
                "failures_per_sec": max(failures_per_sec, 0),
                "p50": pct(all_times, 50),
                "p95": pct(all_times, 95),
                "users": users,
                "_raw_failures": failures,  # 內部用，不輸出到圖表
            })

    def chart_data(self) -> dict:
        """回傳給 reporter 用的乾淨格式"""
        with self._lock:
            labels = [t["t"] for t in self.ticks]
            return {
                "labels": labels,
                "rps":              [t["rps"] for t in self.ticks],
                "failures_per_sec": [t["failures_per_sec"] for t in self.ticks],
                "p50":              [t["p50"] for t in self.ticks],
                "p95":              [t["p95"] for t in self.ticks],
                "users":            [t["users"] for t in self.ticks],
            }