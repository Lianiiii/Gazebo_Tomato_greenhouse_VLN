#!/bin/bash
# 完整的TomatoBot系统测试

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

echo "====================================="
echo "TomatoBot完整系统测试"
echo "====================================="
echo ""

# 清理残留进程
log_step "1. 清理残留进程..."
pkill -f gzserver 2>/dev/null || true
pkill -f gzclient 2>/dev/null || true
pkill -f python 2>/dev/null || true
sleep 2

# 启动Gazebo
log_step "2. 启动Gazebo仿真环境..."
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py headless:=True &
GAZEBO_PID=$!

# 等待Gazebo启动
sleep 8

# 检查Gazebo
if pgrep -f "gzserver" > /dev/null; then
    log_info "✓ Gazebo已启动"
else
    log_error "✗ Gazebo启动失败"
    exit 1
fi

# 启动TomatoBot
log_step "3. 生成TomatoBot机器人..."
ros2 launch tomato_bot_description spawn_tomato_bot.launch.py &
SPAWN_PID=$!

# 等待机器人生成
sleep 5

# 检查机器人
if ros2 topic list | grep -q "/tf"; then
    log_info "✓ 机器人已生成"
else
    log_warn "⚠ 机器人生成状态未知"
fi

# 启动RViz（可选）
log_step "4. 启动RViz可视化..."
read -p "是否启动RViz? (y/n): " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rviz2 -d "$SCRIPT_DIR/src/tomato_bot_controller/config/tomato_bot_rviz.rviz" &
    RVIZ_PID=$!
    log_info "✓ RViz已启动"
fi

# 启动键盘控制
log_step "5. 启动键盘控制..."
read -p "是否启动键盘控制? (y/n): " -r
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ros2 run tomato_bot_controller keyboard_control &
    KEYBOARD_PID=$!
    log_info "✓ 键盘控制已启动"
    echo ""
    echo "控制说明:"
    echo "- W: 前进"
    echo "- S: 后退"
    echo "- A: 左移"
    echo "- D: 右移"
    echo "- Q: 左转"
    echo "- E: 右转"
    echo "- 空格: 停止"
    echo "- ESC: 退出"
    echo ""
fi

log_info "系统已启动完成！"
log_info "按Enter键关闭系统..."
read

# 关闭所有进程
log_step "正在关闭系统..."
kill $GAZEBO_PID 2>/dev/null || true
kill $SPAWN_PID 2>/dev/null || true
if [ ! -z "$RVIZ_PID" ]; then
    kill $RVIZ_PID 2>/dev/null || true
fi
if [ ! -z "$KEYBOARD_PID" ]; then
    kill $KEYBOARD_PID 2>/dev/null || true
fi
wait 2>/dev/null || true

log_info "系统已关闭"