# PHASE 1 优化计划 — Claude Neko

> 生成日期：2026-06-10
> 总计 37 个 issue，分 4 个批次修复

## 批次规划

### Batch 1: 安全紧急（V1-01 ~ V1-08, V1-11 ~ V1-13）
**目标**: 修复所有安全漏洞，防止未授权访问和数据泄露
**预计影响**: server.py, hook_bridge.py, claude_monitor.py, launch.sh, neko

| Issue | 优先级 | 文件 | 修复内容 |
|-------|--------|------|---------|
| V1-01 | HIGH | server.py | 改继承 BaseHTTPRequestHandler，未知 GET 返回 404 |
| V1-03 | HIGH | server.py | 移除 CORS 头或限制 Origin |
| V1-04 | HIGH | server.py | /api/shutdown 和 /api/permission 添加 token 验证 |
| V1-07 | HIGH | hook_bridge.py | 校验 port 范围 9100-9199 |
| V1-08 | HIGH | launch.sh, neko | python -c 通过环境变量传递路径 |
| V1-11 | MEDIUM | server.py | Content-Length 上限 1MB |
| V1-12 | MEDIUM | server.py | prompt 字段结构校验 |
| V1-13 | MEDIUM | claude_monitor.py | 硬编码 host 为 127.0.0.1 |

### Batch 2: 死锁与崩溃（V1-02, V1-05, V1-06, V1-09, V1-10, V1-14 ~ V1-17）
**目标**: 修复死锁、崩溃和资源泄漏
**预计影响**: server.py, hook_bridge.py, claude_monitor.py, launch.sh, uninstall.sh

| Issue | 优先级 | 文件 | 修复内容 |
|-------|--------|------|---------|
| V1-02 | HIGH | server.py | session_end 响应移到锁外 |
| V1-05 | HIGH | server.py | _shutdown_started 改用 threading.Event |
| V1-06 | HIGH | claude_monitor.py | config.json 读取添加 try-except |
| V1-09 | HIGH | launch.sh | 添加 trap EXIT 清理子进程 |
| V1-10 | HIGH | uninstall.sh | 添加 set -e |
| V1-14 | MEDIUM | hook_bridge.py | except 至少 log 到 stderr |
| V1-15 | MEDIUM | hook_bridge.py | urlopen 使用 with 语句 |
| V1-16 | MEDIUM | hook_bridge.py | stdin.read() 检查 JSON 完整性 |
| V1-17 | MEDIUM | server.py | ThreadingTCPServer 设置 daemon_threads |

### Batch 3: 可靠性改进（V1-18 ~ V1-25）
**目标**: 修复误杀、GUI 问题、Shell 脚本健壮性
**预计影响**: neko_widget.py, claude_monitor.py, neko, stop.sh, start.sh

| Issue | 优先级 | 文件 | 修复内容 |
|-------|--------|------|---------|
| V1-18 | MEDIUM | neko_widget.py | 粒子列表添加上限 |
| V1-19 | MEDIUM | neko_widget.py | 审批按钮添加点击检测 |
| V1-20 | MEDIUM | neko_widget.py | get_primary_monitor None 检查 |
| V1-21 | MEDIUM | claude_monitor.py | 缓存文件偏移量 |
| V1-22 | MEDIUM | neko, start.sh | 添加 ss 端口检测 |
| V1-23 | MEDIUM | stop.sh, start.sh | cd 失败时 exit 1 |
| V1-24 | MEDIUM | stop.sh, uninstall.sh, neko | 精确 pkill 模式 |
| V1-25 | MEDIUM | neko | 健康检查中检测进程存活 |

### Batch 4: 代码质量（V1-26 ~ V1-37）
**目标**: 清理代码异味、提升可维护性
**预计影响**: server.py, hook_bridge.py, neko_widget.py, install.sh, start.sh, stop.sh

| Issue | 优先级 | 文件 | 修复内容 |
|-------|--------|------|---------|
| V1-26 | LOW | server.py | 删除重复 global 声明 |
| V1-27 | LOW | server.py | LEVEL_TABLE 提升为模块级常量 |
| V1-28 | LOW | server.py | log_message 至少保留 error 级别 |
| V1-29 | LOW | server.py | 顶部 import os |
| V1-30 | LOW | hook_bridge.py | 顶部统一 import |
| V1-31 | LOW | neko_widget.py | 魔术数字提取为常量 |
| V1-32 | LOW | install.sh | 删除 EXISTING 死代码 |
| V1-33 | LOW | start.sh | stderr 重定向到日志文件 |
| V1-34 | LOW | install.sh | 安装后检测关键模块 |
| V1-35 | LOW | stop.sh, start.sh | read 添加 -r |
| V1-36 | LOW | launch.sh | session_id 校验用 printf |
| V1-37 | LOW | launch.sh | 删除未使用的 PID 变量 |

---

## 执行顺序

```
Batch 1 (安全紧急) → TEST → COMMIT → REVIEW
    ↓ 通过
Batch 2 (死锁崩溃) → TEST → COMMIT → REVIEW
    ↓ 通过
Batch 3 (可靠性) → TEST → COMMIT → REVIEW
    ↓ 通过
Batch 4 (代码质量) → TEST → COMMIT → REVIEW
```

## 测试补充计划

在 Batch 1-4 修复完成后，补充测试：
1. hook_bridge.py 单元测试（Python，非 bash）
2. launch.sh 集成测试
3. 心跳超时机制测试
4. session_end 事件测试
