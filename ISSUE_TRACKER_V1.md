# ISSUE TRACKER V1 — Claude Neko 全面审计

> 生成日期：2026-06-10
> 审计范围：server.py, hook_bridge.py, buddy_widget.py, claude_monitor.py, 所有 Shell 脚本
> 审计维度：安全、代码质量、Shell 脚本、测试覆盖

## 统计

| 等级 | 数量 | 说明 |
|------|------|------|
| 🔴 HIGH | 10 | 安全漏洞、死锁、崩溃 |
| 🟠 MEDIUM | 15 | 可靠性、资源泄漏、误杀风险 |
| 🟡 LOW | 12 | 代码质量、可维护性 |
| **总计** | **37** | |

---

## 🔴 HIGH — 安全漏洞 / 死锁 / 崩溃

### V1-01 [安全] server.py 继承 SimpleHTTPRequestHandler 导致任意文件读取
- **文件**: server.py:14, 140
- **描述**: Handler 继承 SimpleHTTPRequestHandler，/api/state 以外的 GET 请求会暴露 server.py 所在目录的所有文件（config.json、注册文件、pids.txt 等）
- **修复**: 改为继承 BaseHTTPRequestHandler，未知 GET 路径返回 404
- **状态**: ✅ 已修复 (847e0bf)

### V1-02 [死锁] session_end 在 state_lock 内发送 HTTP 响应会死锁
- **文件**: server.py:230
- **描述**: session_end 分支在 `with state_lock:` 块内发送 HTTP 响应，然后调用 do_shutdown()，do_shutdown 内部也获取 state_lock。state_lock 不是 RLock，导致死锁
- **修复**: 将 HTTP 响应发送移到锁外面；锁内仅做状态清理
- **状态**: ✅ 已修复 (847e0bf)

### V1-03 [安全] CORS Access-Control-Allow-Origin: * 配合无认证 API
- **文件**: server.py:135
- **描述**: 任意网页可通过 CSRF 读取小猫状态、发送审批决策、触发 shutdown
- **修复**: 移除 CORS 头或限制 Origin
- **状态**: ⬜ 待修复

### V1-04 [安全] /api/shutdown 和 /api/permission 无认证
- **文件**: server.py:147, 159
- **描述**: 任何能访问 localhost 的进程都可以关停小猫或伪造审批
- **修复**: 使用一次性 token 或 session_id 验证
- **状态**: ⬜ 待修复

### V1-05 [竞态] _shutdown_started 无锁保护
- **文件**: server.py:103
- **描述**: 多线程下 do_shutdown 可能被执行两次，remove_registration 重复调用
- **修复**: 使用 threading.Lock 或 threading.Event
- **状态**: ✅ 已修复 (847e0bf)

### V1-06 [崩溃] claude_monitor.py config.json 读取无异常处理
- **文件**: claude_monitor.py:11
- **描述**: config.json 不存在或格式错误时直接崩溃
- **修复**: 添加 try-except 和 fallback 默认值
- **状态**: ✅ 已修复 (847e0bf)

### V1-07 [安全] hook_bridge.py port 值未校验范围
- **文件**: hook_bridge.py:45
- **描述**: 注册文件被篡改后可向 localhost 任意端口发送 POST（如 Redis 6379）
- **修复**: 校验 port 在 9100-9999 范围内
- **状态**: ✅ 已修复 (847e0bf)

### V1-08 [安全] launch.sh python -c 中嵌入 shell 变量存在命令注入
- **文件**: launch.sh:34, 45, 57 及 neko 多处
- **描述**: 文件名含单引号时会破坏 Python 字符串语法
- **修复**: 通过环境变量传递路径
- **状态**: ✅ 已修复 (847e0bf)

### V1-09 [BUG] launch.sh server 启动失败仍启动 widget，无 trap 清理
- **文件**: launch.sh:74, 90
- **描述**: server 不可用时 widget 仍启动；脚本退出时子进程成为孤儿
- **修复**: 健康检查失败后 exit 1；添加 trap EXIT 清理子进程
- **状态**: ✅ 已修复 (926b989)

### V1-10 [BUG] uninstall.sh 缺少 set -e
- **文件**: uninstall.sh:1
- **描述**: rm -rf 失败时静默继续，用户以为已卸载但文件残留
- **修复**: 添加 set -e
- **状态**: ✅ 已修复 (926b989)

