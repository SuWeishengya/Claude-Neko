# Claude Neko

> **🐱 一只住在你屏幕上的小橘猫，陪你写代码**

Claude Neko 是 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的桌面宠物伴侣。它通过 Claude Code 的 Hooks 机制实时感知工作状态，在你的屏幕角落显示一只小猫动画——空闲时睡觉、忙碌时盯着你看、等你审批时举手请求、升级时开心跳跃。

<!-- TODO: 添加截图或 GIF 演示 -->
<!-- ![Claude Neko Demo](docs/demo.gif) -->

## 它能做什么

**实时状态** — 小猫会根据 Claude 的状态切换动画：

| Claude 在干嘛 | 小猫的反应 |
|--------------|-----------|
| 空闲等你输入 | 😺 待机眨眼，4 秒一次 |
| 正在思考 | 🤔 思考中，显示 "Thinking..." |
| 执行工具（读文件、跑命令…） | 👀 盯着你看，显示工具名 |
| 写代码（Edit/Write） | ⌨️ 打字中 |
| 调用子代理（Agent） | 🔷 呼叫助手 |
| 等你审批操作 | 🙋 举手，弹出 Approve/Deny 按钮 |
| 操作完成 | 🎉 开心 Done! ✨ |
| 工具报错 | ❌ 错误提示 |
| 长时间空闲 | 💤 30 秒后自动睡觉 |

**审批操作** — Claude 需要权限时，小猫身上会弹出按钮，直接点击即可批准或拒绝，不用切回终端。

**多只小猫** — 同时开多个 Claude 会话？每只会话有自己的小猫，独立端口，窗口自动错开，还有 6 种颜色方案（橘/蓝/粉/灰/黑/白）。`claude -c` 继续同一会话时共享同一只猫。

**自动生命周期** — 装好后不用管。打开 Claude Code，小猫自动出现；关闭会话，小猫自动退出。

## 安装

```bash
git clone https://github.com/SuWeishengya/Claude-Neko.git
cd Claude-Neko
bash install.sh
```

安装脚本会自动检测你的发行版（Fedora/Ubuntu/Arch），安装系统依赖，配置 Claude Code Hooks。完成后，打开任意 Claude Code 会话，小猫就会出现。

**卸载：**

```bash
bash ~/.local/share/claude-neko/uninstall.sh
```

## 日常使用

装好后基本不用管。如果需要手动控制：

```bash
neko start     # 手动拉起一只小猫
neko stop      # 关闭所有小猫
neko restart   # 重启
neko status    # 查看哪些小猫在跑
neko enable    # 开启自动随 Claude 启动（默认已开启）
neko disable   # 关闭自动启动
```

## 配置

## 环境要求

| 项目 | 要求 |
|------|------|
| 系统 | Linux 桌面环境 |
| Python | 3.8+ |
| GUI | GTK3（大多数 Linux 发行版自带） |
| 终端 | [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) |

> ⚠️ 仅支持 Linux。不支持 macOS / Windows，不支持 Claude Desktop（GUI 版）。

---

## 开发者文档

### 架构

```
Claude Code (SessionStart)  ──▶ launch.sh ──▶ server.py + neko_widget.py
Claude Code (PreToolUse)    ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PostToolUse)   ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (Stop)          ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (SessionEnd)    ──▶ hook_bridge.py ──POST──▶ server.py (session_end)
```

- **server.py** — HTTP 后端（ThreadingTCPServer），端口 9100+，维护全局状态
- **neko_widget.py** — GTK3 悬浮窗，500ms 轮询状态 + 渲染帧动画
- **hook_bridge.py** — 从 stdin 读取 Claude Code hook JSON，路由到 server.py
- **launch.sh** — SessionStart hook 入口，清理残留、分配端口、启动 server + widget
- **claude_monitor.py** — 手动模式，轮询 `~/.claude/sessions/` 获取状态

### 手动模式

```bash
./start.sh    # 启动（不绑定 Claude 会话，长期运行）
./stop.sh     # 停止
```

手动模式通过 `claude_monitor.py` 每 3 秒扫描 session 文件，适合不想配置 Hooks 的场景。

### 运行时文件

```
~/.local/share/claude-neko/   # 代码（只读）
~/.local/state/claude-neko/   # 运行时数据（读写）
  └── sessions/                      # session 注册表（JSON）
~/.local/bin/neko                    # 命令行工具
~/.claude/settings.json              # hooks 配置（安装时追加，不覆盖）
```

### 测试

```bash
bash test_all.sh    # 38 项测试，覆盖 API、安全、并发、多实例
```

### 技术栈

- Python 3.8+ / GTK3 + Cairo / Pillow / Claude Code CLI Hooks

## 致谢

灵感来自 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版），基于 [worddless1-dotcom/claude-desktop-buddy](https://github.com/worddless1-dotcom/claude-desktop-buddy)（Windows 版）移植适配。

## 许可证

MIT
