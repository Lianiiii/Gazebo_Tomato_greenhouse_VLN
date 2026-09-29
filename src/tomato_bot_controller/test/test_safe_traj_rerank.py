# 中文说明：Phase1 C1 BEV / 左右轮迹 clearance + Phase2 rerank 单测（无 ROS 依赖）。
# 合成 depth：前方墙、右侧柱；断言贴边折线 clearance < 外扩折线；覆盖 hard reject / fallback。

from __future__ import annotations

import time

import numpy as np
import pytest

from tomato_bot_controller.robot_geometry import RobotGeom
from tomato_bot_controller.safe_traj_rerank import (
    BevCost,
    clearances_for_trajectories,
    depth_to_bev_cost,
    preferred_rotate_sign,
    rerank_trajectories,
    trajectory_clearance,
)


def _intrinsic(width=640, height=480, fx=500.0, fy=500.0):
    cx, cy = width / 2.0, height / 2.0
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


def _paint_bev_points(depth, intrinsic, points_xyz):
    """把 BEV/水平系点 (X前, Y左, Z_up) 写入 depth（米）。无效处保持 0。"""
    K = intrinsic
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    h, w = depth.shape
    for X, Y, Z_up in points_xyz:
        z = float(X)
        if z <= 1e-3:
            continue
        x_cam = -float(Y)
        y_cam = -float(Z_up)
        u = int(round(fx * x_cam / z + cx))
        v = int(round(fy * y_cam / z + cy))
        if 0 <= u < w and 0 <= v < h:
            # 近点优先保留（更小深度）
            prev = depth[v, u]
            if prev <= 0.0 or z < prev:
                depth[v, u] = z


def _front_wall_depth(intrinsic, wall_x=1.0, y_half=1.5, z_up=0.4, step=0.02):
    h, w = 480, 640
    depth = np.zeros((h, w), dtype=np.float32)
    ys = np.arange(-y_half, y_half + 1e-6, step)
    pts = [(wall_x, float(y), z_up) for y in ys]
    # 稍微加厚，避免单像素漏检
    for dx in (0.0, 0.05, 0.10):
        _paint_bev_points(depth, intrinsic, [(wall_x + dx, y, z_up) for _, y, z_up in pts])
    return depth


def _right_pillar_depth(intrinsic, x0=0.8, x1=2.0, y_right=-0.45, z_up=0.35, step=0.03):
    """右侧柱：BEV 中 Y<0 为右。"""
    h, w = 480, 640
    depth = np.zeros((h, w), dtype=np.float32)
    xs = np.arange(x0, x1 + 1e-6, step)
    pts = []
    for x in xs:
        for dy in (0.0, -0.05, -0.10):
            pts.append((float(x), float(y_right + dy), z_up))
    _paint_bev_points(depth, intrinsic, pts)
    return depth


def _two_traj_right_pillar():
    xs = np.linspace(0.2, 2.2, 16)
    traj_edge = np.stack([xs, np.full_like(xs, -0.28)], axis=1)
    traj_out = np.stack([xs, np.full_like(xs, 0.25)], axis=1)
    trajs = np.stack([traj_edge, traj_out], axis=0)
    return trajs


def test_depth_zero_is_not_obstacle():
    K = _intrinsic()
    depth = np.zeros((480, 640), dtype=np.float32)
    bev = depth_to_bev_cost(depth, K, z_min=0.05, z_max=1.2, res=0.05, x_max=4.0, y_half=2.0)
    assert isinstance(bev, BevCost)
    assert bev.occ.sum() == 0
    assert float(bev.dist.min()) > 1.0  # 全空闲，距离应较大


def test_front_wall_occupancy_and_low_straight_clearance():
    K = _intrinsic()
    depth = _front_wall_depth(K, wall_x=1.0)
    bev = depth_to_bev_cost(depth, K, res=0.05, x_max=4.0, y_half=2.0)
    assert bev.occ.sum() > 10

    geom = RobotGeom()
    # 直行撞向墙
    traj = np.stack([np.linspace(0.1, 1.2, 12), np.zeros(12)], axis=1)
    c = trajectory_clearance(traj, bev, geom)
    assert c < 0.20


