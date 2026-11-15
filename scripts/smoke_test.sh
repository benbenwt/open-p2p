#!/usr/bin/env bash
#
# open-p2p 端到端冒烟测试
#
# 验证链路：加载真 checkpoint → 前向推理产出动作 → Unix socket 建连 → 客户端发帧收动作
#
# 用法（在 WSL 内执行本脚本）：
#   bash scripts/smoke_test.sh serve       # 前台启动推理服务（Ctrl+C 停止）
#   bash scripts/smoke_test.sh serve-bg    # 后台启动（不占终端）
#   bash scripts/smoke_test.sh status     # 查看启动进度 / socket 是否就绪
#   bash scripts/smoke_test.sh client     # 跑 30s 负载客户端
#   bash scripts/smoke_test.sh stop       # 停止后台服务
#
# 环境变量可覆盖：
#   PROJECT_DIR      项目根目录（默认 ~/cache/open-p2p）
#   CONFIG           推理用 config
#   CHECKPOINT       checkpoint 路径
#   WAIT_TIMEOUT     等待 socket 就绪的最长秒数（默认 3600）
#   CLIENT_SECONDS   客户端压测时长（默认 30）

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/cache/open-p2p}"
CONFIG="${CONFIG:-config/policy_model/150M_local_notoken.yaml}"
CHECKPOINT="${CHECKPOINT:-checkpoints/150M/checkpoint-step=00500000.ckpt}"
LOG="${LOG:-$PROJECT_DIR/inference_server.log}"
CLIENT_LOG="${CLIENT_LOG:-$PROJECT_DIR/inference_client.log}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-3600}"
CLIENT_SECONDS="${CLIENT_SECONDS:-30}"

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export PYTHONUNBUFFERED=1

cd "$PROJECT_DIR" || { echo "!! 找不到项目目录: $PROJECT_DIR"; exit 1; }

server_pid() { pgrep -f "elefant/policy_model/inference.py" | head -1; }
frame_count() { grep -c '^Action:' "$LOG" 2>/dev/null || echo 0; }

case "${1:-serve}" in

  serve)
    echo "=== 前台启动推理服务 ==="
    echo "config    : $CONFIG"
    echo "checkpoint: $CHECKPOINT"
    echo "日志      : $LOG"
    echo
    exec uv run elefant/policy_model/inference.py \
      --config "$CONFIG" \
      --checkpoint_path "$CHECKPOINT"
    ;;

  serve-bg)
    pkill -f "elefant/policy_model/inference.py" 2>/dev/null; sleep 2
    rm -f /tmp/uds.recap "$LOG"
    echo "=== 后台启动推理服务 $(date +%T) ==="
    setsid nohup uv run elefant/policy_model/inference.py \
      --config "$CONFIG" \
      --checkpoint_path "$CHECKPOINT" \
      > "$LOG" 2>&1 < /dev/null &
    echo "pid=$(server_pid)"
    echo "日志: $LOG"
    echo "用 'bash scripts/smoke_test.sh status' 观察进度"
    ;;

  status)
    PID=$(server_pid)
    if [ -z "$PID" ]; then echo "服务未运行"; exit 1; fi
    echo "服务 pid : $PID"
    echo "已跑时长 : $(ps -o etime= -p "$PID" | tr -d ' ')"
    echo "已产帧数: $(frame_count)"
    if [ -S /tmp/uds.recap ]; then
      echo "socket   : ✅ 已就绪 (/tmp/uds.recap)"
    else
      echo "socket   : ⏳ 未就绪（还在 warmup / FPS 测试）"
    fi
    echo "--- 关键日志 ---"
    grep -E 'TIMER|Warm-up|fps =|Server started|Model warmup' "$LOG" 2>/dev/null | tail -8
    ;;

  client)
    if [ ! -S /tmp/uds.recap ]; then
      echo "!! socket 未就绪，先等服务启动完成（或先跑 serve-bg）"; exit 1
    fi
    echo "=== 负载客户端 ${CLIENT_SECONDS}s ==="
    timeout "$CLIENT_SECONDS" uv run elefant/inference/script/inference_load_test.py \
      2>&1 | tee "$CLIENT_LOG" | grep -E "Received action|Total frames|Total time|Overall"
    ;;

  stop)
    PID=$(server_pid)
    if [ -n "$PID" ]; then
      kill "$PID" 2>/dev/null; sleep 2; kill -9 "$PID" 2>/dev/null
      echo "已停止 (pid=$PID)"
    else
      echo "服务未运行"
    fi
    rm -f /tmp/uds.recap
    ;;

  *)
    echo "用法: bash scripts/smoke_test.sh {serve|serve-bg|status|client|stop}"
    exit 1
    ;;
esac
