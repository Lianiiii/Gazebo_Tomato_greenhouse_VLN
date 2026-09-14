#!/bin/bash
# 测试各个组件是否能正常工作

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

echo "====================================="
echo "测试TomatoBot组件"
echo "====================================="
echo ""

# 测试1: 检查话题列表
log_step "1. 检查基本ROS功能..."
log_info "当前ROS核心状态:"
ros2 topic list > /dev/null 2>&1 && log_info "✓ ROS2核心运行正常" || log_error "✗ ROS2核心未运行"

log_info "可用的节点:"
ros2 node list 2>/dev/null | head -5

echo ""

# 测试2: 测试launch文件语法
log_step "2. 测试launch文件语法..."
log_info "测试tomato_farm_world.launch.py..."
ros2 pkg list | grep tomato_farm_simulator > /dev/null 2>&1 && {
    ros2 launch tomato_farm_simulator tomato_farm_world.launch.py --show-args > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        log_info "✓ launch文件语法正确"
    else
        log_error "✗ launch文件有语法错误"
    fi
} || log_error "✗ tomato_farm_simulator包未找到"

echo ""

# 测试3: 测试TomatoBot描述
log_step "3. 测试TomatoBot描述包..."
log_info "检查URDF文件..."
if [ -f "$SCRIPT_DIR/src/tomato_bot_description/urdf/tomato_bot.urdf" ]; then
    log_info "✓ URDF文件存在"
    # 检查URDF是否有效
    check_urdf "$SCRIPT_DIR/src/tomato_bot_description/urdf/tomato_bot.urdf" > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        log_info "✓ URDF格式正确"
    else
        log_error "✗ URDF格式错误"
    fi
else
    log_error "✗ URDF文件不存在"
fi

echo ""

# 测试4: 测试控制节点
log_step "4. 测试控制节点..."
log_info "测试keyboard_control节点..."
ros2 pkg list | grep tomato_bot_controller > /dev/null 2>&1 && {
    ros2 run tomato_bot_controller keyboard_control --help > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        log_info "✓ keyboard_control节点可用"
    else
        log_error "✗ keyboard_control节点不可用"
    fi
} || log_error "✗ tomato_bot_controller包未找到"

echo ""

# 测试5: 检查依赖
log_step "5. 检查关键依赖..."
log_info "检查Gazebo相关包:"
for pkg in gazebo_ros gazebo_ros_pkgs gazebo_ros2_control; do
    if ros2 pkg list | grep -q "$pkg"; then
        log_info "  ✓ $pkg 已安装"
    else
        log_warn "  ⚠ $pkg 未安装"
    fi
done

echo ""
log_step "6. 测试模型加载..."
# 检查世界文件是否存在
if [ -f "$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world" ]; then
    log_info "✓ 世界文件存在"
else
    log_error "✗ 世界文件不存在"
fi

echo ""
log_info "测试完成!"