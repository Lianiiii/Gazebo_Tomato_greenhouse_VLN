# 中文说明：C1 Safe Trajectory Re-ranking（Phase1 几何 + Phase2 重排）。
# 用客户端 raw depth（米）建固定窗口局部 BEV 代价，对候选轨迹做左右轮迹 clearance，
# 再 hard reject + soft fuse 选轨。纯函数，无 ROS 依赖；由 PointGoal 客户端钩入。
#
# 轴约定（写死，勿擅自镜像）：
#   Optical（深度相机）：x 右，y 下，z 前
#   BEV / 轨迹水平系：X = z_cam（前），Y = -x_cam（左为正），高度 Z_up = -y_cam
#   与 navdp_pointgoal_client.transform_traj_camera_to_world 的 p[0],p[1] 一致
#
# 栅格约定：
#   行 → X∈[0, x_max]，行 0 近端；列 → Y∈[-y_half, y_half]，列中心为 Y=0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from tomato_bot_controller.robot_geometry import RobotGeom


@dataclass
class BevCost:
    """局部 BEV 占用与距离场。"""

    occ: np.ndarray  # (H, W) uint8，1=占用，0=空闲
    dist: np.ndarray  # (H, W) float32，到最近障碍的距离（米）
    res: float
    x_max: float
    y_half: float

    @property
    def shape(self) -> Tuple[int, int]:
        return int(self.occ.shape[0]), int(self.occ.shape[1])


@dataclass
class RerankResult:
    """C1 重排结果（相机系选中轨迹 + 诊断字段）。"""

    traj_cam: np.ndarray  # (T, 2+)
    chosen_idx: int
    clearances: np.ndarray  # (N,)
    fused_scores: np.ndarray  # (N,)
    rejected_mask: np.ndarray  # (N,) bool
    v_max_scale: float  # 正常 1.0；全拒降速 <1；极低旋转时 0
    debug: Dict[str, Any] = field(default_factory=dict)


def depth_to_bev_cost(
    depth_m: np.ndarray,
    intrinsic: np.ndarray,
    z_min: float = 0.05,
    z_max: float = 1.2,
    res: float = 0.05,
    x_max: float = 4.0,
    y_half: float = 2.0,
) -> BevCost:
    """raw depth（米）→ 固定窗口 BEV 占用 + 距离变换。

    depth==0 / 非有限值视为无效，不当作障碍。
    """
    depth = np.asarray(depth_m, dtype=np.float32)
    if depth.ndim == 3:
        depth = depth[:, :, 0]
    K = np.asarray(intrinsic, dtype=np.float64).reshape(3, 3)
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])

    h_img, w_img = depth.shape
    uu, vv = np.meshgrid(np.arange(w_img, dtype=np.float32), np.arange(h_img, dtype=np.float32))
    z = depth
    valid = (z > 0.0) & np.isfinite(z) & (z < 10.0)
    x_cam = (uu - cx) * z / fx
    y_cam = (vv - cy) * z / fy

    # Optical → BEV / 水平系
    X = z[valid]  # forward
    Y = -x_cam[valid]  # left +
    Z_up = -y_cam[valid]

    height_ok = (Z_up >= float(z_min)) & (Z_up <= float(z_max))
    X = X[height_ok]
    Y = Y[height_ok]

    n_rows = int(np.ceil(float(x_max) / float(res)))
    n_cols = int(np.ceil(2.0 * float(y_half) / float(res)))
    n_rows = max(n_rows, 1)
    n_cols = max(n_cols, 1)
    occ = np.zeros((n_rows, n_cols), dtype=np.uint8)

    if X.size > 0:
        in_win = (X >= 0.0) & (X < float(x_max)) & (Y >= -float(y_half)) & (Y < float(y_half))
        Xw = X[in_win]
        Yw = Y[in_win]
        rows = np.floor(Xw / float(res)).astype(np.int32)
        cols = np.floor((Yw + float(y_half)) / float(res)).astype(np.int32)
        rows = np.clip(rows, 0, n_rows - 1)
        cols = np.clip(cols, 0, n_cols - 1)
        occ[rows, cols] = 1

    # OpenCV: 非零=可通行，零=障碍；输出像素距离
    free = np.where(occ > 0, 0, 255).astype(np.uint8)
    dist_px = cv2.distanceTransform(free, cv2.DIST_L2, 3)
    dist_m = dist_px.astype(np.float32) * float(res)
    return BevCost(occ=occ, dist=dist_m, res=float(res), x_max=float(x_max), y_half=float(y_half))


