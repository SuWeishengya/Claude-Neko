#!/usr/bin/env python3
"""
Claude Neko — HTTP 后端
接收监控数据，维护全局状态，供桌面悬浮窗轮询
支持多实例：每只小猫独立端口，绑定一个 Claude 会话
"""

import json
import time
import argparse
import threading
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler
import socketserver
import urllib.parse

# ─── 命令行参数 ─────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=9100)
parser.add_argument("--session-id", type=str, default=None)
parser.add_argument("--state-dir", type=str,
                    default=str(Path.home() / ".local" / "state" / "claude-desktop-pet"))
args = parser.parse_args()

# ─── 运行时目录 ─────────────────────────────────────────────
STATE_DIR = Path(args.state_dir)
SESSIONS_DIR = STATE_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

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
    "session_id":    args.session_id,
    "shutdown":      False,
}

# 最后一次收到事件的时间戳（用于心跳超时）
# 初始化为 inf，等第一个 hook 事件到达后才开始计时
# 避免 server 启动后、Claude 发出第一个 tool_use 前就被心跳超时杀掉
last_event_time = float('inf')

# 线程锁：保护 state 字典的并发读写
state_lock = threading.Lock()

# ─── 注册文件管理 ─────────────────────────────────────────────

def write_registration(port):
    """写入注册文件"""
    if not args.session_id:
        return
    reg_file = SESSIONS_DIR / f"{args.session_id}.json"
    reg_data = {
        "session_id": args.session_id,
        "port": port,
        "pid_server": __import__('os').getpid(),
        "created_at": datetime.now().isoformat(),
    }
    reg_file.write_text(json.dumps(reg_data, ensure_ascii=False, indent=2))


def remove_registration():
    """删除注册文件"""
    if not args.session_id:
        return
    reg_file = SESSIONS_DIR / f"{args.session_id}.json"
    reg_file.unlink(missing_ok=True)

# ─── 心跳超时检查 ─────────────────────────────────────────────

def heartbeat_checker():
    """后台线程：检查心跳超时，无事件则自动关闭"""
    global last_event_time
    while True:
        time.sleep(2)
        with state_lock:
            if state["shutdown"]:
                break
        if args.session_id and last_event_time != float('inf') and (time.time() - last_event_time > 120):
            print("⏰ 心跳超时（120 秒无事件），自动关闭")
            do_shutdown()
            break


shutdown_event = threading.Event()
httpd_ref = None
_shutdown_started = False

def do_shutdown():
    """优雅关闭（防重复调用）"""
    global _shutdown_started
    if _shutdown_started:
        return
    _shutdown_started = True
    with state_lock:
        state["shutdown"] = True
    remove_registration()
    # 延迟退出，让 buddy_widget 有时间收到 shutdown 信号
    def _exit():
        time.sleep(5)
        if httpd_ref:
            httpd_ref.shutdown()  # 停止 serve_forever()
        shutdown_event.set()
    threading.Thread(target=_exit, daemon=True).start()

