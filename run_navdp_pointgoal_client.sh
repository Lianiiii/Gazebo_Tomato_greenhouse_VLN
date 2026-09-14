#!/usr/bin/env bash
# 中文说明：在 conda navdp 环境下启动 NavDP PointGoal 客户端。
# 前置：已运行 ./run_tomato_bot_test.sh，且 NavDP server 已在对应端口启动。
# 用法：
#   ./run_navdp_pointgoal_client.sh --goal_x 4.0 --goal_y 1.5
#   ./run_navdp_pointgoal_client.sh --goal_x 4.0 --goal_y 1.5 --port 8888 --speed 0.4

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROS_DISTRO="humble"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$#" -lt 1 ]; then
  echo "用法: $0 --goal_x <x> --goal_y <y> [--port 8888] [--speed 0.5] [--arrive_dist 1.0]"
  exit 1
fi

# 激活 conda navdp（兼容 miniconda / anaconda）
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  # shellcheck disable=SC1091
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  # shellcheck disable=SC1091
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
  # shellcheck disable=SC1091
  source "/opt/conda/etc/profile.d/conda.sh"
else
  log_error "找不到 conda.sh，请先手动 conda activate navdp"
  exit 1
fi

conda activate navdp
log_info "已激活 conda 环境: navdp"

python - <<'PY'
import importlib.util
import sys
missing = []
for m in ("casadi", "requests", "cv2", "numpy"):
    if importlib.util.find_spec(m) is None:
        missing.append(m)
if missing:
    print("缺少依赖:", ", ".join(missing))
    if "casadi" in missing:
        print("请执行: pip install casadi")
    sys.exit(1)
print("依赖检查通过")
PY

# shellcheck disable=SC1090
source "/opt/ros/${ROS_DISTRO}/setup.bash"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/install/setup.bash"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"

log_info "启动 navdp_pointgoal_client ..."
log_warn "请勿同时运行 keyboard_control，避免抢占 /cmd_vel"
exec ros2 run tomato_bot_controller navdp_pointgoal_client -- "$@"
