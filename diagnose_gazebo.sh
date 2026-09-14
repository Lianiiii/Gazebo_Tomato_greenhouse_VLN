#!/bin/bash
# 简单的Gazebo诊断脚本
# 不需要长时间运行，快速检查问题

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_fail()  { echo -e "${RED}✗${NC} $1"; }

echo "=========================================="
echo "Gazebo 环境诊断"
echo "=========================================="

# 1. 检查ROS2安装
log_info "1. 检查ROS2安装..."
if [ -d "/opt/ros/$ROS_DISTRO" ]; then
    log_ok "ROS2 $ROS_DISTRO 已安装"
else
    log_fail "ROS2 $ROS_DISTRO 未安装"
    exit 1
fi

# 2. 检查Gazebo安装
log_info "2. 检查Gazebo安装..."
if command -v gzserver &> /dev/null; then
    GZ_VERSION=$(gzserver --version 2>&1 | head -1)
    log_ok "Gazebo已安装: $GZ_VERSION"
else
    log_fail "Gazebo未安装或不在PATH中"
    exit 1
fi

# 3. 检查Gazebo ROS插件
log_info "3. 检查Gazebo ROS插件..."
PLUGINS=(
    "/opt/ros/humble/lib/libgazebo_ros_init.so"
    "/opt/ros/humble/lib/libgazebo_ros_factory.so"
    "/opt/ros/humble/lib/libgazebo_ros_force_system.so"
)

ALL_PLUGINS_OK=true
for plugin in "${PLUGINS[@]}"; do
    if [ -f "$plugin" ]; then
        log_ok "插件存在: $(basename $plugin)"
    else
        log_fail "插件缺失: $(basename $plugin)"
        ALL_PLUGINS_OK=false
    fi
done

if [ "$ALL_PLUGINS_OK" = false ]; then
    log_error "部分Gazebo ROS插件缺失，请检查安装"
    exit 1
fi

# 4. 检查world文件
log_info "4. 检查world文件..."
WORLD_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/worlds/2mx3m/tomato_farm_2mx3m_gazebo_classic.world"
if [ -f "$WORLD_FILE" ]; then
    log_ok "World文件存在: $WORLD_FILE"
else
    log_fail "World文件不存在: $WORLD_FILE"
    exit 1
fi

# 5. 检查模型目录
log_info "5. 检查模型目录..."
MODEL_DIR="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/models"
if [ -d "$MODEL_DIR" ]; then
    MODEL_COUNT=$(ls -1 "$MODEL_DIR" | wc -l)
    log_ok "模型目录存在，包含 $MODEL_COUNT 个模型"

    # 检查world文件中引用的关键模型
    REQUIRED_MODELS=("structure_0" "metal_34001" "tomato_763407" "flowerpot_763407" "lamp_294731" "soilbed_466022")
    MISSING_MODELS=()

    for model in "${REQUIRED_MODELS[@]}"; do
        if [ -d "$MODEL_DIR/$model" ]; then
            log_ok "  模型存在: $model"
        else
            log_fail "  模型缺失: $model"
            MISSING_MODELS+=("$model")
        fi
    done

    if [ ${#MISSING_MODELS[@]} -gt 0 ]; then
        log_error "缺失的模型: ${MISSING_MODELS[*]}"
        exit 1
    fi
else
    log_fail "模型目录不存在: $MODEL_DIR"
    exit 1
fi

# 6. 检查launch文件
log_info "6. 检查launch文件..."
LAUNCH_FILE="$SCRIPT_DIR/src/aoc_tomato_farm/tomato_farm_simulator/launch/tomato_farm_world.launch.py"
if [ -f "$LAUNCH_FILE" ]; then
    if python3 -m py_compile "$LAUNCH_FILE" 2>/dev/null; then
        log_ok "Launch文件存在且语法正确"
    else
        log_fail "Launch文件存在但语法错误"
        exit 1
    fi
else
    log_fail "Launch文件不存在: $LAUNCH_FILE"
    exit 1
fi

# 7. 检查编译状态
log_info "7. 检查编译状态..."
if [ -f "$SCRIPT_DIR/install/tomato_farm_simulator/share/tomato_farm_simulator/launch/tomato_farm_world.launch.py" ]; then
    log_ok "包已编译并安装"
else
    log_fail "包未编译或安装失败，请运行: colcon build --packages-select tomato_farm_simulator"
    exit 1
fi

# 8. 检查环境变量
log_info "8. 检查环境变量设置..."
source "/opt/ros/$ROS_DISTRO/setup.bash" 2>/dev/null
source "$SCRIPT_DIR/install/setup.bash" 2>/dev/null

if [ -n "$ROS_DISTRO" ]; then
    log_ok "ROS_DISTRO: $ROS_DISTRO"
else
    log_fail "ROS_DISTRO 未设置"
fi

# 9. 快速Gazebo测试（不启动完整服务器）
log_info "9. 快速Gazebo版本测试..."
if /usr/bin/gzserver --version 2>&1 | grep -q "Gazebo multi-robot simulator"; then
    log_ok "Gazebo可以正常执行"
else
    log_fail "Gazebo执行失败"
    exit 1
fi

echo "=========================================="
log_info "诊断完成！所有检查通过。"
echo "=========================================="
echo ""
echo "建议的测试命令："
echo "1. 启动完整测试: ./test_fixed_launch.sh"
echo "2. 直接启动Gazebo: gzserver $WORLD_FILE -s /opt/ros/humble/lib/libgazebo_ros_init.so"
echo "3. 启动launch文件: ros2 launch tomato_farm_simulator tomato_farm_world.launch.py"
