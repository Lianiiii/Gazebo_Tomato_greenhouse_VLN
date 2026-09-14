#!/usr/bin/env bash
# ============================================================================
# run_tomato_bot_test.sh
# 中文说明：一键启动大棚 + TomatoBot + 键盘控制 + RViz（不重复 spawn）。
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

cleanup() {
  log_step "正在关闭系统..."
  if [ -n "${KEYBOARD_PID:-}" ]; then kill "$KEYBOARD_PID" 2>/dev/null || true; fi
  if [ -n "${RVIZ_PID:-}" ]; then kill "$RVIZ_PID" 2>/dev/null || true; fi
  if [ -n "${GAZEBO_PID:-}" ]; then kill "$GAZEBO_PID" 2>/dev/null || true; fi
  pkill -f "tomato_farm_world.launch.py" 2>/dev/null || true
  pkill -9 gzserver 2>/dev/null || true
  pkill -9 gzclient 2>/dev/null || true
}
trap cleanup EXIT

source "/opt/ros/$ROS_DISTRO/setup.bash"
source "$SCRIPT_DIR/install/setup.bash"

# 清理残留 Gazebo，避免端口占用导致黑屏
pkill -9 gzserver 2>/dev/null || true
pkill -9 gzclient 2>/dev/null || true
sleep 1

# WSL 下 CycloneDDS 易耗尽 participant，固定 FastDDS 更稳
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/install/tomato_farm_simulator/share/tomato_farm_simulator/models:${GAZEBO_MODEL_PATH:-}"
export GAZEBO_PLUGIN_PATH="/opt/ros/$ROS_DISTRO/lib:${GAZEBO_PLUGIN_PATH:-}"
export DISPLAY="${DISPLAY:-:0}"

WORLD_FILE="$SCRIPT_DIR/install/tomato_farm_simulator/share/tomato_farm_simulator/worlds/short_metal_4pack/tomato_farm_short_metal_4pack_gazebo_classic.world"
if [ ! -f "$WORLD_FILE" ]; then
  WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/short_metal_4pack/tomato_farm_short_metal_4pack_gazebo_classic.world"
fi
log_step "启动 Gazebo 大棚 + TomatoBot（场景: short_metal_4pack）..."
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py "world:=$WORLD_FILE" &
GAZEBO_PID=$!

log_info "等待仿真与机器人就绪..."
for i in $(seq 1 60); do
  if ros2 topic list 2>/dev/null | grep -q '/cmd_vel'; then
    log_info "检测到 /cmd_vel，机器人插件已就绪"
    break
  fi
  sleep 1
done

log_step "启动键盘控制..."
# 终端 stdin 读键必须前台运行；这里放到独立终端不可用时，改为提示手动启动
if [ -t 0 ]; then
  log_info "请另开一个终端执行: ros2 run tomato_bot_controller keyboard_control"
  log_info "（不要在本脚本后台启动键盘，否则 termios 读不到按键）"
else
  log_warn "当前无前台 TTY，跳过自动键盘启动"
fi
KEYBOARD_PID=""

RVIZ_CFG="$SCRIPT_DIR/src/tomato_bot_controller/config/tomato_bot_rviz.rviz"
if [ ! -f "$RVIZ_CFG" ]; then
  RVIZ_CFG="$SCRIPT_DIR/install/tomato_bot_controller/share/tomato_bot_controller/config/tomato_bot_rviz.rviz"
fi
if [ -f "$RVIZ_CFG" ]; then
  log_step "启动 RViz..."
  rviz2 -d "$RVIZ_CFG" &
  RVIZ_PID=$!
else
  log_warn "未找到 RViz 配置: $RVIZ_CFG"
fi

log_info "TomatoBot 测试系统已启动"
echo ""
echo "控制说明:"
echo "  另开终端并保持前台焦点后运行:"
echo "    source /opt/ros/humble/setup.bash"
echo "    source $SCRIPT_DIR/install/setup.bash"
echo "    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
echo "    ros2 run tomato_bot_controller keyboard_control"
echo "  W/S: 前进/后退"
echo "  A/D 或 Q/E: 左转/右转"
echo "  空格 或 X: 停止"
echo "  R/T: 线速度 ±10%，F/G: 角速度 ±10%"
echo "  Ctrl+C: 退出键盘节点"
echo ""
echo "也可另开终端发送速度指令:"
echo "  ros2 topic pub /cmd_vel geometry_msgs/msg/Twist \"{linear: {x: 0.2}, angular: {z: 0.0}}\" -r 10"
echo ""
read -p "按 Enter 键退出..."

