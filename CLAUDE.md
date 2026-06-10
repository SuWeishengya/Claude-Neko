# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Claude Neko 是一个 Linux 桌面宠物应用，用一只小橘猫实时显示 Claude Code 的工作状态。基于 GTK3 + Cairo 绘制，RGBA 透明背景，支持 Wayland 和 X11。

## 开发命令

```bash
# 环境搭建（venv 需要 --system-site-packages 以访问系统 GTK3）
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt

# 启动（手动模式，不绑定 Claude 会话）
./start.sh

# 停止
./stop.sh

# 一键安装（配置 hooks，自动随 Claude 启动）
./install.sh

# 管理命令
neko start     # 拉起小猫
neko stop      # 关闭小猫
neko restart   # 重启小猫
neko enable    # 开启自动启动
neko disable   # 关闭自动启动
neko status    # 查看状态
```

测试：`bash test_all.sh`（52 项测试，覆盖 API、安全、并发、边界）。无 lint 工具或构建步骤。

## 架构

### 自动模式（hook 驱动）

```
Claude Code (SessionStart)  ──▶ launch.sh ──▶ server.py + neko_widget.py
Claude Code (PreToolUse)    ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PostToolUse)   ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (Stop)          ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (SessionEnd)    ──▶ hook_bridge.py ──POST──▶ server.py (shutdown)
```

### 手动模式（轮询）

```
claude_monitor.py ──POST──▶ server.py (127.0.0.1:9100)
  (轮询 ~/.claude/sessions)        │
                                   │  HTTP 轮询
                                   ▼
                           neko_widget.py (GTK3 + Cairo)
```

**server.py** — HTTP 后端（`ThreadingTCPServer`），端口 9100+（动态分配）。关键端点：
- `GET /api/state` — 返回当前状态 JSON
- `POST /api/hook` — 接收事件：`pre_tool_use`、`post_tool_use`、`stop`、`permission_request`、`session_end`、`cc_switch_update`
- `POST /api/permission` — 审批/拒绝操作
- `POST /api/shutdown` — 优雅关闭

**hook_bridge.py** — 从 stdin 读取 Claude Code hook JSON，路由到对应 server.py。通过 `~/.local/state/claude-desktop-pet/sessions/` 注册表查找端口。

**launch.sh** — SessionStart hook 调用。清理残留、找空闲端口、启动 server + widget、写注册文件。

**neko_widget.py** — GTK3 悬浮窗。`set_decorated(False)` 去标题栏，`set_keep_above(True)` 置顶，RGBA visual 实现透明背景。每 500ms 渲染帧动画 + 轮询状态。支持拖拽、粒子效果、审批弹窗。

**claude_monitor.py** — 仅手动模式使用。每 3 秒扫描 `~/.claude/projects/` 下的 session jsonl 文件。

## 关键文件

- `config.json` — 显示配置（`show_level`、`show_counts`）
- `assets/cat/{state}/frame_{N}.png` — 精灵图，状态：sleep/idle/busy/attention/celebrate/heart
- `neko` — 命令行管理工具
- `install.sh` / `uninstall.sh` — 一键安装/卸载
- `start.sh` / `stop.sh` — 手动模式启动/停止
- `test_all.sh` — 全面测试脚本（52 项）
- `pids.txt` — 手动模式进程 PID 文件

## 安装后文件结构

```
~/.local/share/claude-desktop-pet/   # 代码（只读）
~/.local/state/claude-desktop-pet/   # 运行时数据（读写）
  └── sessions/                      # session 注册表
~/.local/bin/neko                     # 命令行工具
~/.claude/settings.json              # hooks 配置（追加，不覆盖）
```

## 状态机

mode 值及对应显示文字和图标：

| mode | 显示文字 | 图标 | 触发条件 |
|------|---------|------|---------|
| idle | Ready | sleep | stop 事件后（真正空闲） |
| idle | Thinking | idle | post_tool_use 后 running=0（思考中） |
| busy | {tool_name}: {desc} | attention | pre_tool_use |
| attention | Approve: {tool} | busy | permission_request |
| heart | Approved! | heart | approve 操作 |

等级系统基于历史总 token 消耗：Lv.1 (0) 到 Lv.10 (100亿)，升级触发 `celebrate` 状态。

## 多实例

每只小猫独立端口（9100+），独立进程，窗口自动错开 30px。通过 `~/.local/state/claude-desktop-pet/sessions/` 注册表协调。会话结束时对应小猫自动退出，不影响其他小猫。

## 技术实现

- X11 透明：`_NET_WM_WINDOW_TYPE_DOCK` 窗口类型，回退到 `_NET_WM_WINDOW_TYPE_NOTIFICATION`
- GNOME Wayland：`start.sh` 和 `launch.sh` 设置 `GDK_BACKEND=x11` 强制走 XWayland
- 精灵图加载：PIL Image → `cairo.ImageSurface.create_for_data()`，每帧缓存
- 心跳超时：server.py 120 秒无事件自动 shutdown（仅自动模式）

## 依赖

- `PyGObject` + `pycairo` — GTK3 Python 绑定（通过 `--system-site-packages` 访问系统包）
- `pillow` — 精灵图加载（PIL Image → cairo.ImageSurface）