---

## 🟠 MEDIUM — 可靠性 / 资源泄漏 / 误杀

### V1-11 [安全] Content-Length 未限制，内存耗尽风险
- **文件**: server.py:148, 160, 187
- **修复**: 添加 Content-Length 上限（1MB）
- **状态**: ✅ 已修复 (467b66c)

### V1-12 [安全] permission_request 的 prompt 字段未校验结构
- **文件**: server.py:226
- **修复**: 校验 prompt 为 dict 且包含 id、tool 字段
- **状态**: ✅ 已修复 (467b66c)

### V1-13 [安全] claude_monitor.py config.json host 字段可被篡改为远程地址
- **文件**: claude_monitor.py:21
- **修复**: 硬编码 host 为 127.0.0.1
- **状态**: ✅ 已修复 (467b66c)

### V1-14 [BUG] hook_bridge.py 裸 except 吞掉所有异常
- **文件**: hook_bridge.py:37
- **修复**: 至少 log 到 stderr
- **状态**: ✅ 已修复 (847e0bf)

### V1-15 [BUG] hook_bridge.py urlopen 返回值未关闭
- **文件**: hook_bridge.py:49
- **修复**: 使用 with 语句
- **状态**: ✅ 已修复 (467b66c)

### V1-16 [BUG] hook_bridge.py stdin.read() 可能读到不完整 JSON
- **文件**: hook_bridge.py:58
- **修复**: 检查 JSON 完整性或使用 raw_decode
- **状态**: ✅ 已修复 (467b66c)

### V1-17 [BUG] ThreadingTCPServer 未设置 daemon_threads
- **文件**: server.py:266
- **修复**: 添加 daemon_threads = True
- **状态**: ✅ 已修复 (847e0bf)

### V1-18 [BUG] buddy_widget 粒子列表无上限
- **文件**: buddy_widget.py:211
- **修复**: 添加 max 200 个粒子的上限
- **状态**: ✅ 已修复 (467b66c)

### V1-19 [BUG] buddy_widget 审批按钮无法点击
- **文件**: buddy_widget.py:188
- **描述**: 绘制了 Approve/Deny 按钮但 _on_button_press 只处理拖拽
- **修复**: 添加按钮区域点击检测
- **状态**: ✅ 已修复 (467b66c)

### V1-20 [BUG] buddy_widget get_primary_monitor() 可能返回 None
- **文件**: buddy_widget.py:106
- **修复**: 添加 None 检查和默认值
- **状态**: ✅ 已修复 (467b66c)

### V1-21 [BUG] claude_monitor 每 3 秒全量扫描所有 jsonl 文件
- **文件**: claude_monitor.py:59
- **修复**: 缓存已处理文件的偏移量
- **状态**: ⬜ 待修复

### V1-22 [BUG] neko start 和 start.sh 不检测系统级端口占用
- **文件**: neko:47, start.sh:33
- **修复**: 添加 ss -tlnp 端口检测
- **状态**: ✅ 已修复 (926b989)

### V1-23 [BUG] stop.sh 和 start.sh cd 失败未退出
- **文件**: stop.sh:3, start.sh:3
- **修复**: cd 失败时 exit 1
- **状态**: ✅ 已修复 (926b989)

### V1-24 [安全] pkill -f 模式过于宽泛可能误杀
- **文件**: stop.sh:22, uninstall.sh:27, neko:87
- **修复**: 使用更精确的匹配模式
- **状态**: ✅ 已修复 (926b989)

### V1-25 [BUG] neko start PID_SERVER 赋值后从未使用
- **文件**: neko:51
- **修复**: 健康检查中检测进程是否存活
- **状态**: ✅ 已修复 (926b989)

---

## 🟡 LOW — 代码质量 / 可维护性

### V1-26 ~ V1-37（详见上方）
- 全局变量重复声明、魔术数字、死代码、日志缺失等
- **状态**: ✅ 已修复 (a12fbc1)

---

## 测试覆盖评估

| 组件 | 覆盖率 |
|------|--------|
| server.py API | 75% |
| server.py 基础设施 | 40% |
| hook_bridge.py | 10% |
| launch.sh | 0% |
| buddy_widget.py | 0% |
| claude_monitor.py | 0% |
| neko 命令 | 5% |
| install/uninstall.sh | 0% |
| **总体** | **~25%** |
