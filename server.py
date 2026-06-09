#!/usr/bin/env python3
"""
Claude Desktop Buddy — HTTP 后端
接收监控数据，维护全局状态，供桌面悬浮窗轮询
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading
import urllib.parse

# ─── 配置 ───────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    default = {
        "port": 8080,
        "host": "127.0.0.1",
    }
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            user = json.load(f)
            default.update(user)
    return default

CFG = load_config()

# ─── 全局状态 ─────────────────────────────────────────────────
state = {
    "mode":          "idle",       # sleep|idle|busy|attention|celebrate|heart|dizzy
    "total":         0,
    "running":       0,
    "waiting":       0,
    "msg":           "",
    "entries":       [],
    "tokens":        0,
    "tokens_today":  0,
    "prompt":        None,
    "connected":     False,
    "level":         1,
    "approve_count": 0,
    "deny_count":    0,
    "level_up_at":   0,
    "last_update":   0,
    "tokens_total":  0,
    "pet":           {"style": "cat", "color": "#FF9F43"},
}

# ─── HTTP 服务 ─────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(state, ensure_ascii=False).encode())
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/permission":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            decision = body.get("decision", "deny")
            prompt_id = body.get("id")
            if state["prompt"] and state["prompt"]["id"] == prompt_id:
                if decision == "once":
                    state["approve_count"] += 1
                else:
                    state["deny_count"] += 1
                state["prompt"] = None
                state["waiting"] = 0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            return
        if parsed.path == "/api/hook":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            event = body.get("event", "")
            if event == "pre_tool_use":
                state["running"] = max(1, state["running"])
                state["mode"] = "busy"
                state["msg"] = body.get("msg", "")
                state["connected"] = True
                state["entries"] = [f"{datetime.now().strftime('%H:%M')} {state['msg']}"] + state["entries"][:9]
            elif event == "post_tool_use":
                state["running"] = max(0, state["running"] - 1)
                if state["running"] == 0 and state["waiting"] == 0:
                    state["mode"] = "idle"
                state["msg"] = body.get("msg", "")
            elif event == "stop":
                state["running"] = 0
                state["waiting"] = 0
                state["mode"] = "idle"
                state["msg"] = body.get("msg", "任务完成 ✓")
            elif event == "cc_switch_update":
                state["mode"] = body.get("mode", "idle")
                state["msg"] = body.get("msg", "")
                state["tokens_today"] = body.get("tokens_today", state["tokens_today"])
                state["tokens"] = body.get("tokens", state["tokens"])
                state["tokens_total"] = body.get("tokens_total", state["tokens_total"])
                state["total"] = body.get("total", 0)
                state["running"] = body.get("running", 0)
                state["connected"] = True
                state["entries"] = [f"{datetime.now().strftime('%H:%M')} {state['msg']}"] + state["entries"][:9]
                # 等级计算
                LEVEL_TABLE = [
                    (0,1),(1_000_000,2),(5_000_000,3),(10_000_000,4),
                    (50_000_000,5),(100_000_000,6),(500_000_000,7),
                    (1_000_000_000,8),(5_000_000_000,9),(10_000_000_000,10),
                ]
                for th, lv in LEVEL_TABLE:
                    if state["tokens_total"] >= th:
                        state["level"] = lv
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass  # 静默日志

def start_http_server():
    with socketserver.TCPServer((CFG["host"], CFG["port"]), Handler) as httpd:
        httpd.serve_forever()

async def main():
    url = f"http://{CFG['host']}:{CFG['port']}"
    print(f"\n🐾 Claude Desktop Buddy")
    print(f"{'─' * 40}")
    print(f"🌐 {url}")
    print(f"{'─' * 40}\n")

    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    print("按 Ctrl+C 退出\n")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