def _world_to_grid(x: float, y: float, bev: BevCost) -> Optional[Tuple[int, int]]:
    """BEV 米制坐标 → 栅格 (row, col)；窗外返回 None。"""
    if x < 0.0 or x >= bev.x_max or y < -bev.y_half or y >= bev.y_half:
        return None
    row = int(np.floor(x / bev.res))
    col = int(np.floor((y + bev.y_half) / bev.res))
    h, w = bev.shape
    if row < 0 or row >= h or col < 0 or col >= w:
        return None
    return row, col


def _sample_dist(x: float, y: float, bev: BevCost) -> float:
    """查询距离场；窗外按 0（保守）。"""
    idx = _world_to_grid(x, y, bev)
    if idx is None:
        return 0.0
    return float(bev.dist[idx[0], idx[1]])


def trajectory_clearance(
    traj_cam: np.ndarray,
    bev: BevCost,
    geom: RobotGeom,
    x_min: float = 0.0,
    x_horizon: float = 1.5,
) -> float:
    """对一条相机系折线做左右轮迹 clearance（米）。

    只评估 x_min ≤ X ≤ x_horizon 的近场段，避免远端弯进障碍把近场可走轨全拒掉。
    返回 max(0, min_over_samples - inflate)。
    航向由相邻点差分；横向单位向量取航向逆时针 90°（左为正，与 +Y 一致）。
    """
    traj = np.asarray(traj_cam, dtype=np.float64)
    if traj.ndim != 2 or traj.shape[0] < 1 or traj.shape[1] < 2:
        return 0.0

    half_track = 0.5 * float(geom.wheel_separation)
    inflate = float(geom.inflate)
    x_lo = float(x_min)
    x_hi = float(x_horizon)
    if x_hi < x_lo:
        x_lo, x_hi = x_hi, x_lo
    min_d = float("inf")
    sampled = False

    n = traj.shape[0]
    for i in range(n):
        px, py = float(traj[i, 0]), float(traj[i, 1])
        if px < x_lo or px > x_hi:
            continue
        if i + 1 < n:
            dx = float(traj[i + 1, 0] - px)
            dy = float(traj[i + 1, 1] - py)
        elif i > 0:
            dx = float(px - traj[i - 1, 0])
            dy = float(py - traj[i - 1, 1])
        else:
            dx, dy = 1.0, 0.0
        norm = float(np.hypot(dx, dy))
        if norm < 1e-6:
            dx, dy = 1.0, 0.0
            norm = 1.0
        dx /= norm
        dy /= norm
        # 左法向（CCW 90°）：(-dy, dx)；左右轮 = p ± n * half_track
        nx, ny = -dy, dx
        for sign in (-1.0, 1.0):
            d = _sample_dist(px + sign * half_track * nx, py + sign * half_track * ny, bev)
            if d < min_d:
                min_d = d
        sampled = True

    if not sampled or not np.isfinite(min_d):
        return 0.0
    return float(max(0.0, min_d - inflate))


def clearances_for_trajectories(
    all_traj: np.ndarray,
    bev: BevCost,
    geom: RobotGeom,
    x_min: float = 0.0,
    x_horizon: float = 1.5,
) -> np.ndarray:
    """批量计算 clearance，输入 (N,T,>=2) 或 (1,N,T,>=2)。"""
    trajs = np.asarray(all_traj)
    if trajs.ndim == 4:
        trajs = trajs[0]
    if trajs.ndim != 3:
        raise ValueError(f"all_traj 期望 (N,T,C) 或 (1,N,T,C)，得到 {trajs.shape}")
    out = np.zeros((trajs.shape[0],), dtype=np.float64)
    for i in range(trajs.shape[0]):
        out[i] = trajectory_clearance(
            trajs[i],
            bev,
            geom,
            x_min=x_min,
            x_horizon=x_horizon,
        )
    return out


