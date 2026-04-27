"""
console.py — 即時 Console 報表
每隔 interval 秒列印一次統計表格
"""
import threading
import time
import sys

from .stats import StatsCollector
from .engine import LoadEngine

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def _color_error_rate(rate: float) -> str:
    s = f"{rate:.1f}%"
    if rate == 0:
        return GREEN + s + RESET
    if rate < 5:
        return YELLOW + s + RESET
    return RED + s + RESET


def _color_p95(p95: float) -> str:
    s = f"{p95:.0f}"
    if p95 < 500:
        return GREEN + s + RESET
    if p95 < 1500:
        return YELLOW + s + RESET
    return RED + s + RESET


def _bar(value: float, max_val: float, width: int = 10) -> str:
    if max_val == 0:
        filled = 0
    else:
        filled = int(min(value / max_val, 1.0) * width)
    return "█" * filled + "░" * (width - filled)


class ConsoleReporter:
    def __init__(self, stats: StatsCollector, engine: LoadEngine, interval: float = 2.0):
        self.stats = stats
        self.engine = engine
        self.interval = interval
        self._thread: threading.Thread = None
        self._stop = threading.Event()
        self._last_line_count = 0

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        # 最後列印一次完整報表
        self._print_table(final=True)

    def _loop(self):
        while not self._stop.is_set():
            self._print_table()
            self._stop.wait(self.interval)

    def _print_table(self, final: bool = False):
        snap = self.stats.snapshot()
        tasks = snap["tasks"]

        lines = []

        # ── 標題列 ──
        label = "FINAL REPORT" if final else "LIVE"
        elapsed = snap["elapsed_sec"]
        users = self.engine.active_users
        lines.append(
            f"{BOLD}{CYAN}{'─'*80}{RESET}"
        )
        lines.append(
            f"{BOLD} PyLoad [{label}]{RESET}  "
            f"elapsed={CYAN}{elapsed:.0f}s{RESET}  "
            f"users={CYAN}{users}{RESET}  "
            f"RPS={CYAN}{snap['total_rps']:.1f}{RESET}  "
            f"errors={_color_error_rate(snap['overall_error_rate'])}"
        )
        lines.append(f"{BOLD}{'─'*80}{RESET}")

        # ── 表頭 ──
        lines.append(
            f"{BOLD}"
            f"{'Task':<28} {'Reqs':>6} {'Fail':>5} {'Err%':>6} "
            f"{'RPS':>6} {'Avg':>7} {'P50':>7} {'P95':>7} {'P99':>7} {'Max':>7}"
            f"{RESET}"
        )
        lines.append("─" * 80)

        max_rps = max((t["rps"] for t in tasks), default=1) or 1

        for t in tasks:
            name = t["name"][:27]
            err_str = _color_error_rate(t["error_rate"])
            p95_str = _color_p95(t["p95_ms"])
            bar = DIM + _bar(t["rps"], max_rps) + RESET

            lines.append(
                f"{name:<28} {t['total']:>6} {t['failures']:>5} {err_str:>14} "
                f"{t['rps']:>6.1f} {t['avg_ms']:>7.0f} {t['p50_ms']:>7.0f} "
                f"{p95_str:>15} {t['p99_ms']:>7.0f} {t['max_ms']:>7.0f}  {bar}"
            )

        lines.append(f"{DIM}{'─'*80}{RESET}")
        lines.append(
            f"{DIM}  [單位: ms] Ctrl+C 停止測試{RESET}"
        )

        output = "\n".join(lines)

        if not final and self._last_line_count > 0:
            # 移到上方覆寫（ANSI escape）
            sys.stdout.write(f"\033[{self._last_line_count}A\033[J")

        sys.stdout.write(output + "\n")
        sys.stdout.flush()
        self._last_line_count = len(lines) + 1
