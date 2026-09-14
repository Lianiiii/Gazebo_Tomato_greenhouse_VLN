#!/bin/bash
# 简单测试脚本，测试Gazebo和TomatoBot

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

# 源ROS2
source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 设置环境变量
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models"
export GAZEBO_PLUGIN_PATH="/usr/lib/x86_64-linux-gnu/gazebo-11/plugins:$GAZEBO_PLUGIN_PATH"
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu/gazebo-11:$LD_LIBRARY_PATH"

log_step "启动简单测试..."

# 1. 启动Gazebo后台
log_info "启动Gazebo..."
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py headless:=True &
GAZEBO_PID=$!

# 等待几秒
sleep 5

# 2. 检查Gazebo是否启动
if pgrep -f "gzserver" > /dev/null; then
    log_info "✓ Gazebo已启动"
else
    log_error "✗ Gazebo启动失败"
    exit 1
fi

# 3. 启动TomatoBot
log_info "启动TomatoBot..."
ros2 launch tomato_bot_description spawn_tomato_bot.launch.py &
SPAWN_PID=$!

# 等待几秒
sleep 3

# 4. 检查机器人是否生成
if ros2 topic list | grep -q "/tf"; then
    log_info "✓ 机器人已生成"
else
    log_warn "⚠ 生成状态未知"
fi

# 5. 启动键盘控制（可选）
log_info "启动键盘控制..."
read -p "按Enter键启动键盘控制（或Ctrl+C跳过）"
ros2 run tomato_bot_controller keyboard_control &
KEYBOARD_PID=$!

log_info "系统已启动！"
echo "使用WASD控制机器人，按Ctrl+C退出"

# 等待用户退出
trap 'kill $GAZEBO_PID $SPAWN_PID $KEYBOARD_PID 2>/dev/null; exit' INT
wait

# 清理
kill $GAZEBO_PID $SPAWN_PID $KEYBOARD_PID 2>/dev/null || true
log_info "测试完成"