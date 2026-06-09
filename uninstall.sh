#!/bin/bash
# Claude Neko — 卸载脚本

INSTALL_DIR="$HOME/.local/share/claude-desktop-pet"
STATE_DIR="$HOME/.local/state/claude-desktop-pet"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "🐾 Claude Neko 卸载程序"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 1. 停止所有运行中的小猫 ───────────────────────────────
echo ""
echo "🛑 停止运行中的小猫..."

# 停止所有注册的 server 进程
if [ -d "$STATE_DIR/sessions" ]; then
    for f in "$STATE_DIR/sessions"/*.json; do
        [ -f "$f" ] || continue
        PID=$(python3 -c "import json; print(json.load(open('$f')).get('pid_server',0))" 2>/dev/null)
        if [ -n "$PID" ] && [ "$PID" != "0" ]; then
            kill "$PID" 2>/dev/null && echo "  ✅ 停止 server (PID $PID)" || true
        fi
    done
fi

# 也杀掉所有 buddy_widget 进程
pkill -f "buddy_widget.py" 2>/dev/null && echo "  ✅ 停止 buddy_widget" || true
pkill -f "server.py.*--port" 2>/dev/null && echo "  ✅ 停止 server" || true

sleep 1

# ─── 2. 删除安装目录 ───────────────────────────────────────
echo ""
echo "📁 删除安装目录..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  ✅ 已删除 $INSTALL_DIR"
else
    echo "  ℹ️  安装目录不存在"
fi

# ─── 3. 删除运行时目录 ─────────────────────────────────────
echo ""
echo "📁 删除运行时目录..."
if [ -d "$STATE_DIR" ]; then
    rm -rf "$STATE_DIR"
    echo "  ✅ 已删除 $STATE_DIR"
else
    echo "  ℹ️  运行时目录不存在"
fi

# ─── 4. 从 settings.json 移除 hooks ────────────────────────
echo ""
echo "⚙️  移除 Claude Code hooks..."
if [ -f "$SETTINGS_FILE" ]; then
    python3 << 'PYEOF'
import json
from pathlib import Path

settings_file = Path.home() / ".claude" / "settings.json"
if not settings_file.exists():
    print("  ℹ️  settings.json 不存在")
    exit(0)

try:
    settings = json.loads(settings_file.read_text())
except json.JSONDecodeError:
    print("  ⚠️  settings.json 格式错误")
    exit(0)

if "hooks" in settings:
    # 只移除包含 claude-desktop-pet 的 hooks
    hooks = settings["hooks"]
    cleaned = {}
    removed = False
    for event, matchers in hooks.items():
        new_matchers = []
        for matcher in matchers:
            new_hooks = []
            for h in matcher.get("hooks", []):
                cmd = h.get("command", "")
                if "claude-desktop-pet" in cmd:
                    removed = True
                else:
                    new_hooks.append(h)
            if new_hooks:
                matcher["hooks"] = new_hooks
                new_matchers.append(matcher)
        if new_matchers:
            cleaned[event] = new_matchers
    settings["hooks"] = cleaned

    if removed:
        # 如果 hooks 为空，删除整个 key
        if not settings["hooks"]:
            del settings["hooks"]
        settings_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        print("  ✅ hooks 配置已移除")
    else:
        print("  ℹ️  未找到相关 hooks 配置")
else:
    print("  ℹ️  无 hooks 配置")
PYEOF
else
    echo "  ℹ️  settings.json 不存在"
fi

# ─── 5. 完成 ──────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 卸载完成！"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