def test_right_pillar_edge_hugging_worse_than_outward():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    bev = depth_to_bev_cost(depth, K, res=0.05, x_max=4.0, y_half=2.0)
    assert bev.occ.sum() > 5

    geom = RobotGeom(inflate=0.05, wheel_separation=0.22)
    trajs = _two_traj_right_pillar()
    c_edge = trajectory_clearance(trajs[0], bev, geom)
    c_out = trajectory_clearance(trajs[1], bev, geom)
    assert c_edge < c_out, f"expected edge {c_edge} < outward {c_out}"


def test_batch_clearances_shape():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    bev = depth_to_bev_cost(depth, K)
    geom = RobotGeom()
    trajs = _two_traj_right_pillar()
    cs = clearances_for_trajectories(trajs, bev, geom)
    assert cs.shape == (2,)
    assert cs[0] < cs[1]


def test_single_frame_timing_budget():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    geom = RobotGeom()
    xs = np.linspace(0.2, 2.0, 24)
    trajs = np.stack(
        [np.stack([xs, np.full_like(xs, y)], axis=1) for y in np.linspace(-0.5, 0.5, 16)],
        axis=0,
    )

    t0 = time.perf_counter()
    bev = depth_to_bev_cost(depth, K, res=0.05, x_max=4.0, y_half=2.0)
    _ = clearances_for_trajectories(trajs, bev, geom)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # 宽松上限：CI/WSL 波动；frame 文档另记实测
    assert elapsed_ms < 200.0, f"too slow: {elapsed_ms:.1f} ms"
    print(f"phase1_single_frame_ms={elapsed_ms:.2f}")


def test_robot_geom_defaults_match_yaml_live():
    g = RobotGeom()
    assert g.base_x == pytest.approx(0.32)
    assert g.base_y == pytest.approx(0.18)
    assert g.wheel_separation == pytest.approx(0.22)
    assert g.camera_offset_xyz == (0.12, 0.0, 0.64)
    assert g.inflate == pytest.approx(0.05)


def test_rerank_raw_picks_critic_argmax():
    K = _intrinsic()
    depth = np.zeros((480, 640), dtype=np.float32)
    trajs = _two_traj_right_pillar()
    values = np.array([0.1, 0.9], dtype=np.float64)
    geom = RobotGeom()
    rr = rerank_trajectories(trajs, values, depth, K, geom, mode="raw")
    assert rr.chosen_idx == 1
    assert rr.v_max_scale == pytest.approx(1.0)
    assert not rr.debug.get("fallback")
    assert not rr.debug.get("rotate")


def test_rerank_hard_reject_mask_and_clearance_mode():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    trajs = _two_traj_right_pillar()
    # critic 故意偏爱贴边轨
    values = np.array([1.0, 0.1], dtype=np.float64)
    geom = RobotGeom(inflate=0.05, wheel_separation=0.22)
    rr = rerank_trajectories(
        trajs,
        values,
        depth,
        K,
        geom,
        mode="clearance",
        clearance_min=0.16,
    )
    assert rr.rejected_mask.shape == (2,)
    # 贴边应更易被拒或至少 clearance 更低；clearance mode 应选外扩
    assert rr.chosen_idx == 1
    assert rr.clearances[0] < rr.clearances[1]


def test_rerank_fused_can_override_bad_critic():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    trajs = _two_traj_right_pillar()
    values = np.array([0.55, 0.45], dtype=np.float64)  # critic 略偏贴边
    geom = RobotGeom(inflate=0.05, wheel_separation=0.22)
    rr = rerank_trajectories(
        trajs,
        values,
        depth,
        K,
        geom,
        mode="fused",
        clearance_min=0.05,  # 放宽，让两轨都存活，靠 soft fuse
        alpha=0.3,
        beta=0.7,
    )
    assert rr.chosen_idx == 1
    assert rr.v_max_scale == pytest.approx(1.0)


