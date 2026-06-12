#!/usr/bin/env python3
"""
Claude Neko — 跨平台工具模块
运行时检测平台，统一路径和进程管理。
"""

import os
import sys
import ctypes
from pathlib import Path

# ─── 平台检测 ─────────────────────────────────────────────

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_WAYLAND = False

if IS_LINUX:
    IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE") == "wayland"


# ─── 目录路径 ─────────────────────────────────────────────

def get_state_dir():
    """运行时数据目录（日志、session 注册表、偏好）"""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "claude-neko"
    return Path.home() / ".local" / "state" / "claude-neko"


def get_install_dir():
    """安装目录（代码 + venv + assets）"""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(base) / "claude-neko" / "app"
    return Path.home() / ".local" / "share" / "claude-neko"


def get_claude_dir():
    """Claude Code 配置目录"""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "Claude"
    return Path.home() / ".claude"


def get_claude_settings():
    """Claude Code settings.json 路径"""
    return get_claude_dir() / "settings.json"


def get_claude_sessions_dir():
    """Claude Code sessions 目录"""
    return get_claude_dir() / "sessions"


def get_claude_projects_dir():
    """Claude Code projects 目录"""
    return get_claude_dir() / "projects"


def get_venv_python():
    """venv 中 python 可执行文件路径"""
    if IS_WINDOWS:
        return str(get_install_dir() / "venv" / "Scripts" / "python.exe")
    return str(get_install_dir() / "venv" / "bin" / "python")


def get_tmp_dir():
    """临时目录"""
    if IS_WINDOWS:
        return Path(os.environ.get("TEMP", str(Path.home() / "AppData" / "Local" / "Temp")))
    return Path("/tmp")


# ─── 进程管理 ─────────────────────────────────────────────

def process_exists(pid):
    """检查进程是否存在（跨平台）"""
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass

    if IS_WINDOWS:
        try:
            handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


# ─── 打开文件/URL ──────────────────────────────────────────

def open_with_default(path_or_url):
    """用系统默认程序打开文件或 URL"""
    if IS_WINDOWS:
        os.startfile(path_or_url)
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(path_or_url)])


# ─── 端口检查 ──────────────────────────────────────────────

def is_port_in_use(port):
    """检查端口是否被占用"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return False
    except OSError:
        return True
