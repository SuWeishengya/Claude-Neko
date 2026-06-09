# Claude Neko

一只住在你屏幕上的小橘猫，实时显示 Claude Code 的工作状态。

## 功能

- 🐱 **实时状态**：空闲睡觉、忙碌工作、思考中、等待审批、升级庆祝
- 🪝 **深度绑定**：通过 Claude Code Hooks 自动随 Claude 启动/退出
- 🐾 **多实例**：多个 Claude 会话同时运行，每只会话一只独立小猫
- 📦 **一键安装**：`./install.sh` 自动配置环境和 hooks
- 🎮 **命令行管理**：`pet start/stop/status` 管理小猫
- 🖱️ **拖拽置顶**：可拖拽移动，始终置顶显示
- ✨ **RGBA 透明**：原生透明背景，支持 Wayland 和 X11

## 快速安装

```bash
git clone https://github.com/SuWeishengya/Claude-Neko.git
cd Claude-Neko
chmod +x install.sh
./install.sh
```

安装完成后，打开任意 Claude Code 会话，小橘猫自动出现。

## 命令行工具

```bash
pet start     # 手动拉起一只小猫
pet stop      # 关闭所有小猫
pet enable    # 开启自动随 Claude 启动
pet disable   # 关闭自动随 Claude 启动
pet status    # 查看运行状态
```

## 状态说明

| 状态 | 显示文字 | 图标 | 触发条件 |
|------|---------|------|---------|
| 空闲 | Ready | 睡觉猫 | Claude 完成回复 |
| 思考 | Thinking | 待机猫 | 工具完成，Claude 还在思考 |
| 忙碌 | {工具名}: {描述} | 工作猫 | Claude 正在执行工具调用 |
| 审批 | Approve: {工具} | 工作猫 | 等待用户审批操作 |
| 升级 | Level Up! | 跳跃猫 | 等级提升 |
| 批准 | Approved! | 爱心猫 | 批准操作 |

## 等级系统

基于历史总 token 消耗量：

| 等级 | 所需 tokens |
|------|------------|
| Lv.1 | 0 |
| Lv.2 | 100 万 |
| Lv.3 | 500 万 |
| Lv.4 | 1000 万 |
| Lv.5 | 5000 万 |
| Lv.6 | 1 亿 |
| Lv.7 | 5 亿 |
| Lv.8 | 10 亿 |
| Lv.9 | 50 亿 |
| Lv.10 | 100 亿 |

## 配置

编辑 `config.json`（安装后位于 `~/.local/share/claude-neko/config.json`）：

```json
{
  "show_level": false,
  "show_counts": false
}
```

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `show_level` | false | 显示等级和 token 数 |
| `show_counts` | false | 显示审批/拒绝计数 |

## 架构

### 自动模式（推荐）

```
Claude Code (SessionStart)  ──▶ launch.sh ──▶ server.py + buddy_widget.py
Claude Code (PreToolUse)    ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PostToolUse)   ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (Stop)          ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (SessionEnd)    ──▶ hook_bridge.py ──POST──▶ server.py (shutdown)
```

通过 Claude Code 的 hook 机制，事件实时推送，无需轮询。

### 手动模式

```bash
./start.sh    # 启动（不自动退出）
./stop.sh     # 停止
```

手动模式通过 `claude_monitor.py` 轮询 `~/.claude/sessions/` 获取状态。

### 多实例

每只小猫独立端口（9100+），独立进程，窗口自动错开 30px。会话结束时对应的小猫自动退出，不影响其他小猫。

## 安装后文件结构

```
~/.local/share/claude-neko/          # 代码（只读）
~/.local/state/claude-neko/          # 运行时数据（读写）
  └── sessions/                      # session 注册表
~/.local/bin/pet                     # 命令行工具
~/.claude/settings.json              # hooks 配置（追加，不覆盖）
```

## 与原项目的关系

本项目基于 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版）和 [worddless1-dotcom/claude-desktop-buddy](https://github.com/worddless1-dotcom/claude-desktop-buddy)（Windows 桌面版）迁移演化而来，已发展为完全独立的项目。

### 主要变化

| 维度 | 原项目 | Claude Neko |
|------|--------|-------------|
| 平台 | Windows | Linux |
| GUI | tkinter | GTK3 + Cairo |
| 透明方案 | tkinter hack | RGBA visual 原生 |
| 监控方式 | SQLite 轮询 | Claude Code Hooks 事件驱动 |
| 绑定方式 | 无绑定 | 1:1 会话绑定 |
| 多实例 | ❌ | ✅ 独立端口+窗口偏移 |
| 自动启动 | ❌ | ✅ SessionStart hook |
| 自动退出 | ❌ | ✅ SessionEnd hook |
| 安装方式 | 手动 | `./install.sh` 一键 |
| 命令行工具 | ❌ | `pet` 命令 |
| 状态机 | idle/busy/attention | idle(+Thinking)/busy/attention/heart/celebrate |
| 审批 | 无 | 审批弹窗+approve/deny |
| 心跳超时 | ❌ | ✅ 120 秒自动退出 |
| Wayland | ❌ | ✅ XWayland 兼容 |

### 文件变化

| 文件 | 原项目 | Claude Neko |
|------|--------|-------------|
| `buddy_widget.py` | tkinter GUI | GTK3 + Cairo 重写 |
| `server.py` | SQLite 轮询 | HTTP 事件驱动重写 |
| `cc_switch_monitor.py` | ✅ | ❌ 删除 |
| `hook_bridge.py` | ❌ | ✅ 新增 |
| `launch.sh` | ❌ | ✅ 新增 |
| `install.sh` / `uninstall.sh` | ❌ | ✅ 新增 |
| `pet` | ❌ | ✅ 新增 |
| `start.bat` / `stop.bat` | ✅ Windows | ❌ 删除 |
| `start.sh` / `stop.sh` | ❌ | ✅ 新增 |

## 技术栈

- Python 3.12+
- GTK3 + Cairo（GUI，RGBA 透明背景）
- Pillow（精灵图加载，转为 cairo.ImageSurface）
- Claude Code Hooks（事件驱动）

## 许可证

MIT
