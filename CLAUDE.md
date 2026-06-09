# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Claude Desktop Buddy 是一个 Linux 桌面宠物应用，用一只小橘猫实时显示 Claude Code 的工作状态。基于 GTK3 + Cairo 绘制，RGBA 透明背景，支持 Wayland 和 X11。

## 开发命令

```bash
# 环境搭建（venv 需要 --system-site-packages 以访问系统 GTK3）
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt

# 启动
./start.sh

# 停止
./stop.sh
```

没有测试套件、lint 工具或构建步骤。代码通过直接运行验证。

## 架构

三个独立进程通过 HTTP 通信，由 `start.sh` 统一启动：

```
claude_monitor.py ──POST /api/hook──▶ server.py (127.0.0.1:9090)
  (轮询 ~/.claude/projects)              │
                                         │ GET /api/state（500ms 轮询）
                                         ▼
                                 buddy_widget.py (GTK3 + Cairo 悬浮窗)
```

**server.py** — HTTP 后端（`http.server`），端口 9090（config.json 配置）。维护全局 `state` 字典。关键端点：
- `GET /api/state` — 返回当前状态 JSON
- `POST /api/hook` — 接收监控数据，事件类型：`pre_tool_use`、`post_tool_use`、`stop`、`cc_switch_update`
- `POST /api/permission` — 审批/拒绝 Claude 操作

**claude_monitor.py** — 每 3 秒扫描 `~/.claude/projects/` 下的 session jsonl 文件，统计 token 使用量和活跃会话，推送给 server。

**buddy_widget.py** — GTK3 悬浮窗。`set_decorated(False)` 去标题栏，`set_keep_above(True)` 置顶，RGBA visual 实现透明背景。每 500ms 渲染帧动画 + 轮询状态。支持拖拽、粒子效果、审批弹窗。

## 关键文件

- `config.json` — 端口和主机配置（默认 `127.0.0.1:9090`）
- `assets/cat/{state}/frame_{N}.png` — 精灵图，状态：sleep/idle/busy/attention/celebrate/heart
- `start.sh` / `stop.sh` — 启动/停止脚本
- `pids.txt` — 运行时生成的进程 PID 文件

## 状态机

mode 值：`sleep` → `idle` → `busy`/`attention` → `celebrate`/`heart`/`angry`

## 技术实现

- X11 透明：`_NET_WM_WINDOW_TYPE_DOCK` 窗口类型（100x100 像素，屏幕左下角），回退到 `_NET_WM_WINDOW_TYPE_NOTIFICATION`（48x48，右上角）
- 精灵图加载：PIL Image → `cairo.ImageSurface.create_for_data()`，每帧缓存避免重复转换
- PyGObject 类型注解：buddy_widget.py 顶部有 `# type: ignore[attr-defined]` 等抑制 Pyright 警告的注释，因为 PyGObject stubs 不完整（`Gtk.init()` 需要参数但实际可以无参调用）

等级系统基于历史总 token 消耗：Lv.1 (0) 到 Lv.10 (100亿)，升级触发 `celebrate` 状态。

## 依赖

- `PyGObject` + `pycairo` — GTK3 Python 绑定（通过 `--system-site-packages` 访问系统包）
- `pillow` — 精灵图加载（PIL Image → cairo.ImageSurface）
- `tkinter` — 不再使用，已迁移到 GTK3
- `x11_transparency.py` — 不再使用，透明由 GTK3 RGBA visual 原生实现
