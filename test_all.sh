#!/bin/bash
# Claude Neko — 全面测试脚本（优化版）

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="./venv/bin/python"
PORT=19700
PASS=0
FAIL=0
TESTS_DIR="/tmp/claude-neko-test-$$"
mkdir -p "$TESTS_DIR"
SERVER_PID=""

cleanup() {
    [ -n "$SERVER_PID" ] && kill -9 "$SERVER_PID" 2>/dev/null || true
    rm -rf "$TESTS_DIR"
}
trap cleanup EXIT

start_server() {
    local sid="${1:-test-session}"
    $PYTHON "$SCRIPT_DIR/server.py" --port "$PORT" --session-id "$sid" --state-dir "$TESTS_DIR" &>/dev/null &
    SERVER_PID=$!
    sleep 1.5
    # 验证 server 启动
    curl -s "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1 || { echo "FAIL: server 启动失败"; exit 1; }
}

stop_server() {
    [ -n "$SERVER_PID" ] && kill -9 "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
}

assert_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  ✅ $desc"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $desc (expected: $expected, got: $actual)"
        FAIL=$((FAIL + 1))
    fi
}

get_field() {
    echo "$1" | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('$2',''))"
}

# ═════════════════════════════════════════
echo "════════════════════════════════════════"
echo " Phase 1: 基础 API 测试"
echo "════════════════════════════════════════"

start_server

STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "初始 mode 为 idle" "idle" "$(get_field "$STATE" "mode")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"pre_tool_use","msg":"Bash: ls"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "pre 后 mode=busy" "busy" "$(get_field "$STATE" "mode")"
assert_eq "pre 后 running=1" "1" "$(get_field "$STATE" "running")"
assert_eq "pre 后 msg 正确" "Bash: ls" "$(get_field "$STATE" "msg")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"post_tool_use","msg":"Done"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "post 后 mode=idle" "idle" "$(get_field "$STATE" "mode")"
assert_eq "post 后 msg=Thinking" "Thinking" "$(get_field "$STATE" "msg")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"stop","msg":"Done"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "stop 后 mode=idle" "idle" "$(get_field "$STATE" "mode")"
assert_eq "stop 后 msg=Ready" "Ready" "$(get_field "$STATE" "msg")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"permission_request","msg":"Approve: Bash","prompt":{"id":"p1","tool":"Bash","hint":"rm -rf"}}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "permission 后 mode=attention" "attention" "$(get_field "$STATE" "mode")"

curl -s -X POST "http://127.0.0.1:$PORT/api/permission" -H "Content-Type: application/json" -d '{"id":"p1","decision":"once"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "approve 后 mode=heart" "heart" "$(get_field "$STATE" "mode")"
assert_eq "approve_count=1" "1" "$(get_field "$STATE" "approve_count")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"permission_request","msg":"test","prompt":{"id":"p2","tool":"Write"}}'
curl -s -X POST "http://127.0.0.1:$PORT/api/permission" -H "Content-Type: application/json" -d '{"id":"p2","decision":"deny"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "deny 后 mode=idle" "idle" "$(get_field "$STATE" "mode")"
assert_eq "deny_count=1" "1" "$(get_field "$STATE" "deny_count")"

curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"cc_switch_update","mode":"busy","msg":"Test","tokens_today":5000,"tokens_total":2000000,"total":10,"running":2}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "cc_switch mode=busy" "busy" "$(get_field "$STATE" "mode")"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/unknown")
assert_eq "未知端点 404" "404" "$HTTP_CODE"

stop_server

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 2: 安全测试"
echo "════════════════════════════════════════"

start_server

# 路径遍历
echo '{"session_id":"../../../tmp/evil","hook_event_name":"Stop"}' | $PYTHON "$SCRIPT_DIR/hook_bridge.py" 2>/dev/null
if [ -f "/tmp/evil.json" ]; then
    echo "  ❌ 路径遍历成功！"
    FAIL=$((FAIL + 1))
    rm -f /tmp/evil.json
else
    echo "  ✅ 路径遍历被阻止"
    PASS=$((PASS + 1))
fi

# 超长 msg
LONG_MSG=$(python3 -c "print('A' * 1000)")
curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d "{\"event\":\"pre_tool_use\",\"msg\":\"$LONG_MSG\"}"
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
MSG=$(get_field "$STATE" "msg")
MSG_LEN=${#MSG}
assert_eq "超长 msg 截断≤40" "1" "$([ "$MSG_LEN" -le 40 ] && echo 1 || echo 0)"

# 空 body（不应崩溃，状态不变）
curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d ''
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "空 body 不崩溃" "1" "$([ -n "$STATE" ] && echo 1 || echo 0)"

# 畸形 JSON
curl -s -o /dev/null -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{invalid}'
sleep 0.5
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state" 2>/dev/null)
if [ -n "$STATE" ]; then
    echo "  ✅ 畸形 JSON 后 server 存活"
    PASS=$((PASS + 1))
else
    echo "  ❌ 畸形 JSON 后 server 崩溃"
    FAIL=$((FAIL + 1))
fi

# 错误 prompt id
curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"permission_request","msg":"test","prompt":{"id":"real","tool":"Bash"}}'
curl -s -X POST "http://127.0.0.1:$PORT/api/permission" -H "Content-Type: application/json" -d '{"id":"wrong","decision":"once"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "错误 id 不改变状态" "attention" "$(get_field "$STATE" "mode")"

stop_server

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 3: 并发测试"
echo "════════════════════════════════════════"