def _minmax_norm(x: np.ndarray) -> np.ndarray:
    """对一维数组做 min-max；全相等或空则返回 0.5 常量。"""
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    if x.size == 0:
        return x
    lo = float(np.min(x))
    hi = float(np.max(x))
    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        return np.full_like(x, 0.5)
    return (x - lo) / (hi - lo)


def preferred_rotate_sign(
    bev: BevCost,
    x_near: float = 1.5,
    goal_y: Optional[float] = None,
    goal_bias_thr: float = 0.15,
    free_margin: float = 0.05,
) -> int:
    """选原地旋转方向：优先明显更空旷的一侧，否则朝 goal 侧，避免正对墙时来回翻号。

    返回 +1 = 左转/CCW（朝 +Y），-1 = 右转/CW（朝 -Y）。
    列约定：小列号 = Y<0（右），大列号 = Y>0（左）。
    """
    left_score = 0.0
    right_score = 0.0
    if bev.dist.size > 0:
        n_rows = int(min(bev.shape[0], max(1, int(np.floor(float(x_near) / float(bev.res))))))
        mid = int(bev.shape[1] // 2)
        if mid > 0:
            left = bev.dist[:n_rows, mid:]
            right = bev.dist[:n_rows, :mid]
            left_score = float(np.mean(left)) if left.size else 0.0
            right_score = float(np.mean(right)) if right.size else 0.0
            if not np.isfinite(left_score):
                left_score = 0.0
            if not np.isfinite(right_score):
                right_score = 0.0

    # 左右空旷度差够大：跟 BEV，避免转到更堵的一侧
    if abs(left_score - right_score) >= float(free_margin):
        return 1 if left_score > right_score else -1

    # 否则朝目标侧转，减少背对 goal 空转/转过头
    if goal_y is not None and abs(float(goal_y)) >= float(goal_bias_thr):
        return 1 if float(goal_y) >= 0.0 else -1

    return 1 if left_score >= right_score else -1


def _squeeze_trajs(all_traj: np.ndarray) -> np.ndarray:
    """统一为 (N,T,C)。"""
    trajs = np.asarray(all_traj)
    if trajs.ndim == 4:
        trajs = trajs[0]
    if trajs.ndim != 3:
        raise ValueError(f"all_traj 期望 (N,T,C) 或 (1,N,T,C)，得到 {trajs.shape}")
    return trajs


def rerank_trajectories(
    all_traj: np.ndarray,
    all_values: np.ndarray,
    depth_m: np.ndarray,
    intrinsic: np.ndarray,
    robot_geom: RobotGeom,
    mode: str = "fused",
    clearance_min: float = 0.16,
    alpha: float = 0.5,
    beta: float = 0.5,
    bev_z_min: float = 0.05,
    bev_z_max: float = 1.2,
    bev_res: float = 0.05,
    bev_x_max: float = 4.0,
    bev_y_half: float = 2.0,
    fallback_v_scale: float = 0.3,
    fallback_clearance_eps: float = 0.02,
    clearance_horizon: float = 1.5,
    goal_y: Optional[float] = None,
) -> RerankResult:
    """对 16 条候选做 hard reject + soft fuse 重排。

    mode:
      - raw: 等价 critic argmax，不做 reject（便于单测；线上客户端可短路）
      - critic / clearance / fused: 先 clearance < clearance_min 硬拒绝，再按模式选
    全拒 fallback: 一律 debug['rotate']=True（不再降速爬最差轨，避免左右摆）；
    rotate_sign 由 BEV 空旷度 + goal 侧写入（+1 左/-1 右）。
    fallback_clearance_eps / fallback_v_scale 保留兼容，全拒时不再用于爬行分支。
    """
    mode = str(mode).strip().lower()
    if mode not in ("raw", "critic", "clearance", "fused"):
        raise ValueError(f"未知 safe mode: {mode}")

    trajs = _squeeze_trajs(all_traj)
    values = np.asarray(all_values, dtype=np.float64).reshape(-1)
    n = int(trajs.shape[0])
    if values.size != n:
        m = min(n, int(values.size))
        trajs = trajs[:m]
        values = values[:m]
        n = m
    if n < 1:
        raise ValueError("all_traj 为空")

    fused_scores = np.full((n,), -np.inf, dtype=np.float64)
    rejected_mask = np.zeros((n,), dtype=bool)
    debug: Dict[str, Any] = {
        "mode": mode,
        "fallback": False,
        "rotate": False,
        "n_reject": 0,
        "n_survivor": 0,
    }

    if mode == "raw":
        chosen_idx = int(np.argmax(values)) if n > 0 else 0
        clearances = np.zeros((n,), dtype=np.float64)
        fused_scores = values.copy()
        debug["chosen_clearance"] = 0.0
        debug["max_clearance"] = 0.0
        return RerankResult(
            traj_cam=np.asarray(trajs[chosen_idx]),
            chosen_idx=chosen_idx,
            clearances=clearances,
            fused_scores=fused_scores,
            rejected_mask=rejected_mask,
            v_max_scale=1.0,
            debug=debug,
        )

    bev = depth_to_bev_cost(
        depth_m,
        intrinsic,
        z_min=bev_z_min,
        z_max=bev_z_max,
        res=bev_res,
        x_max=bev_x_max,
        y_half=bev_y_half,
    )
    clearances = clearances_for_trajectories(
        trajs,
        bev,
        robot_geom,
        x_horizon=float(clearance_horizon),
    )
    rejected_mask = clearances < float(clearance_min)
    survivors = np.flatnonzero(~rejected_mask)
    debug["n_reject"] = int(rejected_mask.sum())
    debug["n_survivor"] = int(survivors.size)
    debug["max_clearance"] = float(np.max(clearances)) if n > 0 else 0.0

    if survivors.size == 0:
        # 全拒：只原地旋转探路，不再选「最不差」轨降速爬行（那是左右摆的主因之一）
        chosen_idx = int(np.argmax(clearances))
        _ = fallback_v_scale, fallback_clearance_eps  # 兼容旧 CLI/单测参数
        rotate_sign = preferred_rotate_sign(bev, goal_y=goal_y)
        fused_scores[chosen_idx] = float(clearances[chosen_idx])
        debug["fallback"] = True
        debug["rotate"] = True
        debug["rotate_sign"] = int(rotate_sign)
        debug["chosen_clearance"] = float(clearances[chosen_idx])
        return RerankResult(
            traj_cam=np.asarray(trajs[chosen_idx]),
            chosen_idx=chosen_idx,
            clearances=clearances,
            fused_scores=fused_scores,
            rejected_mask=rejected_mask,
            v_max_scale=0.0,
            debug=debug,
        )

    if mode == "critic":
        local = values[survivors]
        chosen_idx = int(survivors[int(np.argmax(local))])
        fused_scores[survivors] = values[survivors]
    elif mode == "clearance":
        local = clearances[survivors]
        chosen_idx = int(survivors[int(np.argmax(local))])
        fused_scores[survivors] = clearances[survivors]
    else:  # fused
        nc = _minmax_norm(values[survivors])
        ncl = _minmax_norm(clearances[survivors])
        scores = float(alpha) * nc + float(beta) * ncl
        fused_scores[survivors] = scores
        chosen_idx = int(survivors[int(np.argmax(scores))])

    debug["chosen_clearance"] = float(clearances[chosen_idx])
    return RerankResult(
        traj_cam=np.asarray(trajs[chosen_idx]),
        chosen_idx=chosen_idx,
        clearances=clearances,
        fused_scores=fused_scores,
        rejected_mask=rejected_mask,
        v_max_scale=1.0,
        debug=debug,
    )
