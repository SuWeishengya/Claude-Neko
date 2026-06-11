#!/usr/bin/env python3
"""
Claude Code Hook → Desktop Neko 桥接
从 stdin 读取 Claude Code hook 事件，转发到对应 server.py
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

STATE_DIR = Path.home() / ".local" / "state" / "claude-desktop-pet"
SESSIONS_DIR = STATE_DIR / "sessions"


def find_server_port(session_id: str) -> "int | None":
    """从注册表查找 session 对应的 server 端口"""
    if not session_id or not re.match(r'^[a-zA-Z0-9_-]+$', session_id):
        return None
    reg_file = SESSIONS_DIR / f"{session_id}.json"
    if not reg_file.exists():
        return None
    try:
        data = json.loads(reg_file.read_text())
        # 检查 server 进程是否还活着
        pid = data.get("pid_server")
        if pid:
            try:
                os.kill(pid, 0)  # 不发送信号，只检查进程存在
            except ProcessLookupError:
                # 进程已死，清理注册文件
                reg_file.unlink(missing_ok=True)
                return None
        port = data.get("port")
        if port and 9100 <= port <= 9999:
            return port
        return None
    except Exception as e:
        print(f"hook_bridge: failed to read registration: {e}", file=sys.stderr)
        return None


def post_to_server(port: int, endpoint: str, data: dict):
    """POST 数据到 server.py"""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{endpoint}",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
    except Exception as e:
        print(f"hook_bridge: {endpoint} failed: {e}", file=sys.stderr)


def main():
    # 读取 stdin（限制 1MB 防止异常大的输入）
    try:
        raw = sys.stdin.read(1024 * 1024)
        if not raw:
            return
        # 检查 JSON 基本完整性（以 } 结尾）
        raw = raw.strip()
        if not raw.endswith('}'):
            return
        event_data = json.loads(raw)
    except Exception:
        return

    session_id = event_data.get("session_id")
    hook_event = event_data.get("hook_event_name", "")

    # 查找 server 端口（注册表优先，fallback 到 9100）
    port = find_server_port(session_id)
    if not port:
        # 注册表找不到 → 尝试 9100（兼容手动模式）
        try:
            urllib.request.urlopen("http://127.0.0.1:9100/api/state", timeout=1)
            port = 9100
        except Exception:
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
            "tool_name": tool_name,
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
            "event": "post_tool_use_failure",
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

    elif hook_event == "UserPromptSubmit":
        # 用户提交问题 → 小猫进入 think
        post_to_server(port, "/api/hook", {
            "event": "user_prompt_submit",
            "msg": "Thinking...",
        })

    elif hook_event == "SessionEnd":
        post_to_server(port, "/api/shutdown", {})


if __name__ == "__main__":
    main()
