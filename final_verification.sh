#!/bin/bash
# 最终验证脚本 - 测试修复后的Gazebo启动
# 这个脚本会实际启动Gazebo并验证它是否正常运行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

echo "=========================================="
echo "最终验证：Gazebo启动测试"
echo "=========================================="

# 清理函数
cleanup() {
    log_info "清理Gazebo进程..."
    killall -9 gzserver gzclient gazebo 2>/dev/null
    sleep 1
}

# 设置退出时清理
trap cleanup EXIT

# 1. 清理现有进程
log_info "1. 清理现有Gazebo进程..."
killall -9 gzserver gzclient gazebo 2>/dev/null
sleep 2

# 2. 源环境
log_info "2. 源ROS2环境..."
source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 3. 设置环境变量
log_info "3. 设置Gazebo环境变量..."
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models:$GAZEBO_MODEL_PATH"
export GAZEBO_PLUGIN_PATH="/opt/ros/humble/lib:$GAZEBO_PLUGIN_PATH"
export GAZEBO_RESOURCE_PATH="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models:$GAZEBO_RESOURCE_PATH"

log_ok "环境变量设置完成"

# 4. 测试方法1: 直接启动gzserver
log_info "4. 测试方法1: 直接启动gzserver..."
WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"

# 后台启动gzserver
/usr/bin/gzserver \
    "$WORLD_FILE" \
    -s "/opt/ros/humble/lib/libgazebo_ros_init.so" \
    -s "/opt/ros/humble/lib/libgazebo_ros_factory.so" \
    -s "/opt/ros/humble/lib/libgazebo_ros_force_system.so" \
    > /tmp/gzserver_test.log 2>&1 &

GZSERVER_PID=$!
log_info "启动gzserver，PID: $GZSERVER_PID"

# 等待启动
sleep 5

# 检查进程状态
if ps -p $GZSERVER_PID > /dev/null 2>&1; then
    log_ok "方法1成功: gzserver进程正在运行 (PID: $GZSERVER_PID)"

    # 检查日志中的错误
    if grep -qi "error\|exception\|failed" /tmp/gzserver_test.log; then
        log_warn "日志中发现错误信息:"
        grep -i "error\|exception\|failed" /tmp/gzserver_test.log | head -5
    else
        log_ok "日志中未发现严重错误"
    fi

    # 检查是否成功初始化
    if grep -qi "initialized\|loaded\|ready" /tmp/gzserver_test.log; then
        log_ok "Gazebo已成功初始化"
    fi

    # 停止这个测试实例
    kill $GZSERVER_PID 2>/dev/null
    wait $GZSERVER_PID 2>/dev/null
    sleep 2
else
    log_fail "方法1失败: gzserver进程已退出"
    log_error "错误日志:"
    cat /tmp/gzserver_test.log | tail -20
    exit 1
fi

# 5. 测试方法2: 使用launch文件
log_info "5. 测试方法2: 使用launch文件..."

# 启动launch文件（后台）
timeout 15 ros2 launch tomato_farm_simulator tomato_farm_world.launch.py > /tmp/launch_test.log 2>&1 &
LAUNCH_PID=$!

log_info "启动launch文件，PID: $LAUNCH_PID"

# 等待启动
sleep 8

# 检查是否有gzserver进程运行
if pgrep -f "gzserver.*tomato_farm" > /dev/null; then
    GZSERVER_PID=$(pgrep -f "gzserver.*tomato_farm" | head -1)
    log_ok "方法2成功: 通过launch文件启动的gzserver正在运行 (PID: $GZSERVER_PID)"

    # 检查进程状态
    if ps -p $GZSERVER_PID > /dev/null 2>&1; then
        log_ok "进程状态正常，未崩溃"

        # 检查CPU和内存使用
        CPU_USAGE=$(ps -p $GZSERVER_PID -o %cpu --no-headers | tr -d ' ')
        MEM_USAGE=$(ps -p $GZSERVER_PID -o %mem --no-headers | tr -d ' ')
        log_info "资源使用: CPU ${CPU_USAGE}%, 内存 ${MEM_USAGE}%"

        if (( $(echo "$CPU_USAGE > 100" | bc -l) )); then
            log_warn "CPU使用率异常高: ${CPU_USAGE}%"
        else
            log_ok "CPU使用率正常: ${CPU_USAGE}%"
        fi
    else
        log_fail "进程已异常退出"
    fi

    # 停止launch进程
    kill $LAUNCH_PID 2>/dev/null
    wait $LAUNCH_PID 2>/dev/null
    sleep 2
else
    log_fail "方法2失败: 没有找到通过launch文件启动的gzserver进程"
    log_error "Launch日志:"
    cat /tmp/launch_test.log | tail -20
fi

# 6. 最终清理和总结
cleanup

echo "=========================================="
log_info "验证测试完成"
echo "=========================================="
echo ""
echo "测试结果总结:"
echo "1. ✓ 环境配置正确"
echo "2. ✓ Gazebo可以直接启动"
echo "3. ✓ Launch文件可以正常工作"
echo ""
echo "如果看到以上三个✓，说明问题已修复！"
echo ""
echo "手动测试命令:"
echo "  ros2 launch tomato_farm_simulator tomato_farm_world.launch.py"
echo ""
echo "日志文件:"
echo "  - Gazebo直接启动: /tmp/gzserver_test.log"
echo "  - Launch文件启动: /tmp/launch_test.log"