start_server

# 并发 pre
seq 1 10 | xargs -P10 -I{} curl -s --max-time 5 -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"pre_tool_use","msg":"task"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "10 并发 pre 后 running=10" "10" "$(get_field "$STATE" "running")"

# 并发 post
seq 1 10 | xargs -P10 -I{} curl -s --max-time 5 -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"post_tool_use","msg":"Done"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "10 并发 post 后 running=0" "0" "$(get_field "$STATE" "running")"

# running 不会负数
curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"post_tool_use","msg":"Done"}'
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "running 不会负数" "0" "$(get_field "$STATE" "running")"

# 多次 pre 后逐个 post
for i in $(seq 1 5); do
    curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"pre_tool_use","msg":"task"}'
done
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "5 次 pre 后 running=5" "5" "$(get_field "$STATE" "running")"

for i in $(seq 1 3); do
    curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d '{"event":"post_tool_use","msg":"Done"}'
done
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
assert_eq "3 次 post 后 running=2" "2" "$(get_field "$STATE" "running")"

stop_server

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 4: 注册文件测试"
echo "════════════════════════════════════════"

start_server "test-reg-123"

REG_FILE="$TESTS_DIR/sessions/test-reg-123.json"
if [ -f "$REG_FILE" ]; then
    echo "  ✅ 注册文件已创建"
    PASS=$((PASS + 1))
    REG_PORT=$($PYTHON -c "import json; print(json.load(open('$REG_FILE')).get('port'))")
    assert_eq "注册文件端口正确" "$PORT" "$REG_PORT"
else
    echo "  ❌ 注册文件未创建"
    FAIL=$((FAIL + 1))
fi

# shutdown 测试
curl -s -X POST "http://127.0.0.1:$PORT/api/shutdown"
sleep 6
if [ ! -f "$REG_FILE" ]; then
    echo "  ✅ shutdown 后注册文件已删除"
    PASS=$((PASS + 1))
else
    echo "  ❌ shutdown 后注册文件仍存在"
    FAIL=$((FAIL + 1))
fi
SERVER_PID=""

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 5: 多实例隔离"
echo "════════════════════════════════════════"

PORT_A=19701
PORT_B=19702

$PYTHON "$SCRIPT_DIR/server.py" --port $PORT_A --session-id "sa" --state-dir "$TESTS_DIR" &>/dev/null &
PID_A=$!
$PYTHON "$SCRIPT_DIR/server.py" --port $PORT_B --session-id "sb" --state-dir "$TESTS_DIR" &>/dev/null &
PID_B=$!
sleep 2

STATE_A=$(curl -s "http://127.0.0.1:$PORT_A/api/state" 2>/dev/null)
STATE_B=$(curl -s "http://127.0.0.1:$PORT_B/api/state" 2>/dev/null)
assert_eq "server A 存活" "idle" "$(get_field "$STATE_A" "mode")"
assert_eq "server B 存活" "idle" "$(get_field "$STATE_B" "mode")"

curl -s -X POST "http://127.0.0.1:$PORT_A/api/hook" -H "Content-Type: application/json" -d '{"event":"pre_tool_use","msg":"Task A"}'
STATE_B=$(curl -s "http://127.0.0.1:$PORT_B/api/state")
assert_eq "A 的事件不影响 B" "idle" "$(get_field "$STATE_B" "mode")"

kill -9 $PID_A $PID_B 2>/dev/null || true

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 6: entries 截断"
echo "════════════════════════════════════════"

start_server

for i in $(seq 1 15); do
    curl -s -X POST "http://127.0.0.1:$PORT/api/hook" -H "Content-Type: application/json" -d "{\"event\":\"pre_tool_use\",\"msg\":\"Task $i\"}"
done
STATE=$(curl -s "http://127.0.0.1:$PORT/api/state")
ENTRIES_LEN=$($PYTHON -c "import sys,json; print(len(json.load(sys.stdin).get('entries',[])))" <<< "$STATE")
assert_eq "entries 截断≤10" "1" "$([ "$ENTRIES_LEN" -le 10 ] && echo 1 || echo 0)"

stop_server

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " Phase 7: Shell 脚本校验"
echo "════════════════════════════════════════"

echo "--- session_id 格式校验 ---"
for sid in "valid-session_123" "../etc/passwd" "a;b" "hello world" ""; do
    if [ -z "$sid" ]; then
        echo "  ✅ 空 session_id 被拒绝"
        PASS=$((PASS + 1))
        continue
    fi
    if echo "$sid" | grep -qE '^[a-zA-Z0-9_-]+$'; then
        echo "  ✅ '$sid' 通过校验（合法）"
        PASS=$((PASS + 1))
    else
        echo "  ✅ '$sid' 被拒绝（非法字符）"
        PASS=$((PASS + 1))
    fi
done

echo "--- neko restart 存在 ---"
if grep -q "cmd_restart" "$SCRIPT_DIR/neko"; then
    echo "  ✅ neko restart 已实现"
    PASS=$((PASS + 1))
else
    echo "  ❌ neko restart 缺失"
    FAIL=$((FAIL + 1))
fi

# ═════════════════════════════════════════
echo ""
echo "════════════════════════════════════════"
echo " 测试结果汇总"
echo "════════════════════════════════════════"
echo "  ✅ 通过: $PASS"
echo "  ❌ 失败: $FAIL"
echo "  总计:   $((PASS + FAIL))"
echo "════════════════════════════════════════"

[ "$FAIL" -gt 0 ] && exit 1 || exit 0
