# Claude Neko 架构文档

## 整体架构

```
┌─────────────────────────────────────────────────────┐
│  Claude Code                                        │
│  ┌──────────────────────────────────────────────┐  │
│  │ Hooks (settings.json)                        │  │
│  │  SessionStart → launch.sh                    │  │
│  │  UserPromptSubmit → hook_bridge.py           │  │
│  │  PreToolUse → hook_bridge.py                 │  │
│  │  PostToolUse → hook_bridge.py                │  │
│  │  Stop → hook_bridge.py                       │  │
│  │  SessionEnd → hook_bridge.py                 │  │
│  │  PermissionRequest → hook_bridge.py          │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────┘
                  │ stdin (JSON)
                  ▼
┌─────────────────────────────────────────────────────┐
│  hook_bridge.py                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ 路由: session_id → port (注册表 / fallback)  │  │
│  │ 事件映射: hook_event → POST /api/hook        │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP POST
                  ▼
┌─────────────────────────────────────────────────────┐
│  server.py (ThreadingTCPServer)                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ 状态机: 10 mode, prompt_active, pending_heart│  │
│  │ API: /api/state (GET), /api/hook (POST)      │  │
│  │ 心跳: 会话存活检查 + sleep 过渡              │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP GET (200ms)
                  ▼
┌─────────────────────────────────────────────────────┐
│  neko_widget.py (GTK3 + Cairo)                       │
│  ┌──────────────────────────────────────────────┐  │
│  │ 帧动画: 125ms, 精灵图缓存                    │  │
│  │ 粒子特效: sleep/busy/typing/heart            │  │
│  │ 弹窗: 审批框 + 右键菜单 + 左键统计 + 帮助    │  │
│  │ 交互: 拖拽 + 点击 + 右键菜单                 │  │
│  │ 颜色方案: 6 种, 多实例自动分配               │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## 状态机

```
                               user_prompt_submit
  idle ──────────────────────────────────────────► think
    ▲                                               │
    │ 1s                                            │ pre_tool_use
    │                                               ▼
  happy ◄── stop (was_working) ─────────── busy/typing/subagent
                                               │
    permission_request                         │ post_tool_use
         │                                     │ (running=0)
         ▼                                     ▼
    attention ── pre_tool_use ──► heart ──0.8s──┘
                                     │
                                     └──► busy/typing/subagent
```

10 种 mode：
| mode | 精灵图 | 触发 |
|------|--------|------|
| idle | idle | 初始/停止后 |
| think | think | user_prompt_submit / 工具间恢复 |
| busy | busy | 通用工具 |
| typing | typing | Edit/Write |
| subagent | subagent | Agent |
| attention | attention | permission_request |
| heart | heart | 审批通过 (0.8s) |
| happy | happy | 任务完成 |
| error | error | 工具失败 |
| sleep | sleep | 30s idle |

## API

### GET /api/state

返回当前状态 JSON：

```json
{
  "mode": "idle",
  "running": 0,
  "waiting": 0,
  "msg": "Ready",
  "tokens_today": 12345,
  "total": 3,
  "prompt": null,
  "prompt_active": false,
  "pending_heart": false,
  "shutdown": false
}
```

### POST /api/hook

事件驱动状态更新。事件类型：`user_prompt_submit`, `pre_tool_use`, `post_tool_use`, `post_tool_use_failure`, `stop`, `permission_request`, `session_end`, `cc_switch_update`

### POST /api/shutdown

优雅关闭 server 和 widget。

## 多实例

- 每只猫独立端口 (9100+), 独立进程
- 注册表: `~/.local/state/claude-neko/sessions/{id}.json`
- 颜色: 按 offset 顺序分配 (橘→蓝→粉→灰→黑→白)
- `claude -c` 继续同一会话 → 共享同一只猫, SessionEnd 不误杀

## 安全

- Hook 端点在 `127.0.0.1` 监听, 不对外暴露
- Content-Length 上限 1MB
- session_id 格式校验 (regex: `^[a-zA-Z0-9_-]+$`)
- `cc_switch_update` 白名单字段校验
- 审批框纯展示, 无交互按钮 (防止 CSS 注入)
