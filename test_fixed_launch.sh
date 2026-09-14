#!/bin/bash
# 修复后的启动测试脚本
# 正确设置环境变量并启动tomato_farm_world

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }

# 清理任何残留的Gazebo进程
log_info "清理残留的Gazebo进程..."
killall -9 gzserver gzclient gazebo 2>/dev/null
sleep 2

# 源ROS2环境
log_info "源ROS2环境..."
source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 设置Gazebo环境变量
log_info "设置Gazebo环境变量..."
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models:$GAZEBO_MODEL_PATH"
export GAZEBO_PLUGIN_PATH="/opt/ros/humble/lib:$GAZEBO_PLUGIN_PATH"
export LD_LIBRARY_PATH="/opt/ros/humble/lib:$LD_LIBRARY_PATH"

log_info "GAZEBO_MODEL_PATH: $GAZEBO_MODEL_PATH"
log_info "GAZEBO_PLUGIN_PATH: $GAZEBO_PLUGIN_PATH"

# 检查world文件
WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"
if [ ! -f "$WORLD_FILE" ]; then
    log_error "World文件不存在: $WORLD_FILE"
    exit 1
fi
log_info "World文件存在: $WORLD_FILE"

# 启动launch文件
log_info "启动tomato_farm_world.launch.py..."
log_info "=========================================="

# 使用timeout限制运行时间，避免卡死
timeout 10 ros2 launch tomato_farm_simulator tomato_farm_world.launch.py 2>&1 | tee /tmp/tomato_farm_launch_test.log

# 检查结果
EXIT_CODE=${PIPESTATUS[0]}
log_info "=========================================="

if [ $EXIT_CODE -eq 124 ]; then
    log_info "测试完成（超时退出，这是正常的）"
    log_info "检查Gazebo进程状态..."

    # 检查是否有Gazebo进程在运行
    if pgrep -f "gzserver" > /dev/null; then
        log_info "✓ Gazebo服务器正在运行"
        GZSERVER_PID=$(pgrep -f "gzserver" | head -1)
        log_info "  PID: $GZSERVER_PID"

        # 检查进程是否正常（没有崩溃）
        if ps -p $GZSERVER_PID > /dev/null 2>&1; then
            log_info "✓ 进程状态正常"
            # 清理
            kill $GZSERVER_PID 2>/dev/null
        else
            log_error "✗ Gazebo进程已崩溃"
        fi
    else
        log_error "✗ 没有找到Gazebo进程"
        log_error "查看日志："
        tail -30 /tmp/tomato_farm_launch_test.log
    fi
elif [ $EXIT_CODE -eq 0 ]; then
    log_info "启动正常退出"
else
    log_error "启动失败，退出码: $EXIT_CODE"
    log_error "查看日志："
    tail -30 /tmp/tomato_farm_launch_test.log
fi

# 最终清理
log_info "清理所有Gazebo进程..."
killall -9 gzserver gzclient gazebo 2>/dev/null

log_info "测试完成"
log_info "详细日志: /tmp/tomato_farm_launch_test.log"
