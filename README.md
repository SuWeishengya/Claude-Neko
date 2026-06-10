# Claude Neko

> **🐱 专为 Linux 下的 Claude Code CLI 设计的桌面宠物**

一只住在你屏幕上的小橘猫，实时显示 Claude Code 的工作状态。本程序**仅适用于 Linux 桌面环境**，通过 Claude Code 的 Hooks 机制深度绑定 CLI 会话，为终端中的 Claude 交互增添一份陪伴感。

## 功能

- 🐱 **实时状态**：空闲睡觉、忙碌工作、思考中、等待审批、升级庆祝
- 🪝 **深度绑定**：通过 Claude Code Hooks 自动随 Claude 启动/退出
- 🐾 **多实例**：多个 Claude 会话同时运行，每只会话一只独立小猫
- 📦 **一键安装**：`./install.sh` 自动配置环境和 hooks
- 🎮 **命令行管理**：`neko start/stop/status` 管理小猫
- 🖱️ **拖拽置顶**：可拖拽移动，始终置顶显示
- ✨ **RGBA 透明**：原生透明背景，支持 Wayland 和 X11

## 环境要求

| 项目 | 要求 |
|------|------|
| 系统 | **Linux 桌面环境**（不支持 macOS / Windows） |
| 终端 | [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)（命令行版本） |
| Python | 3.10+ |
| GUI | GTK3（大多数 Linux 发行版自带） |
| 显示 | X11 或 Wayland（GNOME 下自动走 XWayland） |

> ⚠️ 本程序依赖 Claude Code 的 Hooks 机制获取实时状态，**不支持** Claude Desktop（桌面 GUI 版）或其他非 CLI 环境。

## 快速安装

```bash
git clone https://github.com/SuWeishengya/Claude-Neko.git && cd Claude-Neko && bash install.sh
```

安装完成后，打开任意 Claude Code 会话，小橘猫自动出现。

## 命令行工具

```bash
neko start     # 手动拉起一只小猫
neko stop      # 关闭所有小猫
neko restart   # 重启小猫
neko enable    # 开启自动随 Claude 启动
neko disable   # 关闭自动随 Claude 启动
neko status    # 查看运行状态
```

## 状态说明

| 状态 | 显示文字 | 图标 | 触发条件 |
|------|---------|------|---------|
| 空闲 | Ready | 睡觉猫 | Claude 完成回复 |
| 思考 | Thinking | 待机猫 | 工具完成，Claude 还在思考 |
| 忙碌 | {工具名}: {描述} | 工作猫 | Claude 正在执行工具调用 |
| 审批 | Approve: {工具} | 待机猫 | 等待用户审批操作 |
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
Claude Code (SessionStart)  ──▶ launch.sh ──▶ server.py + neko_widget.py
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
~/.local/bin/neko                    # 命令行工具
~/.claude/settings.json              # hooks 配置（追加，不覆盖）
```

## 与原项目的关系

本项目是 [worddless1-dotcom/claude-desktop-buddy](https://github.com/worddless1-dotcom/claude-desktop-buddy)（Windows 桌面版）在 **Linux CLI 环境**下的移植适配版本。原项目灵感来自 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版）。

与原项目的本质区别：原项目面向 Windows + Claude Desktop GUI，而 **Claude Neko 专为 Linux 终端下的 Claude Code CLI 打造**，通过 Hooks 实现事件驱动的深度集成。

在移植过程中，针对 Linux 桌面环境做了大量适配和增强：

### 平台适配

| 维度 | 原项目（Windows） | Claude Neko（Linux） |
|------|------------------|---------------------|
| GUI | tkinter | GTK3 + Cairo |
| 透明方案 | tkinter hack | RGBA visual 原生支持 |
| Wayland | 不涉及 | XWayland 兼容 |
| 启动脚本 | .bat 文件 | .sh 脚本 |
| 安装方式 | 手动复制 | `./install.sh` 一键安装 |

### 功能增强

| 维度 | 原项目 | Claude Neko |
|------|--------|-------------|
| 监控方式 | SQLite 轮询 | Claude Code Hooks 事件驱动 |
| 会话绑定 | 无绑定 | 1:1 深度绑定 |
| 多实例 | ❌ | ✅ 独立端口+窗口偏移 |
| 自动生命周期 | ❌ | ✅ 随 Claude 启动/退出 |
| 命令行工具 | ❌ | `neko` 命令 |
| 审批操作 | 无 | 审批弹窗+approve/deny |
| 心跳超时 | ❌ | ✅ 自动清理 |
| 状态机 | idle/busy/attention | 增加 Thinking/heart/celebrate |

## 技术栈

- Python 3.10+
- GTK3 + Cairo（GUI，RGBA 透明背景）
- Pillow（精灵图加载，转为 cairo.ImageSurface）
- **Claude Code CLI Hooks**（事件驱动，核心集成方式）

## 测试

```bash
bash test_all.sh
```

覆盖 8 个阶段、52 项测试：基础 API、安全（路径遍历/畸形 JSON）、并发、等级边界、注册文件、多实例隔离、entries 截断、Shell 脚本校验。

## 许可证

MIT
