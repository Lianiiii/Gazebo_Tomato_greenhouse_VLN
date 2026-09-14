#!/bin/bash
# 修复后的Gazebo测试脚本

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
export GAZEBO_PLUGIN_PATH="/opt/ros/humble/lib:$GAZEBO_PLUGIN_PATH"
export LD_LIBRARY_PATH="/opt/ros/humble/lib:$LD_LIBRARY_PATH"

log_step "启动修复后的Gazebo测试..."

# 清理任何残留的Gazebo进程
log_info "清理残留进程..."
pkill -f gzserver 2>/dev/null || true
pkill -f gzclient 2>/dev/null || true
sleep 2

# 检查world文件
WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"
if [ ! -f "$WORLD_FILE" ]; then
    log_error "世界文件不存在: $WORLD_FILE"
    exit 1
fi

log_info "使用修复后的launch文件启动..."

# 启动Gazebo
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py headless:=True &
GAZEBO_PID=$!

# 等待启动
sleep 5

# 检查是否成功
if pgrep -f "gzserver" > /dev/null; then
    log_info "✓ Gazebo已启动"

    # 检查ROS话题
    sleep 3
    log_info "检查Gazebo相关话题:"
    ros2 topic list | grep -E "(gazebo|world)" | head -3

    # 等待用户输入
    log_info "按Enter键关闭测试..."
    read
else
    log_error "✗ Gazebo启动失败"

    # 查看错误日志
    log_error "检查日志:"
    if [ -d "$HOME/.ros/log" ]; then
        ls -la "$HOME/.ros/log/" | tail -5
    fi
fi

# 清理
log_step "关闭进程..."
kill $GAZEBO_PID 2>/dev/null || true
wait $GAZEBO_PID 2>/dev/null || true
log_info "测试完成"