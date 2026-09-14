#!/bin/bash
# 直接使用gzserver启动测试

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 源ROS2
source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 设置环境变量
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models"
export GAZEBO_PLUGIN_PATH="/opt/ros/humble/lib:$GAZEBO_PLUGIN_PATH"
export LD_LIBRARY_PATH="/opt/ros/humble/lib:$LD_LIBRARY_PATH"

log_info "直接测试gzserver启动..."

WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"

if [ ! -f "$WORLD_FILE" ]; then
    log_error "世界文件不存在: $WORLD_FILE"
    exit 1
fi

log_info "启动世界文件: $WORLD_FILE"

# 使用完整路径启动
gzserver \
    "$WORLD_FILE" \
    -s "/opt/ros/humble/lib/libgazebo_ros_init.so" \
    -s "/opt/ros/humble/lib/libgazebo_ros_factory.so" \
    -s "/opt/ros/humble/lib/libgazebo_ros_force_system.so" \
    --verbose