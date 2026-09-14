#!/usr/bin/env bash
# ============================================================================
# start_individual.sh
# 分步启动，便于调试。主路径已不含 Go2。
# Usage: ./start_individual.sh [server|gazebo|spawn|keyboard|all]
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STREAMVLN_DIR="/home/ylubt2204/StreamVLN"
CONDA_BASE="/home/ylubt2204/miniconda3"
STREAMVLN_ENV="$CONDA_BASE/envs/streamvln"
ROS_DISTRO="humble"

source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/install/tomato_farm_simulator/share/tomato_farm_simulator/models:${GAZEBO_MODEL_PATH:-}"
export GAZEBO_PLUGIN_PATH="/opt/ros/$ROS_DISTRO/lib:${GAZEBO_PLUGIN_PATH:-}"
export DISPLAY="${DISPLAY:-:0}"

STEP=${1:-"all"}

start_server() {
    echo "=== [1/4] Starting StreamVLN HTTP Server (可选) ==="
    if [ ! -x "$STREAMVLN_ENV/bin/python" ]; then
        echo "StreamVLN conda env 不存在，跳过"
        return
    fi
    cd "$STREAMVLN_DIR"
    kill $(lsof -t -i:5801 2>/dev/null) 2>/dev/null || true
    sleep 1
    $STREAMVLN_ENV/bin/python streamvln/http_realworld_server.py \
        --port 5801 > /tmp/streamvln_server.log 2>&1 &
    echo "Server PID: $!"
    echo "Log: /tmp/streamvln_server.log"
    echo "Waiting for server (may take 1-2 min)..."
    for i in $(seq 1 120); do
        if curl -s http://localhost:5801/health >/dev/null 2>&1; then
            echo "Server ready!"
            return
        fi
        sleep 1
    done
    echo "Server failed to start!"
    tail -30 /tmp/streamvln_server.log
    exit 1
}

start_gazebo() {
    echo "=== [2/4] Starting Gazebo tomato farm + TomatoBot ==="
    # tomato_farm_world.launch.py 已包含 spawn；默认 spawn_robot:=true
    local HEADLESS_ARG=""
    if [ "${2:-}" = "--headless" ] || [ "${1:-}" = "--headless" ]; then
        HEADLESS_ARG="headless:=True"
    fi
    ros2 launch tomato_farm_simulator tomato_farm_world.launch.py $HEADLESS_ARG
}

spawn_tomato_bot() {
    echo "=== [3/4] Spawning TomatoBot (仅在 world 以 spawn_robot:=false 启动时使用) ==="
    ros2 launch tomato_bot_description spawn_tomato_bot.launch.py \
        x:=0.5 y:=1.5 z:=0.08
}

start_keyboard_control() {
    echo "=== [4/4] Starting Keyboard Control ==="
    ros2 run tomato_bot_controller keyboard_control
}

case "$STEP" in
    server)  start_server ;;
    gazebo)  start_gazebo "$@" ;;
    spawn)   spawn_tomato_bot ;;
    keyboard)  start_keyboard_control ;;
    all)
        echo "最小可用一键流程不依赖 StreamVLN。若需要可先: $0 server"
        echo "建议直接使用: ./run_tomato_bot_test.sh"
        start_gazebo "$@"
        ;;
    *)
        echo "Usage: $0 [server|gazebo|spawn|keyboard|all]"
        echo "  gazebo   - 启动大棚世界并自动生成 TomatoBot"
        echo "  spawn    - 仅在需要单独生成机器人时使用"
        echo "  keyboard - 启动键盘控制 (/cmd_vel)"
        exit 1
        ;;
esac
