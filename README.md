# Claude Desktop Buddy

Claude Code 的桌面宠物伴侣，一只小橘猫实时显示你的 Claude 使用状态。仅支持 Linux。

灵感来自 [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)（ESP32 硬件版），本项目为纯软件版本，直接运行在电脑屏幕上。

## 功能

- 实时显示 Claude Code 的工作状态（空闲 / 工作中 / 等待审批）
- 基于历史 token 消耗的等级系统（Lv.1 ~ Lv.10）
- 精灵图动画，不同状态展示不同表情
- 审批弹窗：直接在宠物窗口上批准/拒绝 Claude 的操作
- 可拖拽，置顶显示，RGBA 透明背景（支持 Wayland + X11）

## 前置条件

- Python 3.12+
- GTK3（GNOME 桌面环境自带）
- X11 或 Wayland 桌面环境
- Claude Code（`~/.claude` 目录下的 session 数据）

## 安装

```bash
git clone https://github.com/yourname/claude-desktop-buddy.git
cd claude-desktop-buddy

# venv 需要 --system-site-packages 以访问系统 GTK3
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt
```

## 使用

```bash
# 启动
./start.sh

# 停止
./stop.sh
```

启动后小橘猫会出现在屏幕右上角，可拖拽移动。

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
  "port": 9090,
  "host": "127.0.0.1"
}
```

## 架构

```
claude_monitor.py ──POST──▶ server.py (127.0.0.1:9090)
  (轮询 ~/.claude/sessions)        │
                                   │  HTTP 轮询
                                   ▼
                           buddy_widget.py (GTK3 + Cairo)
```

三个进程通过 HTTP 通信：

1. **claude_monitor.py** — 轮询 `~/.claude/projects/` 的 session jsonl，统计 token 和活跃状态
2. **server.py** — HTTP 后端，接收监控数据，维护全局状态
3. **buddy_widget.py** — GTK3 桌面悬浮窗，Cairo 绘制精灵图 + 状态文字

## 技术栈

- Python 3.12+
- GTK3 + Cairo（GUI，RGBA 透明背景）
- Pillow（精灵图加载，转为 cairo.ImageSurface）

## 许可证

MIT
