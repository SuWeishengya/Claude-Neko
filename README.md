# Claude Neko

<p align="center">
  <img src="assets/cat/idle/frame_0.png" width="120" alt="Claude Neko">
</p>

<p align="center">
  <strong>一只住在你屏幕上的小橘猫，陪你写代码</strong>
</p>

<p align="center">
  <img src="assets/cat/idle/frame_0.png" width="48" alt="idle">
  <img src="assets/cat/think/frame_0.png" width="48" alt="think">
  <img src="assets/cat/typing/frame_0.png" width="48" alt="typing">
  <img src="assets/cat/busy/frame_0.png" width="48" alt="busy">
  <img src="assets/cat/happy/frame_0.png" width="48" alt="happy">
  <img src="assets/cat/sleep/frame_0.png" width="48" alt="sleep">
  <img src="assets/cat/heart/frame_0.png" width="48" alt="heart">
  <img src="assets/cat/error/frame_0.png" width="48" alt="error">
</p>

---

Claude Neko 是 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的桌面宠物伴侣。一只小橘猫实时显示 Claude 的工作状态——空闲时眨眼、思考时沉思、写代码时打字、完成后开心跳跃。

基于 GTK3 + Cairo 绘制，RGBA 透明背景，支持 Wayland 和 X11。

## 功能特性

### 10 种状态动画

| 状态 | 精灵图 | 触发条件 | 显示文字 |
|:----:|:------:|---------|---------|
| **idle** | <img src="assets/cat/idle/frame_0.png" width="32"> | 空闲等待输入 | Ready |
| **think** | <img src="assets/cat/think/frame_0.png" width="32"> | 用户提交问题 | Thinking... |
| **busy** | <img src="assets/cat/busy/frame_0.png" width="32"> | 执行工具（Bash/Read…） | 工具名 |
| **typing** | <img src="assets/cat/typing/frame_0.png" width="32"> | 写代码（Edit/Write） | Coding... |
| **subagent** | <img src="assets/cat/subagent/frame_0.png" width="32"> | 调用子代理 | Helper... |
| **attention** | <img src="assets/cat/attention/frame_0.png" width="32"> | 等待审批 | 等待审批: 工具名 |
| **heart** | <img src="assets/cat/heart/frame_0.png" width="32"> | 审批通过 | Approved! |
| **happy** | <img src="assets/cat/happy/frame_0.png" width="32"> | 任务完成 | Done! ★ |
| **error** | <img src="assets/cat/error/frame_0.png" width="32"> | 工具报错 | Error! |
| **sleep** | <img src="assets/cat/sleep/frame_0.png" width="32"> | 30 秒无活动 | zZz... |

### 粒子特效

每种状态都有独特的粒子效果：sleep 飘出 "z"、busy 旋转加载点、typing 弹出代码符号、heart 飘爱心。

### 6 种颜色方案

<p align="center">
  <img src="assets/cat/preview_orange.png" width="80" alt="橘猫">
  <img src="assets/cat/preview_blue.png" width="80" alt="蓝猫">
  <img src="assets/cat/preview_pink.png" width="80" alt="粉猫">
  <img src="assets/cat/preview_gray.png" width="80" alt="灰猫">
  <img src="assets/cat/preview_black.png" width="80" alt="黑猫">
  <img src="assets/cat/preview_white.png" width="80" alt="白猫">
</p>

多实例自动分配不同颜色：橘 → 蓝 → 粉 → 灰 → 黑 → 白。右键菜单可实时切换。

### 右键菜单

右键点击小猫弹出操作菜单：

- **检查更新** — 从 GitHub Release 检测新版本
- **帮助** — 显示 neko 指令表
- **颜色切换** — 实时切换猫咪颜色（不关闭菜单）
- **反馈问题** — 打开 GitHub Issues
- **停止** — 关闭小猫

### 在线更新

```bash
neko update     # 检查并安装更新
neko version    # 查看当前版本号
```

更新时自动备份，失败可回滚。

## 安装

**方式一：Git Clone**

```bash
git clone https://github.com/SuWeishengya/Claude-Neko.git
cd Claude-Neko
bash install.sh
```

**方式二：下载压缩包**

从 [Releases](https://github.com/SuWeishengya/Claude-Neko/releases) 下载 `claude-neko-v0.1.0.tar.gz`：

```bash
tar xzf claude-neko-v0.1.0.tar.gz
cd claude-neko-v0.1.0
bash install.sh
```

安装脚本自动检测发行版（Fedora / Ubuntu / Arch），安装系统依赖，配置 Claude Code Hooks。完成后打开任意 Claude Code 会话，小猫自动出现。

**卸载：**

```bash
bash ~/.local/share/claude-neko/uninstall.sh
```

## 日常使用

装好后基本不用管。手动控制：

```bash
neko start      # 拉起小猫（监听所有 Claude 会话）
neko stop       # 关闭所有小猫
neko restart    # 重启
neko status     # 查看运行状态
neko enable     # 开启自动随 Claude 启动
neko disable    # 关闭自动启动
neko version    # 显示版本号
neko update     # 检查并安装更新
```

### 自动模式 vs 手动模式

| | 自动模式 | 手动模式 |
|--|---------|---------|
| 启动方式 | Claude Code 自动触发 | `neko start` |
| 会话绑定 | 每只猫绑定一个会话 | 一只猫监听所有会话 |
| 生命周期 | 会话结束猫退出 | 手动 `neko stop` |
| 多实例 | 每个会话一只猫 | 单实例 |

## 操作方式

| 操作 | 效果 |
|------|------|
| 左键拖拽 | 移动小猫位置 |
| 左键单击 | 显示统计信息（Token、会话数等） |
| 右键 | 打开操作菜单 |

## 环境要求

| 项目 | 要求 |
|------|------|
| 系统 | Linux 桌面环境 |
| Python | 3.8+ |
| GUI | GTK3（大多数 Linux 发行版自带） |
| 终端 | [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) |

> ⚠️ 仅支持 Linux。不支持 macOS / Windows，不支持 Claude Desktop（GUI 版）。

## 技术架构

```
Claude Code (SessionStart)  ──▶ launch.sh ──▶ server.py + neko_widget.py
Claude Code (PreToolUse)    ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (PostToolUse)   ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (Stop)          ──▶ hook_bridge.py ──POST──▶ server.py
Claude Code (SessionEnd)    ──▶ hook_bridge.py ──POST──▶ server.py
```

- **server.py** — HTTP 后端，端口 9100+，维护全局状态机
- **neko_widget.py** — GTK3 悬浮窗，125ms 帧动画 + 500ms 状态轮询
- **hook_bridge.py** — Claude Code Hook 事件桥接
- **updater.py** — 在线更新模块（GitHub Release 检测 + 下载 + 安装）

## 许可证

MIT

## 致谢

灵感来自 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版），基于 [worddless1-dotcom/claude-desktop-buddy](https://github.com/worddless1-dotcom/claude-desktop-buddy)（Windows 版）移植适配。