# ─── HTTP 服务 ─────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            with state_lock:
                data = json.dumps(state, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self):
        global last_event_time
        # Content-Length 上限检查（1MB），防止内存耗尽攻击
        length = int(self.headers.get("Content-Length", 0))
        if length > 1_000_000:
            self.send_error(413, "Request too large")
            return
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/shutdown":
            self.rfile.read(length) if length else None
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            do_shutdown()
            return

        if parsed.path == "/api/permission":
            body = json.loads(self.rfile.read(length)) if length else {}
            decision = body.get("decision", "deny")
            prompt_id = body.get("id")
            with state_lock:
                if state["prompt"] and state["prompt"]["id"] == prompt_id:
                    if decision == "once":
                        state["approve_count"] += 1
                        state["mode"] = "heart"
                        state["msg"] = "Approved!"
                    else:
                        state["deny_count"] += 1
                        state["mode"] = "idle"
                        state["msg"] = "Denied"
                    state["prompt"] = None
                    state["waiting"] = 0
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            return

        if parsed.path == "/api/hook":
            global last_event_time
            last_event_time = time.time()
            try:
                body = json.loads(self.rfile.read(length)) if length else {}
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            event = body.get("event", "")

            # 等级计算表
            LEVEL_TABLE = [
                (0,1),(1_000_000,2),(5_000_000,3),(10_000_000,4),
                (50_000_000,5),(100_000_000,6),(500_000_000,7),
                (1_000_000_000,8),(5_000_000_000,9),(10_000_000_000,10),
            ]

            with state_lock:
                if event == "pre_tool_use":
                    state["running"] += 1
                    state["mode"] = "busy"
                    state["msg"] = body.get("msg", "")[:40]
                    state["connected"] = True
                    state["entries"] = [f"{datetime.now().strftime('%H:%M')} {state['msg']}"] + state["entries"][:9]

                elif event == "post_tool_use":
                    state["running"] = max(0, state["running"] - 1)
                    if state["running"] == 0 and state["waiting"] == 0:
                        state["mode"] = "idle"
                        state["msg"] = "Thinking"
                    else:
                        state["msg"] = body.get("msg", "")[:40]

                elif event == "stop":
                    state["running"] = 0
                    state["waiting"] = 0
                    state["mode"] = "idle"
                    state["msg"] = "Ready"

                elif event == "permission_request":
                    prompt = body.get("prompt")
                    # 校验 prompt 结构，防止注入恶意数据
                    if isinstance(prompt, dict) and "id" in prompt:
                        state["mode"] = "attention"
                        state["waiting"] = 1
                        state["prompt"] = prompt
                        state["msg"] = body.get("msg", "Approval needed")

                elif event == "session_end":
                    # 状态清理在锁内（与 stop 事件一致），HTTP 响应在锁外
                    state["running"] = 0
                    state["waiting"] = 0
                    state["mode"] = "idle"
                    state["msg"] = "Session ended"

                elif event == "cc_switch_update":
                    # 只允许已知字段，防止注入任意 state
                    ALLOWED_FIELDS = {"mode", "msg", "tokens_today", "tokens", "tokens_total", "total", "running"}
                    for key in ALLOWED_FIELDS:
                        if key in body:
                            state[key] = body[key]
                    state["connected"] = True
                    state["entries"] = [f"{datetime.now().strftime('%H:%M')} {state.get('msg', '')}"] + state["entries"][:9]
                    for th, lv in LEVEL_TABLE:
                        if state["tokens_total"] >= th:
                            state["level"] = lv

            # session_end 在锁外处理：do_shutdown 内部也要获取 state_lock，
            # 如果在锁内调用会导致死锁（state_lock 不是 RLock）
            if event == "session_end":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
                do_shutdown()
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            return

        self.send_error(404)

    def log_message(self, format, *args):
        pass  # 静默日志


def start_http_server():
    global httpd_ref
    class ReusableTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    httpd = ReusableTCPServer(("127.0.0.1", args.port), Handler)
    httpd_ref = httpd
    httpd.serve_forever()


def main():
    print(f"\n🐾 Claude Neko")
    print(f"{'─' * 40}")
    print(f"🌐 http://127.0.0.1:{args.port}")
    if args.session_id:
        print(f"🔗 Session: {args.session_id[:12]}...")
    print(f"{'─' * 40}\n")

    # 写注册文件
    write_registration(args.port)

    # 启动心跳检查线程（仅自动模式）
    if args.session_id:
        threading.Thread(target=heartbeat_checker, daemon=True).start()

    # 启动 HTTP 服务
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    # 等待关闭信号
    try:
        while not shutdown_event.is_set():
            shutdown_event.wait(timeout=1)
    except KeyboardInterrupt:
        print("\nBye!")
    finally:
        remove_registration()


if __name__ == "__main__":
    main()
