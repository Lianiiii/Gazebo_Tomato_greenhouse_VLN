#!/bin/bash
# 最小化测试Gazebo启动
# 用于诊断Gazebo启动问题

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }

# 源ROS2环境
log_info "源ROS2环境..."
source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 清理任何残留的Gazebo进程
log_info "清理残留的Gazebo进程..."
killall -9 gzserver gzclient gazebo 2>/dev/null
sleep 2

# 设置环境变量
log_info "设置Gazebo环境变量..."
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models"
export GAZEBO_PLUGIN_PATH="/opt/ros/humble/lib:$GAZEBO_PLUGIN_PATH"
export LD_LIBRARY_PATH="/opt/ros/humble/lib:$LD_LIBRARY_PATH"

log_info "GAZEBO_MODEL_PATH: $GAZEBO_MODEL_PATH"
log_info "GAZEBO_PLUGIN_PATH: $GAZEBO_PLUGIN_PATH"

# 测试1: 使用最小world文件
log_info "测试1: 使用最小world文件启动Gazebo..."
MINIMAL_WORLD="$SCRIPT_DIR/test_minimal_world.sdf"

if [ ! -f "$MINIMAL_WORLD" ]; then
    log_error "最小world文件不存在: $MINIMAL_WORLD"
    exit 1
fi

# 后台启动gzserver，监控5秒
log_info "启动gzserver（最小world）..."
timeout 5 gzserver "$MINIMAL_WORLD" -s "/opt/ros/humble/lib/libgazebo_ros_init.so" --verbose 2>&1 | tee /tmp/gazebo_minimal_test.log &
GZSERVER_PID=$!

# 等待几秒
sleep 3

# 检查进程状态
if ps -p $GZSERVER_PID > /dev/null 2>&1; then
    log_info "✓ gzserver进程正在运行 (PID: $GZSERVER_PID)"
    # 检查日志
    if grep -q "Initialized" /tmp/gazebo_minimal_test.log; then
        log_info "✓ Gazebo已成功初始化"
    else
        log_warn "⚠ Gazebo可能正在初始化中"
    fi
    # 清理
    kill $GZSERVER_PID 2>/dev/null
    wait $GZSERVER_PID 2>/dev/null
else
    log_error "✗ gzserver进程已退出"
    log_error "日志输出："
    cat /tmp/gazebo_minimal_test.log | tail -20
fi

echo ""
log_info "测试2: 使用原world文件启动Gazebo..."
sleep 2

# 测试2: 使用原world文件
ORIGINAL_WORLD="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"

if [ ! -f "$ORIGINAL_WORLD" ]; then
    log_error "原world文件不存在: $ORIGINAL_WORLD"
    exit 1
fi

# 后台启动gzserver，监控5秒
log_info "启动gzserver（原world）..."
timeout 5 gzserver "$ORIGINAL_WORLD" -s "/opt/ros/humble/lib/libgazebo_ros_init.so" -s "/opt/ros/humble/lib/libgazebo_ros_factory.so" -s "/opt/ros/humble/lib/libgazebo_ros_force_system.so" --verbose 2>&1 | tee /tmp/gazebo_original_test.log &
GZSERVER_PID=$!

# 等待几秒
sleep 3

# 检查进程状态
if ps -p $GZSERVER_PID > /dev/null 2>&1; then
    log_info "✓ gzserver进程正在运行 (PID: $GZSERVER_PID)"
    # 检查日志
    if grep -q "Initialized" /tmp/gazebo_original_test.log; then
        log_info "✓ Gazebo已成功初始化"
    else
        log_warn "⚠ Gazebo可能正在初始化中"
    fi
    # 清理
    kill $GZSERVER_PID 2>/dev/null
    wait $GZSERVER_PID 2>/dev/null
else
    log_error "✗ gzserver进程已退出"
    log_error "日志输出："
    cat /tmp/gazebo_original_test.log | tail -20
fi

# 最终清理
log_info "清理所有Gazebo进程..."
killall -9 gzserver gzclient gazebo 2>/dev/null

log_info "测试完成"
log_info "查看详细日志："
echo "  - 最小world测试: /tmp/gazebo_minimal_test.log"
echo "  - 原world测试: /tmp/gazebo_original_test.log"
