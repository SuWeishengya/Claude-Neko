# Claude Desktop Buddy

Claude Code 的桌面宠物伴侣，一只小橘猫实时显示你的 Claude 使用状态。

灵感来自 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版），本项目为纯软件版本，直接运行在电脑屏幕上。

## 功能

- 实时显示 Claude Code 的工作状态（空闲 / 工作中 / 等待审批）
- 基于历史 token 消耗的等级系统（Lv.1 ~ Lv.10）
- 精灵图动画，不同状态展示不同表情
- 审批弹窗：直接在宠物窗口上批准/拒绝 Claude 的操作
- 可拖拽，置顶显示，透明背景

## 前置条件

需要安装 [CC Switch](https://github.com/farion1231/cc-switch) 作为 Claude Code 的代理，本项目从 CC Switch 的数据库读取使用数据。

```
Claude Code → CC Switch（代理）→ Anthropic API
                    ↓
              SQLite 数据库 ← 本项目读取这里
```

## 安装

### 方式一：直接下载（推荐）

从 [Releases](https://github.com/yourname/claude-desktop-buddy/releases) 下载 ZIP 包，解压后双击 `start.bat` 即可，无需任何配置。

### 方式二：从源码安装

```bash
git clone https://github.com/yourname/claude-desktop-buddy.git
cd claude-desktop-buddy
setup.bat
```

或手动：

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 使用

首次运行：双击 `setup.bat`（仅需一次）。

之后每次：双击 `start.bat` 启动，双击 `stop.bat` 停止。

## 状态说明

| 状态 | 表现 | 触发条件 |
|------|------|----------|
| idle | 坐着，平静 | 无活跃请求 |
| attention | 惊讶表情 | 有请求正在处理 |
| sleep | 趴着睡觉，z-z 飘出 | 无连接 |
| celebrate | 开心笑脸 | 等级提升 |
| heart | 爱心飘出 | 批准操作 |

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

编辑 `config.json`：

```json
{
  "port": 8080,
  "host": "127.0.0.1"
}
```

## 架构

```
cc_switch_monitor.py  ──POST──▶  server.py (127.0.0.1:8080)
  (watchdog 监控 SQLite)              │
                                      │  HTTP 轮询
                                      ▼
                               buddy_widget.py (tkinter 悬浮窗)
```

三个进程通过 HTTP 通信：

1. **cc_switch_monitor.py** — 用 watchdog 监控 CC Switch 数据库文件变化，实时推送状态
2. **server.py** — HTTP 后端，接收监控数据，维护全局状态
3. **buddy_widget.py** — tkinter 桌面悬浮窗，显示精灵图 + 状态文字

## 技术栈

- Python 3.12+
- tkinter（GUI）
- Pillow（精灵图加载）
- watchdog（文件变化监控）

## 许可证

MIT
