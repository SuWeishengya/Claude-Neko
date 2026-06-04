# Claude Desktop Buddy — 项目日志

## 起因

调研 Anthropic 官方仓库时发现了 `anthropics/claude-desktop-buddy`，一个跑在 ESP32（M5StickC Plus）上的实体硬件桌面宠物，通过蓝牙连接 Claude Desktop，实时显示工作状态。我们决定做一个**桌面软件版**，不需要硬件，直接在电脑屏幕上显示。

## 数据来源选择

最初方案是用 CC Switch 的 SQLite 数据库，因为用户电脑上同时运行着 CC Switch（`farion1231/cc-switch`），它记录了所有 token 消耗。

通过阅读 CC Switch 源码（Rust + Tauri），找到了：
- **数据库路径**：`~/.cc-switch/cc-switch.db`
- **核心表**：`proxy_request_logs`
- **关键字段**：`input_tokens`、`output_tokens`、`cache_read_tokens`、`cache_creation_tokens`、`total_cost_usd`、`model`、`created_at`
- SQLite 是嵌入式的，CC Switch 自带，不需要用户额外安装数据库

我们没有接 Claude Desktop 的 BLE 协议（需要硬件外设），也没有接 Claude Code CLI（没有官方事件接口），而是直接轮询 CC Switch 的数据库。项目定位为 **CC Switch 的桌面伴侣扩展**。

## 架构设计

```
CC Switch DB (SQLite, ~/.cc-switch/cc-switch.db)
    │
    │  watchdog 文件监控（实时触发）
    ▼
cc_switch_monitor.py  ──POST──▶  server.py (127.0.0.1:8080)
                                     │
                                     │  每 500ms HTTP 轮询
                                     ▼
                                buddy_widget.py (tkinter 悬浮窗)
```

三个独立进程，通过 HTTP JSON 通信：

1. **cc_switch_monitor.py** — 用 watchdog 监控 CC Switch 数据库文件变化，200ms 防抖后立即推送状态
2. **server.py** — HTTP 服务器，接收 monitor 推送，维护全局状态，供 widget 查询
3. **buddy_widget.py** — tkinter 桌面悬浮窗，右上角透明背景，显示像素精灵图 + 状态文字

## 等级体系

基于**历史总 token 消耗量**（不是今日消耗），让等级有积累感：

| 等级 | 所需 tokens | 备注 |
|------|------------|------|
| Lv.1 | 0 | 初始 |
| Lv.2 | 100 万 | |
| Lv.3 | 500 万 | |
| Lv.4 | 1000 万 | |
| Lv.5 | 5000 万 | |
| Lv.6 | 1 亿 | |
| Lv.7 | 5 亿 | ← 我们当前在这（约 5 亿） |
| Lv.8 | 10 亿 | |
| Lv.9 | 50 亿 | |
| Lv.10 | 100 亿 | |

等级提升时猫咪进入 celebrate 状态，跳跃 + 撒星号。

## 猫咪状态机

由 server.py 根据 monitor 推送的数据自动推断：

| 状态 | 触发条件 | 视觉表现 |
|------|----------|----------|
| sleep | 无活跃会话（total == 0） | 趴着睡觉，z-z 飘出 |
| idle | 连接但当前无任务 | 坐着，平静 |
| attention | 有请求正在处理（30秒内有记录） | 惊讶表情，大眼睛 |
| celebrate | 等级提升 | 开心笑脸 + 爱心 |
| heart | 批准成功 | 爱心飘出 |

## 踩过的坑

### pythonw.exe 与 asyncio
`pythonw.exe`（无窗口 Python）在我们的 server.py 中会导致 asyncio event loop 创建失败，HTTP 服务起不来。最终方案：用 `python.exe` + `subprocess.CREATE_NO_WINDOW`，既没有窗口又兼容 asyncio。

### asyncio.get_event_loop() 在 HTTP 线程
server.py 的 HTTP Handler 跑在独立线程里，`asyncio.get_event_loop()` 找不到 event loop。修复：在 `main()` 里用 `asyncio.get_running_loop()` 保存到全局变量 `_main_loop`，HTTP 线程用 `asyncio.run_coroutine_threadsafe()` 提交协程。

### Windows GBK 编码
`print()` 输出 emoji 在 Windows 默认 GBK 编码下报错。修复：在 server.py 开头强制设置 `sys.stdout.reconfigure(encoding="utf-8")`。

### bat 文件中文注释
`start.bat` 里的中文注释通过 bash 执行会乱码。修复：bat 文件中去除中文，或用 `cmd //C start.bat` 在 Windows 终端执行。

### token 计算遗漏
最初只算 `input_tokens + output_tokens`，漏掉了 `cache_read_tokens`（8000 多万）。CC Switch 里 cache tokens 占大头，必须加上 `cache_read_tokens + cache_creation_tokens`。

### tkinter 透明背景
tkinter 的 `overrideredirect` 窗口默认不透明。用 `root.attributes("-transparentcolor", "#0d1117")` 把深色背景变透明，只留猫咪和文字。

### 窗口尺寸
最初 H=290，猫咪在中间，文字在底部，间距太大。调整到 H=220，文字紧贴猫下方。

## 启动方式

```bash
# 启动
cd C:\Users\wxj\Desktop\claude-desktop-buddy
venv\Scripts\python start.py

# 停止
venv\Scripts\python stop.py
```

或双击 `start.bat` / `stop.bat`。

启动时用 `subprocess.CREATE_NO_WINDOW` 创建三个后台进程，不会在任务栏显示。`pids.txt` 记录进程 ID，供停止时使用。

## 文件清单

```
start.bat              ← 用户双击启动
stop.bat               ← 用户双击停止
start.py               ← 启动逻辑（创建 3 个无窗口进程）
stop.py                ← 停止逻辑（读 pids.txt + wmic 兜底）
server.py              ← HTTP 后端，端口 8080
cc_switch_monitor.py   ← watchdog 监控 CC Switch SQLite 数据库
buddy_widget.py        ← tkinter 桌面悬浮窗（精灵图版）
config.json            ← 端口配置
requirements.txt       ← Python 依赖（pillow, watchdog）
README.md              ← 发布说明文档
assets/cat/            ← 精灵图（每状态一个 PNG）
```

## 未完成 / 可扩展

- **多宠物切换**：目前只有一只猫，可以加更多角色
- **拖拽位置记忆**：窗口位置重启后重置，可以保存到 config.json
- **今日消耗 + 成本显示**：数据已经有了（tokens_today、cost_today），可以加到 UI
- **CLI hooks**：`cli_hook.py` 已删除，如果要接 Claude Code 可以重写

## 清理记录（2026-06-04）

移除了所有 BLE 蓝牙协议相关代码、模拟数据循环、WebSocket 子系统（无人连接），以及各文件中的无用 import。项目定位明确为 CC Switch 数据库驱动，不再保留 BLE 兼容层。

## 精灵图升级（2026-06-04）

用 AI 生成像素风格猫咪精灵图，替代原来 tkinter canvas 画的几何简笔画。6 个状态各有一帧 PNG，加载到 tkinter 显示。busy 状态改为 attention 作为主要活跃状态。

## watchdog 实时监控（2026-06-04）

cc_switch_monitor.py 从 1 秒轮询改为 watchdog 文件监控，检测延迟从 ~1 秒降到 ~200ms。保留 5 秒兜底轮询。
