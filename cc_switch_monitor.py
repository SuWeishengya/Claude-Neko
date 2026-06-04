#!/usr/bin/env python3
"""
CC Switch 数据库监控 → Desktop Buddy 桥接
用 watchdog 监控 SQLite 文件变化，实时推送给桌面宠物
"""

import json, time, urllib.request, sqlite3, sys, threading
from pathlib import Path
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
DB_PATH = Path.home() / ".cc-switch" / "cc-switch.db"
POLL_INTERVAL = 5  # watchdog 模式下的兜底轮询间隔（秒）
DEBOUNCE_MS = 200  # 防抖：连续写入只处理最后一次


def post(data):
    try:
        req = urllib.request.Request(
            f"http://{CONFIG['host']}:{CONFIG['port']}/api/hook",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def query_db(sql, params=()):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def get_active_session():
    rows = query_db(
        "SELECT model, input_tokens, output_tokens, latency_ms, created_at "
        "FROM proxy_request_logs WHERE created_at > ? ORDER BY created_at DESC LIMIT 1",
        (int(time.time()) - 30,)
    )
    if rows:
        r = rows[0]
        return {
            "model": r["model"],
            "tokens": (r["input_tokens"] or 0) + (r["output_tokens"] or 0),
            "latency_ms": r["latency_ms"],
            "age_seconds": int(time.time()) - r["created_at"],
        }
    return None


def get_today_stats():
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    rows = query_db(
        "SELECT SUM(input_tokens) as inp, SUM(output_tokens) as outp, "
        "SUM(cache_read_tokens) as cache_read, SUM(cache_creation_tokens) as cache_create, "
        "COUNT(*) as cnt, "
        "SUM(CAST(total_cost_usd AS REAL)) as cost "
        "FROM proxy_request_logs WHERE created_at >= ?",
        (today_start,)
    )
    if rows and rows[0]["inp"] is not None:
        r = rows[0]
        return {
            "tokens_today": (r["inp"] or 0) + (r["outp"] or 0) + (r["cache_read"] or 0) + (r["cache_create"] or 0),
            "input_tokens": r["inp"] or 0,
            "output_tokens": r["outp"] or 0,
            "cache_tokens": (r["cache_read"] or 0) + (r["cache_create"] or 0),
            "request_count": r["cnt"] or 0,
            "cost_today": round(r["cost"] or 0, 4),
        }
    return {"tokens_today": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_tokens": 0, "request_count": 0, "cost_today": 0}


def get_recent_models(limit=3):
    rows = query_db(
        "SELECT model, COUNT(*) as cnt, SUM(input_tokens+output_tokens) as toks "
        "FROM proxy_request_logs WHERE created_at > ? "
        "GROUP BY model ORDER BY toks DESC LIMIT ?",
        (int(time.time()) - 3600, limit)
    )
    return [{"model": r["model"], "count": r["cnt"], "tokens": r["toks"] or 0} for r in rows]


def get_total_tokens():
    rows = query_db(
        "SELECT SUM(input_tokens+output_tokens+cache_read_tokens+cache_creation_tokens) as total "
        "FROM proxy_request_logs"
    )
    if rows and rows[0]["total"]:
        return rows[0]["total"]
    return 0


last_request_count = 0


def check_and_push():
    """查询数据库，构造状态推送"""
    global last_request_count

    stats = get_today_stats()
    active = get_active_session()
    models = get_recent_models()

    if active and active["age_seconds"] < 10:
        mode = "attention"
        msg = f"{active['model']} ({active['tokens']} tok)"
    elif active and active["age_seconds"] < 30:
        mode = "attention"
        msg = f"{active['model']} (recent)"
    else:
        mode = "idle"
        if models:
            msg = f"Today: {stats['request_count']} req, ${stats['cost_today']:.2f}"
        else:
            msg = f"Today: {stats['request_count']} requests"

    new_requests = stats["request_count"] - last_request_count
    if new_requests > 0:
        mode = "attention"
        msg = f"+{new_requests} new request(s)"
    last_request_count = stats["request_count"]

    state_update = {
        "type": "hook",
        "event": "cc_switch_update",
        "mode": mode,
        "msg": msg,
        "tokens_today": stats["tokens_today"],
        "tokens": stats["tokens_today"],
        "tokens_total": get_total_tokens(),
        "total": 1 if active else 0,
        "running": 1 if mode == "attention" else 0,
        "model": models[0]["model"] if models else "",
        "cost_today": stats["cost_today"],
        "request_count": stats["request_count"],
        "connected": True,
    }
    post(state_update)


# ─── 防抖逻辑 ─────────────────────────────────────────────────
_timer = None
_lock = threading.Lock()


def schedule_push():
    """防抖：200ms 内的连续文件变更只触发最后一次"""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(DEBOUNCE_MS / 1000, check_and_push)
        _timer.start()


# ─── watchdog 文件监控 ─────────────────────────────────────────
class DBChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self.db_name = DB_PATH.name

    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).name == self.db_name:
            schedule_push()

    def on_created(self, event):
        if not event.is_directory and Path(event.src_path).name == self.db_name:
            schedule_push()

    def on_closed(self, event):
        if not event.is_directory and Path(event.src_path).name == self.db_name:
            schedule_push()


# ─── 兜底轮询（watchdog 失效时用）─────────────────────────────
def fallback_poll():
    while True:
        try:
            check_and_push()
        except Exception as e:
            print(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


# ─── 启动 ─────────────────────────────────────────────────────
def main():
    print(f"CC Switch monitor started")
    print(f"  DB: {DB_PATH}")

    if not DB_PATH.exists():
        print(f"  CC Switch DB not found: {DB_PATH}")
        sys.exit(1)

    if HAS_WATCHDOG:
        db_dir = str(DB_PATH.parent)
        handler = DBChangeHandler()
        observer = Observer()
        observer.schedule(handler, db_dir, recursive=False)
        observer.start()
        print(f"  Mode: watchdog (file watching)")
    else:
        print(f"  Mode: polling (watchdog not installed)")

    # 启动时先推一次
    try:
        check_and_push()
    except Exception:
        pass

    try:
        fallback_poll()
    except KeyboardInterrupt:
        if HAS_WATCHDOG:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()
