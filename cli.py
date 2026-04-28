"""
cli.py — 命令列入口
用法：python -m pyload -f scenario.py -u 50 -r 5 -t 60
"""
import argparse
import importlib.util
import sys
import os
import signal

from .stats import StatsCollector
from .engine import LoadEngine
from .console import ConsoleReporter
from .reporter import save_html, save_json
from .user import HttpUser


def load_user_class(filepath: str) -> type[HttpUser]:
    """從指定 .py 檔案動態載入 HttpUser 子類別"""
    spec = importlib.util.spec_from_file_location("scenario", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidates = []
    for name in dir(module):
        obj = getattr(module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, HttpUser)
            and obj is not HttpUser
        ):
            candidates.append(obj)

    if not candidates:
        print(f"[PyLoad] 錯誤：{filepath} 中找不到 HttpUser 子類別")
        sys.exit(1)
    if len(candidates) > 1:
        names = ", ".join(c.__name__ for c in candidates)
        print(f"[PyLoad] 找到多個 User 類別：{names}，使用第一個：{candidates[0].__name__}")
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m pyload",
        description="PyLoad — Python 輕量級 API 負載測試工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python -m pyload -f examples/jsonplaceholder.py -u 20 -r 5 -t 30
  python -m pyload -f myscenario.py -u 100 -r 10 -t 120 --html report.html --json result.json
        """
    )
    p.add_argument("-f", "--file",       required=True,       help="情境檔案路徑 (.py)")
    p.add_argument("-u", "--users",      type=int, default=10, help="虛擬使用者數量 (預設: 10)")
    p.add_argument("-r", "--spawn-rate", type=float, default=1, help="每秒新增使用者數 (預設: 1)")
    p.add_argument("-t", "--run-time",   type=float, default=0, help="執行秒數，0=無限 (預設: 0)")
    p.add_argument("--interval",         type=float, default=2.0, help="Console 更新間隔秒數 (預設: 2)")
    p.add_argument("--html",             default="report.html", help="HTML 報告路徑 (預設: report.html)")
    p.add_argument("--json",             default="",            help="JSON 報告路徑 (空=不輸出)")
    p.add_argument("--no-html",          action="store_true",   help="不產生 HTML 報告")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"[PyLoad] 找不到檔案：{args.file}")
        sys.exit(1)

    user_class = load_user_class(args.file)
    host = getattr(user_class, "host", "")

    print(f"\n[PyLoad] 載入情境：{user_class.__name__}  host={host}")
    print(f"[PyLoad] 使用者={args.users}  spawn_rate={args.spawn_rate}/s  "
          f"執行時間={'∞' if args.run_time == 0 else f'{args.run_time}s'}\n")

    stats = StatsCollector()
    engine = LoadEngine(
        user_class=user_class,
        stats=stats,
        num_users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time,
    )
    reporter = ConsoleReporter(stats, engine, interval=args.interval)

    def _shutdown(sig=None, frame=None):
        print("\n[PyLoad] 收到停止訊號，正在結束…")
        engine.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    engine.start()
    reporter.start()

    try:
        engine.wait()
    finally:
        engine.stop()
        reporter.stop()

        print()
        if not args.no_html:
            save_html(stats, path=args.html, host=host)
        if args.json:
            save_json(stats, path=args.json)
        print("[PyLoad] 完成！")


if __name__ == "__main__":
    main()
