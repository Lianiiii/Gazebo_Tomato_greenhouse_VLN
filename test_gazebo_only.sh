#!/bin/bash
# 只测试Gazebo启动

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

log_step "测试Gazebo启动..."

# 只启动Gazebo，不启动机器人
log_info "启动Gazebo仿真环境..."
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py headless:=True &
GAZEBO_PID=$!

# 等待几秒
sleep 5

# 检查Gazebo是否启动
if pgrep -f "gzserver" > /dev/null; then
    log_info "✓ Gazebo已成功启动"
    log_info "PID: $GAZEBO_PID"
else
    log_error "✗ Gazebo启动失败"
    exit 1
fi

# 检查话题
log_info "检查Gazebo相关话题:"
ros2 topic list | grep -E "(gazebo|world)" | head -3

# 等待用户关闭
log_info "按Enter键关闭Gazebo..."
read

# 清理
kill $GAZEBO_PID 2>/dev/null || true
wait $GAZEBO_PID 2>/dev/null || true
log_info "Gazebo已关闭"