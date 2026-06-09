#!/usr/bin/env python3
"""
Claude Code 会话监控 → Desktop Neko 桥接
直接从 ~/.claude 的 session jsonl 文件读取 token 使用数据
"""

import json, time, urllib.request, sys, threading, glob, os
from pathlib import Path
from datetime import datetime

CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())
CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"

POLL_INTERVAL = 3  # 轮询间隔（秒）

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


def get_active_session():
    """检查是否有活跃的 Claude 会话"""
    try:
        for f in SESSIONS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            if data.get("status") == "busy":
                started = data.get("startedAt", 0)
                age = (time.time() * 1000 - started) / 1000
                if age < 300:  # 5 分钟内有活动
                    return {
                        "sessionId": data.get("sessionId"),
                        "cwd": data.get("cwd"),
                        "age_seconds": int(age),
                    }
    except Exception:
        pass
    return None


def count_tokens_from_sessions():
    """从所有 session jsonl 文件中统计 token 使用量"""
    total_input = 0
    total_output = 0
    session_count = 0
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_input = 0
    today_output = 0

    # 扫描所有项目的 session 文件
    for jsonl in PROJECTS_DIR.rglob("*.jsonl"):
        # 跳过 subagents 目录
        if "subagents" in str(jsonl):
            continue
        try:
            session_count += 1
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # 只统计 assistant 消息的 usage
                        if entry.get("type") == "assistant":
                            msg = entry.get("message", {})
                            usage = msg.get("usage", {})
                            inp = usage.get("input_tokens", 0)
                            out = usage.get("output_tokens", 0)
                            total_input += inp
                            total_output += out

                            # 统计今日用量
                            ts = entry.get("timestamp", "")
                            if ts:
                                try:
                                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                    if dt.timestamp() >= today_start:
                                        today_input += inp
                                        today_output += out
                                except Exception:
                                    pass
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return {
        "total_tokens": total_input + total_output,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "today_tokens": today_input + today_output,
        "session_count": session_count,
    }


# 等级表
LEVEL_TABLE = [
    (0, 1), (1_000_000, 2), (5_000_000, 3), (10_000_000, 4),
    (50_000_000, 5), (100_000_000, 6), (500_000_000, 7),
    (1_000_000_000, 8), (5_000_000_000, 9), (10_000_000_000, 10),
]


def calc_level(tokens):
    level = 1
    for th, lv in LEVEL_TABLE:
        if tokens >= th:
            level = lv
    return level


last_tokens = 0
last_mode = "idle"


def check_and_push():
    """查询数据，构造状态推送"""
    global last_tokens, last_mode

    active = get_active_session()
    stats = count_tokens_from_sessions()

    # 判断状态
    if active:
        mode = "attention"
        msg = f"Working... ({active['age_seconds']}s ago)"
    else:
        mode = "idle"
        msg = f"Sessions: {stats['session_count']}"

    # 检测是否升级
    new_level = calc_level(stats["total_tokens"])
    old_level = calc_level(last_tokens)
    if new_level > old_level:
        mode = "celebrate"
        msg = f"Level Up! Lv.{old_level} → Lv.{new_level}"

    last_tokens = stats["total_tokens"]
    last_mode = mode

    state_update = {
        "type": "hook",
        "event": "cc_switch_update",
        "mode": mode,
        "msg": msg,
        "tokens_today": stats["today_tokens"],
        "tokens": stats["today_tokens"],
        "tokens_total": stats["total_tokens"],
        "total": stats["session_count"],
        "running": 1 if active else 0,
        "connected": True,
    }
    post(state_update)


def main():
    print(f"Claude Code Monitor started")
    print(f"  Scanning: {PROJECTS_DIR}")

    # 启动时先推一次
    try:
        check_and_push()
    except Exception as e:
        print(f"Initial check error: {e}")

    try:
        while True:
            try:
                check_and_push()
            except Exception as e:
                print(f"Check error: {e}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