def test_rerank_all_reject_fallback_and_rotate():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    trajs = _two_traj_right_pillar()
    values = np.array([0.9, 0.1], dtype=np.float64)
    geom = RobotGeom(inflate=0.05, wheel_separation=0.22)

    # 全拒一律 rotate（不再降速爬行），v_scale=0
    rr = rerank_trajectories(
        trajs,
        values,
        depth,
        K,
        geom,
        mode="fused",
        clearance_min=10.0,  # 抬高阈值，强制全拒
        fallback_v_scale=0.3,
        fallback_clearance_eps=0.02,
    )
    assert bool(rr.debug.get("fallback"))
    assert bool(rr.debug.get("rotate"))
    assert int(rr.debug.get("n_reject", 0)) == 2
    assert int(rr.debug.get("n_survivor", -1)) == 0
    assert rr.chosen_idx == int(np.argmax(rr.clearances))
    assert rr.v_max_scale == pytest.approx(0.0)
    # 右侧柱 → 左侧更空旷 → +1（左转）
    assert int(rr.debug.get("rotate_sign", 0)) == 1

    # goal_y 在左右空旷接近时偏向目标侧
    rr_goal = rerank_trajectories(
        trajs,
        values,
        depth,
        K,
        geom,
        mode="clearance",
        clearance_min=10.0,
        goal_y=-0.5,
    )
    assert bool(rr_goal.debug.get("rotate"))
    assert int(rr_goal.debug.get("rotate_sign", 0)) in (-1, 1)


def test_preferred_rotate_sign_avoids_occupied_side():
    K = _intrinsic()
    depth_right = _right_pillar_depth(K)
    bev_right = depth_to_bev_cost(depth_right, K, res=0.05, x_max=4.0, y_half=2.0)
    assert preferred_rotate_sign(bev_right) == 1

    # 左侧柱：镜像到 Y>0
    h, w = 480, 640
    depth_left = np.zeros((h, w), dtype=np.float32)
    xs = np.arange(0.8, 2.0 + 1e-6, 0.03)
    pts = []
    for x in xs:
        for dy in (0.0, 0.05, 0.10):
            pts.append((float(x), float(0.45 + dy), 0.35))
    _paint_bev_points(depth_left, K, pts)
    bev_left = depth_to_bev_cost(depth_left, K, res=0.05, x_max=4.0, y_half=2.0)
    assert preferred_rotate_sign(bev_left) == -1


def test_rerank_accepts_batched_shape_and_unknown_mode():
    K = _intrinsic()
    depth = _right_pillar_depth(K)
    trajs = _two_traj_right_pillar()[None, ...]  # (1,N,T,2)
    values = np.array([0.2, 0.8], dtype=np.float64)
    geom = RobotGeom()
    rr = rerank_trajectories(trajs, values, depth, K, geom, mode="critic", clearance_min=0.01)
    assert rr.traj_cam.ndim == 2
    with pytest.raises(ValueError):
        rerank_trajectories(trajs, values, depth, K, geom, mode="nope")


def test_clearance_horizon_ignores_far_obstacle():
    """近场干净、远端撞障：全时域会拒，horizon 截断后应存活。"""
    K = _intrinsic()
    # 墙在 2.5m，超出默认 horizon 1.5m
    depth = _front_wall_depth(K, wall_x=2.5)
    bev = depth_to_bev_cost(depth, K, res=0.05, x_max=4.0, y_half=2.0)
    geom = RobotGeom(inflate=0.05, wheel_separation=0.22)
    traj = np.stack([np.linspace(0.1, 3.0, 20), np.zeros(20)], axis=1)
    c_full = trajectory_clearance(traj, bev, geom, x_horizon=4.0)
    c_near = trajectory_clearance(traj, bev, geom, x_horizon=1.5)
    assert c_full < 0.20
    assert c_near > c_full
    assert c_near >= 0.16


def test_preferred_rotate_sign_goal_bias_when_sides_close():
    K = _intrinsic()
    # 空场景：左右分数接近，goal_y 决定方向
    depth = np.zeros((480, 640), dtype=np.float32)
    bev = depth_to_bev_cost(depth, K, res=0.05, x_max=4.0, y_half=2.0)
    assert preferred_rotate_sign(bev, goal_y=0.5, free_margin=0.5) == 1
    assert preferred_rotate_sign(bev, goal_y=-0.5, free_margin=0.5) == -1
