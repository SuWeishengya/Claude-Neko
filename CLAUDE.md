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
neko version   # 显示版本号
neko update    # 检查并安装更新
```

测试：`bash test_all.sh`（38 项测试，覆盖 API、安全、并发、边界）。无 lint 工具或构建步骤。

## 架构

### 自动模式（hook 驱动）

```
Claude Code (SessionStart)     ──▶ launch.sh ──▶ server.py + neko_widget.py
Claude Code (UserPromptSubmit) ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PreToolUse)       ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PostToolUse)      ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (Stop)             ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (SessionEnd)       ──▶ hook_bridge.py ──POST──▶ server.py (session_end)
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
- `POST /api/hook` — 接收事件：`user_prompt_submit`、`pre_tool_use`、`post_tool_use`、`post_tool_use_failure`、`stop`、`permission_request`、`session_end`、`cc_switch_update`
- `POST /api/permission` — 审批/拒绝操作（旧版交互按钮使用，新版审批框纯展示）
- `POST /api/shutdown` — 优雅关闭

**hook_bridge.py** — 从 stdin 读取 Claude Code hook JSON，路由到对应 server.py。通过 `~/.local/state/claude-neko/sessions/` 注册表查找端口。

**launch.sh** — SessionStart hook 调用。清理残留、找空闲端口、启动 server + widget、写注册文件。

**neko_widget.py** — GTK3 悬浮窗。`set_decorated(False)` 去标题栏，`set_keep_above(True)` 置顶，RGBA visual 实现透明背景。每 125ms 渲染帧动画 + 200ms 轮询状态。支持拖拽（motion 检测区分点击/拖拽）、粒子效果（sleep:z、busy:加载点、typing:代码符号、heart:爱心）、审批弹窗（叠加在猫胸口 82% 处）、右键菜单（Cairo 自绘透明窗口）、左键统计弹窗、多实例颜色方案（橘/蓝/粉/灰/黑/白）。窗口尺寸 140×155（PET_SIZE=110+PAD_TOP=5+PAD_BOT=40）。idle 状态下 frame_0 停留 4s 后快速眨眼，think 状态下 frame_0 停留 2s。Cairo ARGB32 需预乘 alpha（PIL 直通 alpha → numpy 预乘 → BGRA 字节序）。

**claude_monitor.py** — 仅手动模式使用。每 3 秒扫描 `~/.claude/projects/` 下的 session jsonl 文件。

## 关键文件

- `config.json` — 显示配置（`port`）
- `version.json` — 版本元数据（version + repo）
- `updater.py` — 在线更新模块（GitHub Release 检测 + 下载 + 备份 + 安装）
- `assets/cat/{state}/frame_{N}.png` — 精灵图，10 状态：sleep/idle/think/busy/typing/subagent/attention/heart/happy/error
- `assets/cat/preview_{color}.png` — 6 种颜色方案预览图（代码渲染）
- `tools/cleanup_sprites.py` — 精灵图边缘清理工具（黑线 flood fill 去噪）
- `neko` — 命令行管理工具
- `install.sh` / `uninstall.sh` — 一键安装/卸载（install.sh 用 rsync --delete 同步 assets）
- `start.sh` / `stop.sh` — 手动模式启动/停止
- `test_all.sh` — 全面测试脚本（38 项）
- `pids.txt` — 手动模式进程 PID 文件

## 安装后文件结构

```
~/.local/share/claude-neko/   # 代码 + venv
  ├── assets/cat/                    # 精灵图
  ├── venv/                          # Python 虚拟环境（更新时保留）
  ├── version.json                   # 版本元数据
  └── updater.py                     # 在线更新模块
~/.local/state/claude-neko/   # 运行时数据（读写）
  ├── sessions/                      # session 注册表（JSON）
  ├── server.log                     # 服务端日志
  └── hook_bridge.log                # Hook 桥接日志
~/.local/bin/neko                    # 命令行工具
~/.claude/settings.json              # hooks 配置（追加，不覆盖）
```

## 状态机

10 种 mode，各有独立精灵图。状态流转：

| mode | 默认文字 | 触发条件 |
|------|---------|---------|
| idle | Ready | 初始状态；stop 且无事可做 |
| sleep | zZz... | idle 状态 + stop 后 30s 无用户事件（自动触发） |
| think | Thinking... | user_prompt_submit；工具完成后 prompt_active 仍为 True 时自动恢复 |
| busy | {tool} | pre_tool_use（非 Edit/Write/Agent） |
| typing | Coding... | pre_tool_use（Edit/Write/NotebookEdit） |
| subagent | Helper... | pre_tool_use（Agent） |
| attention | Approve: {tool} | permission_request（需 prompt.id） |
| heart | Approved! | pre_tool_use 且 pending_heart=True（审批通过后 0.8s 过渡） → 然后切到 busy/typing |
| happy | Done! ★ | stop 且之前有活跃工作（think/busy/typing/subagent） |
| error | Error! | post_tool_use_failure |

**关键状态变量**：
- `prompt_active` — 用户问题是否还在处理中。`user_prompt_submit` 设为 True，`stop` 设为 False。工具间恢复 think 靠此标记。
- `pending_heart` — `permission_request` 设为 True，`pre_tool_use` 消费后设为 False。确保审批通过 heart 动画必然触发。

**过渡链**：stop（有工作）→ `happy` —1s→ `idle` —30s→ `sleep`

**cc_switch_update 规则**：数据字段（tokens_today/tokens/tokens_total/total）始终更新；mode/msg 仅在当前为 `idle` 时才接受覆盖，防止 monitor 轮询覆盖活跃状态。`running` 计数由 pre/post 事件独占管理。

## 多实例

每只小猫独立端口（9100+），独立进程，窗口自动错开 130px（PET_SIZE+20）。通过 `~/.local/state/claude-neko/sessions/` 注册表协调。支持 6 种颜色方案（橘/蓝/粉/灰/黑/白），按 offset 顺序分配。`claude -c` 继续同一会话时共享同一只猫，SessionEnd 不会误杀。

## 技术实现

- X11 透明：`_NET_WM_WINDOW_TYPE_DOCK` 窗口类型，回退到 `_NET_WM_WINDOW_TYPE_NOTIFICATION`
- GNOME Wayland：`start.sh` 和 `launch.sh` 设置 `GDK_BACKEND=x11` 强制走 XWayland
- 精灵图加载：PIL Image → `cairo.ImageSurface.create_for_data()`，每帧缓存
- 会话存活：server.py 通过检查 `~/.claude/sessions/` 下的 session 文件判断会话是否存活。启动后 10s 宽限期（等 Claude 创建 session 文件），session_end 后 60s 无事件自动关闭（僵尸防护）
- 手动模式也启用心跳线程（sleep 过渡 + session 存活检查），自动/手动行为一致
- SessionStart 有 `startup`（新会话）和 `resume`（claude -c）两种 matcher

## 依赖

- `PyGObject` + `pycairo` — GTK3 Python 绑定（通过 `--system-site-packages` 访问系统包）
- `pillow` — 精灵图加载（PIL Image → cairo.ImageSurface）
- `numpy` — Cairo 预乘 alpha 计算
- `scipy` — 精灵图边缘清理（`scipy.ndimage`）
