#!/usr/bin/env python3
"""
Claude Code Hook → Desktop Neko 桥接
从 stdin 读取 Claude Code hook 事件，转发到对应 server.py
"""

import json
import sys
import urllib.request
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "claude-desktop-pet"
SESSIONS_DIR = STATE_DIR / "sessions"


def find_server_port(session_id: str) -> int | None:
    """从注册表查找 session 对应的 server 端口"""
    import re
    if not session_id or not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        return None
    reg_file = SESSIONS_DIR / f"{session_id}.json"
    if not reg_file.exists():
        return None
    try:
        data = json.loads(reg_file.read_text())
        # 检查 server 进程是否还活着
        import os
        pid = data.get("pid_server")
        if pid:
            try:
                os.kill(pid, 0)  # 不发送信号，只检查进程存在
            except ProcessLookupError:
                # 进程已死，清理注册文件
                reg_file.unlink(missing_ok=True)
                return None
        return data.get("port")
    except Exception:
        return None


def post_to_server(port: int, endpoint: str, data: dict):
    """POST 数据到 server.py"""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{endpoint}",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception as e:
        import sys
        print(f"hook_bridge: {endpoint} failed: {e}", file=sys.stderr)


def main():
    # 读取 stdin
    try:
        raw = sys.stdin.read()
        if not raw:
            return
        event_data = json.loads(raw)
    except Exception:
        return

    session_id = event_data.get("session_id")
    hook_event = event_data.get("hook_event_name", "")

    # 查找 server 端口
    port = find_server_port(session_id)
    if not port:
        # server 未运行，静默退出
        return

    # 根据事件类型构造转发数据
    if hook_event == "PreToolUse":
        tool_name = event_data.get("tool_name", "")
        tool_input = event_data.get("tool_input", {})
        # 构造简短描述
        desc = ""
        if tool_name == "Bash":
            cmd = tool_input.get("command", "")
            desc = cmd[:30] if cmd else ""
        elif tool_name in ("Edit", "Write"):
            desc = tool_input.get("file_path", "").split("/")[-1]
        elif tool_name == "Read":
            desc = tool_input.get("file_path", "").split("/")[-1]
        else:
            desc = str(tool_input)[:30]
        msg = f"{tool_name}: {desc}" if desc else tool_name
        post_to_server(port, "/api/hook", {
            "event": "pre_tool_use",
            "msg": msg,
        })

    elif hook_event == "PostToolUse":
        tool_name = event_data.get("tool_name", "")
        post_to_server(port, "/api/hook", {
            "event": "post_tool_use",
            "msg": f"Done: {tool_name}",
        })

    elif hook_event == "PostToolUseFailure":
        tool_name = event_data.get("tool_name", "")
        post_to_server(port, "/api/hook", {
            "event": "post_tool_use",
            "msg": f"Failed: {tool_name}",
        })

    elif hook_event == "Stop":
        post_to_server(port, "/api/hook", {
            "event": "stop",
            "msg": "Done ✓",
        })

    elif hook_event == "PermissionRequest":
        tool_name = event_data.get("tool_name", "")
        post_to_server(port, "/api/hook", {
            "event": "permission_request",
            "msg": f"Approve: {tool_name}",
            "prompt": {
                "id": event_data.get("permission_request_id", ""),
                "tool": tool_name,
                "hint": str(event_data.get("tool_input", {}))[:50],
            },
        })

    elif hook_event == "SessionEnd":
        post_to_server(port, "/api/shutdown", {})

    elif hook_event == "SessionStart":
        # SessionStart 由 launch.sh 处理，这里不转发
        pass


if __name__ == "__main__":
    main()
