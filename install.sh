#!/bin/bash
# Claude Neko — 一键安装脚本
# 安装到 ~/.local/share/claude-neko/
# 配置全局 Claude Code hooks

set -e

INSTALL_DIR="$HOME/.local/share/claude-neko"
STATE_DIR="$HOME/.local/state/claude-neko"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🐾 Claude Neko 安装程序"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 1. 检测发行版，安装系统依赖 ─────────────────────────
echo ""
echo "📦 检测系统依赖..."

install_system_deps() {
    if command -v dnf &>/dev/null; then
        echo "  检测到 Fedora/RHEL，使用 dnf 安装..."
        sudo dnf install -y python3-gobject python3-cairo gtk3 python3-pillow 2>/dev/null || true
    elif command -v apt &>/dev/null; then
        echo "  检测到 Debian/Ubuntu，使用 apt 安装..."
        sudo apt install -y python3-gi python3-cairo gir1.2-gtk-3.0 python3-pil 2>/dev/null || true
    elif command -v pacman &>/dev/null; then
        echo "  检测到 Arch，使用 pacman 安装..."
        sudo pacman -S --noconfirm python-gobject gtk3 python-pillow 2>/dev/null || true
    else
        echo "  ⚠️  未知发行版，请手动安装: python3-gobject python3-cairo gtk3 python3-pillow"
    fi
}

install_system_deps

# 验证关键依赖是否可用
if ! python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null; then
    echo "  ⚠️  GTK3 绑定未安装成功，请手动安装: python3-gobject gtk3"
fi

# ─── 2. 创建 venv ─────────────────────────────────────────
echo ""
echo "🐍 创建 Python 虚拟环境..."

# 如果安装目录已存在 venv，保留；否则创建
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv --system-site-packages "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/pip" install -q pillow 2>/dev/null || true

# ─── 3. 复制代码到安装目录 ─────────────────────────────────
echo ""
echo "📁 安装到 $INSTALL_DIR ..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$STATE_DIR/sessions"

# 如果从安装目录调用（如 neko enable），跳过复制
if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
    echo "  已在安装目录，跳过文件复制"
else
    # 复制文件
    for f in server.py neko_widget.py hook_bridge.py launch.sh stop.sh neko config.json uninstall.sh; do
        if [ -f "$SCRIPT_DIR/$f" ]; then
            cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
        fi
    done

    # 复制 assets
    if [ -d "$SCRIPT_DIR/assets" ]; then
        cp -r "$SCRIPT_DIR/assets" "$INSTALL_DIR/"
    fi
fi

# 设置可执行权限（仅对存在的文件操作，避免 set -e 中止）
chmod +x "$INSTALL_DIR/launch.sh" "$INSTALL_DIR/stop.sh" "$INSTALL_DIR/hook_bridge.py" "$INSTALL_DIR/neko" 2>/dev/null || true

# 创建全局命令链接
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/neko" "$HOME/.local/bin/neko"

# ─── 4. 生成全局 hooks 配置 ─────────────────────────────────
echo ""
echo "⚙️  配置 Claude Code hooks..."

SETTINGS_FILE="$HOME/.claude/settings.json"
mkdir -p "$(dirname "$SETTINGS_FILE")"

# 用 python3 合并 hooks 配置（保留用户现有 hooks，追加而非覆盖）
python3 << 'PYEOF'
import json
from pathlib import Path

settings_file = Path.home() / ".claude" / "settings.json"
install_dir = Path.home() / ".local" / "share" / "claude-neko"

# 读取现有配置
if settings_file.exists():
    try:
        settings = json.loads(settings_file.read_text())
    except json.JSONDecodeError:
        settings = {}
else:
    settings = {}

# 获取现有 hooks（保留用户自己的 hooks）
existing_hooks = settings.get("hooks", {})

# 我们要添加的 hooks 配置
new_hooks = {
    "SessionStart": [
        {
            "matcher": "startup",
            "hooks": [
                {
                    "type": "command",
                    "command": f"bash {install_dir}/launch.sh"
                }
            ]
        }
    ],
    "PreToolUse": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "PostToolUse": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "PostToolUseFailure": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "Stop": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "PermissionRequest": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "UserPromptSubmit": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py",
                    "async": True
                }
            ]
        }
    ],
    "SessionEnd": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"{install_dir}/venv/bin/python {install_dir}/hook_bridge.py"
                }
            ]
        }
    ]
}

# 先移除已有的 claude-neko hooks（防止重复追加）
for event in list(existing_hooks.keys()):
    new_matchers = []
    for matcher in existing_hooks[event]:
        new_hooks_list = []
        for h in matcher.get("hooks", []):
            cmd = h.get("command", "")
            if "claude-neko" not in cmd:
                new_hooks_list.append(h)
        if new_hooks_list:
            matcher["hooks"] = new_hooks_list
            new_matchers.append(matcher)
    if new_matchers:
        existing_hooks[event] = new_matchers
    else:
        del existing_hooks[event]

# 合并新 hooks
for event, matchers in new_hooks.items():
    if event in existing_hooks:
        existing_hooks[event].extend(matchers)
    else:
        existing_hooks[event] = matchers

settings["hooks"] = existing_hooks

# 写回
settings_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
print(f"  ✅ hooks 配置已合并到 {settings_file}")
PYEOF

# ─── 5. 完成 ──────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 安装完成！"
echo ""
echo "使用方式："
echo "  打开任意 Claude Code 会话，小橘猫自动出现"
echo "  会话结束，小橘猫自动退出"
echo ""
echo "手动启动（不绑定会话）："
echo "  $INSTALL_DIR/stop.sh && bash $INSTALL_DIR/launch.sh"
echo ""
echo "卸载："
echo "  bash $INSTALL_DIR/uninstall.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
