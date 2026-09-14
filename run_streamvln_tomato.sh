#!/usr/bin/env bash
# ============================================================================
# run_streamvln_tomato.sh
# 可选路径：StreamVLN HTTP 服务 + 番茄大棚 + TomatoBot。
# 最小可用仿真请优先用：./run_tomato_bot_test.sh（不依赖 StreamVLN/Go2）。
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STREAMVLN_DIR="/home/ylubt2204/StreamVLN"
CONDA_BASE="/home/ylubt2204/miniconda3"
STREAMVLN_ENV="$CONDA_BASE/envs/streamvln"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

# ============================================================================
# Prerequisites
# ============================================================================
log_step "Checking prerequisites..."
[ -d "$STREAMVLN_ENV" ] || { log_error "StreamVLN conda env not found"; exit 1; }
[ -f "/opt/ros/$ROS_DISTRO/setup.bash" ] || { log_error "ROS2 not found"; exit 1; }

# Source ROS2 first (before any conda interference)
source "/opt/ros/$ROS_DISTRO/setup.bash"
WS_SETUP="$SCRIPT_DIR/install/setup.bash"
if [ -f "$WS_SETUP" ]; then source "$WS_SETUP"; else
    log_warn "Building workspace..."
    cd "$SCRIPT_DIR" && colcon build --symlink-install --packages-ignore gz_tomato_farm_generator
    source "$WS_SETUP"
fi
log_info "All prerequisites OK."

# ============================================================================
# Parse args
# ============================================================================
HEADLESS=false; SERVER_PORT=5801; MODEL_PATH=""
VLN_INSTRUCTION="Walk forward through the tomato farm rows. Navigate carefully between the plants."
usage() { echo "Usage: $0 [--headless] [--port PORT] [--model PATH] [--instruction TEXT]"; exit 0; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        --headless) HEADLESS=true; shift ;; --port) SERVER_PORT="$2"; shift 2 ;;
        --model) MODEL_PATH="$2"; shift 2 ;; --instruction) VLN_INSTRUCTION="$2"; shift 2 ;;
        --help) usage ;; *) log_error "Unknown: $1"; usage ;;
    esac
done

# ============================================================================
# Start StreamVLN server (conda, isolated)
# ============================================================================
log_step "Starting StreamVLN server..."
kill $(lsof -t -i:$SERVER_PORT 2>/dev/null) 2>/dev/null || true; sleep 1

SERVER_LOG="/tmp/streamvln_server_$(date +%Y%m%d_%H%M%S).log"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    env -i HOME="$HOME" PATH="$STREAMVLN_ENV/bin:/usr/bin" \
    "$STREAMVLN_ENV/bin/python" "$STREAMVLN_DIR/streamvln/http_realworld_server.py" \
    --port $SERVER_PORT ${MODEL_PATH:+--model_path $MODEL_PATH} \
    > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!; echo $SERVER_PID > /tmp/streamvln_server.pid
log_info "PID $SERVER_PID (log: $SERVER_LOG)"

for i in $(seq 1 180); do
    curl -s "http://localhost:$SERVER_PORT/health" >/dev/null 2>&1 && { log_info "Server ready! ✓"; break; }
    [ $i -eq 180 ] && { log_error "Server failed"; tail -30 "$SERVER_LOG"; exit 1; }; sleep 1
done

# ============================================================================
# Gazebo + TomatoBot + VLN Client (system env)
# ============================================================================
log_step "Starting Gazebo + 2mx3m Tomato Farm + TomatoBot..."

cd "$SCRIPT_DIR"

# Remove conda paths from LD_LIBRARY_PATH while keeping everything else
# This prevents the GDAL/libtiff conflict with OpenCV in cv_bridge
OIFS="$IFS"; IFS=':'; CLEAN_LD_PATH=""
for p in $LD_LIBRARY_PATH; do
    case "$p" in *conda*) ;; *) CLEAN_LD_PATH="${CLEAN_LD_PATH:+$CLEAN_LD_PATH:}$p" ;; esac
done; IFS="$OIFS"
export LD_LIBRARY_PATH="$CLEAN_LD_PATH"

export DISPLAY=:0
export LIBGL_ALWAYS_SOFTWARE=1
export GAZEBO_MODEL_PATH="$SCRIPT_DIR/install/tomato_farm_simulator/share/tomato_farm_simulator/models"

HEADLESS_ARG=""; $HEADLESS && HEADLESS_ARG="headless:=True"
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py \
    $HEADLESS_ARG

log_step "Shutting down..."
[ -f /tmp/streamvln_server.pid ] && kill $(cat /tmp/streamvln_server.pid) 2>/dev/null || true
rm -f /tmp/streamvln_server.pid; log_info "Done."
