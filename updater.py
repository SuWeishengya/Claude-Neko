#!/usr/bin/env python3
"""
Claude Neko — 在线更新模块
检查 GitHub Release、下载、安装、回滚
"""

import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

INSTALL_DIR = Path.home() / ".local" / "share" / "claude-neko"

def _get_github_token():
    """从 git credential 获取 GitHub token"""
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True, text=True, timeout=5)
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None
VERSION_FILE = INSTALL_DIR / "version.json"
BACKUP_DIR = Path.home() / ".local" / "share" / "claude-neko.bak"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"

# 不会被更新覆盖的文件/目录
SKIP_FILES = {"venv", "config.json", "__pycache__"}


def get_current_version():
    """读取当前版本号"""
    try:
        data = json.loads(VERSION_FILE.read_text())
        return data.get("version", "0.0.0")
    except (FileNotFoundError, json.JSONDecodeError):
        return "0.0.0"


def _parse_version(v):
    """将版本号字符串转为可比较的元组"""
    try:
        parts = v.lstrip("v").split(".")
        return tuple(int(p) for p in parts[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_github_update(timeout=10):
    """
    检查 GitHub 最新 release。
    返回: {available, version, url, body} 或 None（网络错误时）
    """
    try:
        version_data = json.loads(VERSION_FILE.read_text())
        repo = version_data.get("repo", "SuWeishengya/Claude-Neko")
    except (FileNotFoundError, json.JSONDecodeError):
        repo = "SuWeishengya/Claude-Neko"

    url = GITHUB_API.format(repo=repo)
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Claude-Neko-Updater",
    }
    # 尝试使用 git credential 中的 token（避免 rate limit）
    token = _get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
    except Exception:
        return None

    remote_version = data.get("tag_name", "").lstrip("v")
    current = get_current_version()

    if _parse_version(remote_version) > _parse_version(current):
        # 找 zipball_url
        zip_url = data.get("zipball_url", "")
        body = data.get("body", "")[:200]  # 更新日志截断
        return {
            "available": True,
            "version": remote_version,
            "current": current,
            "url": zip_url,
            "body": body,
        }

    return {
        "available": False,
        "version": remote_version,
        "current": current,
        "url": "",
        "body": "",
    }


def download_and_install(update_url, progress_callback=None):
    """
    下载并安装更新。
    progress_callback(step, detail) 用于汇报进度。
    返回: (success, message)
    """
    def report(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    # 1. 下载
    report("downloading", "正在下载...")
    try:
        tmp_dir = tempfile.mkdtemp(prefix="neko-update-")
        zip_path = os.path.join(tmp_dir, "update.zip")
        req = urllib.request.Request(update_url, headers={"User-Agent": "Claude-Neko-Updater"})
        resp = urllib.request.urlopen(req, timeout=60)
        with open(zip_path, "wb") as f:
            shutil.copyfileobj(resp, f)
    except Exception as e:
        return False, f"下载失败: {e}"

    # 2. 解压
    report("extracting", "正在解压...")
    try:
        extract_dir = os.path.join(tmp_dir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        # GitHub zip 内有一层目录 (user-repo-hash/)
        inner_dirs = [d for d in Path(extract_dir).iterdir() if d.is_dir()]
        if len(inner_dirs) == 1:
            source_dir = inner_dirs[0]
        else:
            source_dir = Path(extract_dir)
    except Exception as e:
        _cleanup(tmp_dir)
        return False, f"解压失败: {e}"

    # 3. 备份
    report("backing_up", "正在备份...")
    try:
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)
        shutil.copytree(INSTALL_DIR, BACKUP_DIR, ignore=shutil.ignore_patterns(
            "venv", "__pycache__", "*.pyc", "neko.log", "pids.txt"
        ))
    except Exception as e:
        _cleanup(tmp_dir)
        return False, f"备份失败: {e}"

    # 4. 安装新文件
    report("installing", "正在安装...")
    try:
        _copy_update(source_dir, INSTALL_DIR)
    except Exception as e:
        # 回滚
        report("rolling_back", "安装失败，正在回滚...")
        _rollback()
        _cleanup(tmp_dir)
        return False, f"安装失败: {e}"

    # 5. 清理
    _cleanup(tmp_dir)

    # 6. 同步到开发目录（如果存在）
    dev_dir = Path.home() / "Work" / "Claude-Neko"
    if dev_dir.exists() and dev_dir != INSTALL_DIR:
        try:
            _copy_update(source_dir, dev_dir)
        except Exception:
            pass  # 非关键，忽略

    report("done", "更新完成！")
    return True, "更新成功"


def _copy_update(src, dst):
    """将更新文件复制到目标目录（跳过保护文件）"""
    src = Path(src)
    dst = Path(dst)
    for item in src.iterdir():
        if item.name in SKIP_FILES:
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _rollback():
    """从备份回滚"""
    if BACKUP_DIR.exists():
        for item in BACKUP_DIR.iterdir():
            target = INSTALL_DIR / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)


def _cleanup(tmp_dir):
    """清理临时目录"""
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def restart_neko():
    """重启 neko"""
    subprocess.Popen(["neko", "restart"])


# ─── CLI 入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        result = check_github_update()
        if result is None:
            print("检查失败，请检查网络")
        elif result["available"]:
            print(f"有新版本: v{result['version']} (当前 v{result['current']})")
            print(f"更新日志: {result['body'][:100]}")
        else:
            print(f"已是最新版本: v{result['current']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "version":
        print(f"v{get_current_version()}")
    else:
        print("用法: updater.py [check|version]")
