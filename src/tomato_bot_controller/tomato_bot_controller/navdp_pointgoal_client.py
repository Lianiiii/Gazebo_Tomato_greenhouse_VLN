# 中文说明：NavDP PointGoal ROS2 客户端。
# 从 TomatoBot 取 RGB-D 与里程计，调用 NavDP server 的 /pointgoal_step，
# 再用官方风格 MPC 跟踪返回轨迹，发布差速速度指令。
# Phase2：可选 C1 安全重排（--safe_mode），用客户端 raw depth 对 16 条候选
# 做左右轮迹 clearance 硬拒绝 + soft fuse，替换盲选 top-1。
# Phase2 debug：全拒时粘滞同向旋转（BEV 空旷度 + goal 侧定符号），
# 有 survivor 立刻解除 sticky 跟轨前进，避免来回摆/转过头。
#
# ROS 接口：
#   订阅 /camera/image_raw (sensor_msgs/Image)  【兼容别名 /camera/color/image_raw】
#   订阅 /camera/depth/image_raw (sensor_msgs/Image)
#   订阅 /camera/camera_info (sensor_msgs/CameraInfo，可选)
#   订阅 /odom (nav_msgs/Odometry)
#   发布 /cmd_vel (geometry_msgs/Twist)
# HTTP：
#   POST localhost:{port}/navigator_reset
#   POST localhost:{port}/pointgoal_step

import argparse
import csv
import math
import os
import sys
import threading
import time

import message_filters
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image

from tomato_bot_controller.mpc_controller import MPC_Controller
from tomato_bot_controller.robot_geometry import RobotGeom
from tomato_bot_controller.safe_traj_rerank import rerank_trajectories


# xacro 中 camera_link 相对 base_link 的固定外参（米）
CAMERA_OFFSET_X = 0.12
CAMERA_OFFSET_Y = 0.0
# camera_height(0.70) - wheel_radius(0.06)
CAMERA_OFFSET_Z = 0.64
DEFAULT_HFORD = 1.3962634
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480


def quat_to_yaw(qx, qy, qz, qw):
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def yaw_to_rot2d(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def world_goal_to_robot(goal_x, goal_y, robot_x, robot_y, robot_yaw):
    dx = goal_x - robot_x
    dy = goal_y - robot_y
    c, s = math.cos(robot_yaw), math.sin(robot_yaw)
    rel_x = c * dx + s * dy
    rel_y = -s * dx + c * dy
    return np.array([rel_x, rel_y], dtype=np.float64)


def intrinsic_from_fov(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, hfov=DEFAULT_HFORD):
    fx = width / (2.0 * math.tan(hfov / 2.0))
    fy = fx
    cx = width / 2.0
    cy = height / 2.0
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


def camera_pose_from_base(base_x, base_y, base_yaw):
    """用 base_link odom + 固定外参近似相机水平位姿。"""
    c, s = math.cos(base_yaw), math.sin(base_yaw)
    cam_x = base_x + c * CAMERA_OFFSET_X - s * CAMERA_OFFSET_Y
    cam_y = base_y + s * CAMERA_OFFSET_X + c * CAMERA_OFFSET_Y
    return cam_x, cam_y, base_yaw


def transform_traj_camera_to_world(traj_camera, cam_x, cam_y, cam_yaw):
    """traj_camera: (N, >=2) 相机系点 -> (N, 2) 世界/odom 系。"""
    rot = yaw_to_rot2d(cam_yaw)
    pts = []
    for p in traj_camera:
        local = np.array([float(p[0]), float(p[1])], dtype=np.float64)
        world = rot @ local + np.array([cam_x, cam_y], dtype=np.float64)
        pts.append(world)
    return np.asarray(pts, dtype=np.float64)


class NavDPPointGoalClient(Node):
    """PointGoal 导航客户端：观测 -> NavDP -> MPC -> /cmd_vel。"""

    def __init__(self, args):
        super().__init__('navdp_pointgoal_client')
        self.bridge = CvBridge()
        self.port = int(args.port)
        self.speed = float(args.speed)
        self.stop_threshold = float(args.stop_threshold)
        self.arrive_dist = float(args.arrive_dist)
        self.goal_x = float(args.goal_x)
        self.goal_y = float(args.goal_y)

        navdp_root = os.path.expanduser(args.navdp_root)
        if navdp_root not in sys.path:
            sys.path.insert(0, navdp_root)
        try:
            from utils_tasks.client_utils import navigator_reset, pointgoal_step
        except ImportError as exc:
            raise RuntimeError(
                f'无法从 {navdp_root} 导入 utils_tasks.client_utils: {exc}'
            ) from exc
        self._navigator_reset = navigator_reset
        self._pointgoal_step = pointgoal_step

        self._data_lock = threading.Lock()
        self._mpc_lock = threading.Lock()
        self.latest_rgb = None  # RGB HxWx3 uint8
        self.latest_depth = None  # HxW float meters
        self.pose = None  # (x, y, yaw)
        self.camera_info = None
        self.intrinsic = None
        self.mpc = None
        self.arrived = False
        self.is_running = True
        self._server_ready = False
        self._last_reset_error_t = 0.0
        self._last_cmd = Twist()  # 最近一次有效速度，用于平滑续发
        self._has_cmd = False
        self._navigating = False  # 仅在真正开始导航后才占用 /cmd_vel
        self._last_baseline_log_t = 0.0
        self._last_safe_log_t = 0.0
        self._override_cmd = None  # Phase2 fallback 原地旋转时覆盖 MPC
        # 粘滞旋转：无 survivor 时锁定同向；有 survivor 立刻解除跟轨，避免来回摆/转过头
        self._rotate_sticky = False
        self._rotate_sign = 1
        self.safe_mode = str(getattr(args, 'safe_mode', 'raw') or 'raw').strip().lower()
        self.clearance_min = float(getattr(args, 'clearance_min', 0.16))
        self.alpha = float(getattr(args, 'alpha', 0.5))
        self.beta = float(getattr(args, 'beta', 0.5))
        self.bev_z_min = float(getattr(args, 'bev_z_min', 0.05))
        self.bev_z_max = float(getattr(args, 'bev_z_max', 1.2))
        self.bev_res = float(getattr(args, 'bev_res', 0.05))
        self.bev_x_max = float(getattr(args, 'bev_x_max', 4.0))
        self.bev_y_half = float(getattr(args, 'bev_y_half', 2.0))
        self.fallback_v_scale = float(getattr(args, 'fallback_v_scale', 0.3))
        self.fallback_clearance_eps = float(getattr(args, 'fallback_clearance_eps', 0.02))
        self.fallback_w = float(getattr(args, 'fallback_w', 0.4))
        self.clearance_horizon = float(getattr(args, 'clearance_horizon', 1.5))
        self._robot_geom = RobotGeom.from_defaults(
            base_x=float(getattr(args, 'robot_base_x', 0.32)),
            base_y=float(getattr(args, 'robot_base_y', 0.18)),
            wheel_separation=float(getattr(args, 'wheel_separation', 0.22)),
            inflate=float(getattr(args, 'inflate', 0.05)),
            camera_offset_xyz=(CAMERA_OFFSET_X, CAMERA_OFFSET_Y, CAMERA_OFFSET_Z),
        )
        self._baseline_csv_path = str(getattr(args, 'baseline_csv', '') or '').strip()
        self._baseline_csv_lock = threading.Lock()
        if self._baseline_csv_path:
            csv_dir = os.path.dirname(os.path.abspath(self._baseline_csv_path))
            if csv_dir:
                os.makedirs(csv_dir, exist_ok=True)
            write_header = not os.path.exists(self._baseline_csv_path) or (
                os.path.getsize(self._baseline_csv_path) == 0
            )
            with open(self._baseline_csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(
                        [
                            't',
                            'latency',
                            'critic_argmax',
                            'all_traj_shape',
                            'all_values_shape',
                            'max_critic',
                            'dist',
                        ]
                    )

        self.rgb_topic = args.rgb_topic
        self.depth_topic = args.depth_topic
        self.camera_info_topic = args.camera_info_topic

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Odometry, '/odom', self._odom_cb, 10)
        self.create_subscription(CameraInfo, self.camera_info_topic, self._info_cb, 10)

        self.rgb_sub = message_filters.Subscriber(self, Image, self.rgb_topic)
        self.depth_sub = message_filters.Subscriber(self, Image, self.depth_topic)
        self.ts = message_filters.ApproximateTimeSynchronizer(
            [self.rgb_sub, self.depth_sub], queue_size=10, slop=0.1
        )
        self.ts.registerCallback(self._image_cb)

        self.get_logger().info(
            f'PointGoal client 启动: goal=({self.goal_x:.2f}, {self.goal_y:.2f}), '
            f'port={self.port}, speed={self.speed}, arrive={self.arrive_dist}'
        )
        self.get_logger().info(
            f'话题: rgb={self.rgb_topic}, depth={self.depth_topic}, info={self.camera_info_topic}'
        )
        self.get_logger().info(
            f'C1 safe_mode={self.safe_mode}, clearance_min={self.clearance_min:.3f}, '
            f'alpha={self.alpha:.2f}, beta={self.beta:.2f}, inflate={self._robot_geom.inflate:.3f}'
        )
        self.get_logger().info(
            '等待 RGB-D / odom / camera_info ...（未开始导航前不发布 /cmd_vel，避免抢占键盘）'
        )
        if self._baseline_csv_path:
            self.get_logger().info(f'Phase0 基线 CSV: {self._baseline_csv_path}')
        else:
            self.get_logger().info('Phase0 基线 CSV 未启用（可用 --baseline_csv PATH）')

        self._init_timer = self.create_timer(0.5, self._try_init_server)
        self.plan_thread = threading.Thread(target=self._planning_loop, daemon=True)
        self.plan_thread.start()
        # MPC.solve 放到独立线程，避免卡住 ROS executor 导致图像/里程计卡顿
        self.control_thread = threading.Thread(target=self._control_worker, daemon=True)
        self.control_thread.start()
        # 10Hz 只续发最近速度指令，保证 /cmd_vel 连续
        self.control_timer = self.create_timer(0.1, self._control_publish)

    def _info_cb(self, msg: CameraInfo):
        if self.camera_info is None:
            self.camera_info = msg
            k = np.array(msg.k, dtype=np.float64).reshape(3, 3)
            self.intrinsic = k
            self.get_logger().info(f'收到 camera_info, fx={k[0, 0]:.1f}, fy={k[1, 1]:.1f}')

    def _odom_cb(self, msg: Odometry):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        yaw = quat_to_yaw(q.x, q.y, q.z, q.w)
        with self._data_lock:
            self.pose = (x, y, yaw)

    def _image_cb(self, rgb_msg: Image, depth_msg: Image):
        try:
            bgr = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding='bgr8')
            rgb = bgr[:, :, ::-1].copy()

            if depth_msg.encoding in ('32FC1', '32FC'):
                depth = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding='32FC1')
                depth = np.asarray(depth, dtype=np.float32)
            elif depth_msg.encoding in ('16UC1', 'mono16'):
                depth_raw = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding='16UC1')
                depth = np.asarray(depth_raw, dtype=np.float32) / 1000.0
            else:
                depth = self.bridge.imgmsg_to_cv2(depth_msg, desired_encoding='passthrough')
                depth = np.asarray(depth, dtype=np.float32)
                if depth_msg.encoding.lower().startswith('16'):
                    depth = depth / 1000.0

            depth = np.nan_to_num(depth, nan=0.0, posinf=0.0, neginf=0.0)
            depth = np.clip(depth, 0.0, 10.0)

            with self._data_lock:
                self.latest_rgb = rgb
                self.latest_depth = depth
        except Exception as exc:
            self.get_logger().error(f'图像转换失败: {exc}')

    def _try_init_server(self):
        if self._server_ready:
            return
        if self.intrinsic is None:
            # 等一会儿 camera_info；超时则用 FOV 推算
            if self.camera_info is None and self.latest_rgb is not None:
                self.intrinsic = intrinsic_from_fov()
                self.get_logger().warn('未收到 camera_info，使用 FOV 推算内参')
            else:
                return
        if self.pose is None or self.latest_rgb is None or self.latest_depth is None:
            return

        try:
            algo = self._navigator_reset(
                self.intrinsic,
                stop_threshold=self.stop_threshold,
                batch_size=1,
                port=self.port,
            )
            self._server_ready = True
            self._init_timer.cancel()
            self.get_logger().info(f'NavDP reset 成功, algo={algo}')
        except Exception as exc:
            now = time.time()
            if now - self._last_reset_error_t > 5.0:
                self._last_reset_error_t = now
                self.get_logger().error(
                    f'连接 NavDP server 失败(port={self.port}): {exc}；请确认 server 已启动'
                )

    def _planning_loop(self):
        while self.is_running and rclpy.ok():
            if not self._server_ready or self.arrived:
                time.sleep(0.05)
                continue

            with self._data_lock:
                if self.latest_rgb is None or self.latest_depth is None or self.pose is None:
                    time.sleep(0.05)
                    continue
                rgb = self.latest_rgb.copy()
                depth = self.latest_depth.copy()
                base_x, base_y, base_yaw = self.pose

            rel_goal = world_goal_to_robot(self.goal_x, self.goal_y, base_x, base_y, base_yaw)
            dist = float(np.linalg.norm(rel_goal))
            if dist < self.arrive_dist:
                if not self.arrived:
                    self.arrived = True
                    self.get_logger().info(
                        f'到达目标附近, pose=({base_x:.2f},{base_y:.2f}) '
                        f'goal=({self.goal_x:.2f},{self.goal_y:.2f}) '
                        f'dist={dist:.3f}m < {self.arrive_dist}'
                    )
                    self._publish_stop()
                continue

            cam_x, cam_y, cam_yaw = camera_pose_from_base(base_x, base_y, base_yaw)
            goal_batch = rel_goal.reshape(1, 2)
            rgb_batch = rgb[None, ...]
            depth_batch = depth[None, ...]

            try:
                t0 = time.time()
                result = self._pointgoal_step(goal_batch, rgb_batch, depth_batch, port=self.port)
                # 兼容 3/4 元组：只用前三项；控制仍取 top-1
                traj_cam = result[0]
                all_traj = np.asarray(result[1])
                all_values = np.asarray(result[2]).reshape(-1)
                latency = time.time() - t0

                if all_traj.ndim == 4:
                    all_traj = all_traj[0]
                critic_argmax = int(np.argmax(all_values)) if all_values.size > 0 else -1
                max_critic = float(all_values[critic_argmax]) if critic_argmax >= 0 else float('nan')
                now = time.time()
                if now - self._last_baseline_log_t >= 1.0:
                    self._last_baseline_log_t = now
                    self.get_logger().info(
                        f'Phase0 all_* shapes: all_traj={tuple(all_traj.shape)} '
                        f'all_values={tuple(all_values.shape)} '
                        f'critic_argmax={critic_argmax} max_critic={max_critic:.3f} '
                        f'latency={latency:.3f}s'
                    )
                if self._baseline_csv_path:
                    with self._baseline_csv_lock:
                        with open(self._baseline_csv_path, 'a', newline='', encoding='utf-8') as f:
                            csv.writer(f).writerow(
                                [
                                    f'{now:.3f}',
                                    f'{latency:.4f}',
                                    critic_argmax,
                                    str(tuple(all_traj.shape)),
                                    str(tuple(all_values.shape)),
                                    f'{max_critic:.6f}',
                                    f'{dist:.4f}',
                                ]
                            )

                if traj_cam is None or len(traj_cam) == 0:
                    self.get_logger().warn('NavDP 返回空轨迹')
                    time.sleep(0.1)
                    continue

                # batch 维: (1, T, 2+) 或 (T, 2+)；raw 保持 Phase0 top-1
                traj = np.asarray(traj_cam)
                if traj.ndim == 3:
                    traj = traj[0]
                v_scale = 1.0
                chosen_idx = critic_argmax
                chosen_clearance = float('nan')
                n_reject = 0
                fallback = False

                if self.safe_mode != 'raw':
                    if self.intrinsic is None:
                        self.get_logger().warn('无 intrinsic，跳过 C1 重排，沿用 top-1')
                    else:
                        rr = rerank_trajectories(
                            all_traj,
                            all_values,
                            depth,
                            self.intrinsic,
                            self._robot_geom,
                            mode=self.safe_mode,
                            clearance_min=self.clearance_min,
                            alpha=self.alpha,
                            beta=self.beta,
                            bev_z_min=self.bev_z_min,
                            bev_z_max=self.bev_z_max,
                            bev_res=self.bev_res,
                            bev_x_max=self.bev_x_max,
                            bev_y_half=self.bev_y_half,
                            fallback_v_scale=self.fallback_v_scale,
                            fallback_clearance_eps=self.fallback_clearance_eps,
                            clearance_horizon=self.clearance_horizon,
                            goal_y=float(rel_goal[1]),
                        )
                        chosen_idx = int(rr.chosen_idx)
                        chosen_clearance = float(rr.debug.get('chosen_clearance', float('nan')))
                        n_reject = int(rr.debug.get('n_reject', 0))
                        n_survivor = int(rr.debug.get('n_survivor', 0))
                        fallback = bool(rr.debug.get('fallback', False))
                        v_scale = float(rr.v_max_scale)
                        want_rotate = bool(rr.debug.get('rotate', False))
                        suggest_sign = int(rr.debug.get('rotate_sign', 1))
                        if suggest_sign == 0:
                            suggest_sign = 1

                        # 有 survivor：立刻解除 sticky，跟可走轨前进（不要转过头）。
                        # 无 survivor：锁定同向原地转，直到 server 给出可走候选。
                        if n_survivor > 0 and not want_rotate:
                            self._rotate_sticky = False
                        elif want_rotate or n_survivor == 0:
                            if not self._rotate_sticky:
                                self._rotate_sticky = True
                                self._rotate_sign = 1 if suggest_sign >= 0 else -1
                            w_cmd = float(self.fallback_w) * float(self._rotate_sign)
                            twist = Twist()
                            twist.linear.x = 0.0
                            twist.angular.z = w_cmd
                            with self._mpc_lock:
                                self.mpc = None
                                self._override_cmd = twist
                                self._last_cmd = twist
                                self._has_cmd = True
                            self._navigating = True
                            if now - self._last_safe_log_t >= 1.0:
                                self._last_safe_log_t = now
                                self.get_logger().warn(
                                    f'C1 fallback rotate: mode={self.safe_mode} '
                                    f'chosen={chosen_idx} critic_argmax={critic_argmax} '
                                    f'n_reject={n_reject} n_survivor={n_survivor} '
                                    f'clearance={chosen_clearance:.3f} '
                                    f'w={w_cmd:.2f} sign={self._rotate_sign} sticky=1'
                                )
                            time.sleep(0.05)
                            continue

                        traj = np.asarray(rr.traj_cam)
                        if traj.ndim == 3:
                            traj = traj[0]

                if traj.shape[0] < 2:
                    self.get_logger().warn(f'轨迹点过少: {traj.shape}')
                    time.sleep(0.1)
                    continue

                traj_world = transform_traj_camera_to_world(traj, cam_x, cam_y, cam_yaw)
                v_cap = max(0.05, float(self.speed) * float(max(v_scale, 0.0)))
                # 正常/全拒降速：仅构造 MPC 时注入一次 v_max
                mpc = MPC_Controller(
                    traj_world,
                    desired_v=v_cap,
                    v_max=v_cap,
                    w_max=self.speed,
                )
                with self._mpc_lock:
                    self.mpc = mpc
                    self._override_cmd = None
                self._navigating = True

                if now - self._last_safe_log_t >= 1.0:
                    self._last_safe_log_t = now
                    self.get_logger().info(
                        f'规划完成 latency={latency:.3f}s '
                        f'pose=({base_x:.2f},{base_y:.2f}) '
                        f'rel_goal=({rel_goal[0]:.2f},{rel_goal[1]:.2f}) '
                        f'dist={dist:.2f} traj_n={traj_world.shape[0]} '
                        f'mode={self.safe_mode} chosen={chosen_idx} '
                        f'critic_argmax={critic_argmax} n_reject={n_reject} '
                        f'clearance={chosen_clearance:.3f} v_scale={v_scale:.2f} '
                        f'fallback={fallback}'
                    )
            except Exception as exc:
                self.get_logger().error(f'pointgoal 推理失败: {exc}')
                time.sleep(0.5)
                continue

            # 规划本身耗时已提供节奏；额外短睡降低 CPU
            time.sleep(0.05)

    def _control_worker(self):
        """独立线程求解 MPC；结果写入 _last_cmd，由定时器平滑续发。"""
        while self.is_running and rclpy.ok():
            if self.arrived:
                if self._navigating:
                    self._publish_stop()
                    self._navigating = False
                time.sleep(0.05)
                continue

            if not self._server_ready or not self._navigating:
                time.sleep(0.05)
                continue

            with self._data_lock:
                pose = self.pose
            if pose is None:
                time.sleep(0.05)
                continue

            base_x, base_y, base_yaw = pose
            dist = float(np.linalg.norm(
                world_goal_to_robot(self.goal_x, self.goal_y, base_x, base_y, base_yaw)
            ))
            if dist < self.arrive_dist:
                self.arrived = True
                self.get_logger().info(
                    f'控制环判定到达，停车: pose=({base_x:.2f},{base_y:.2f}) '
                    f'goal=({self.goal_x:.2f},{self.goal_y:.2f}) dist={dist:.3f}m'
                )
                self._publish_stop()
                self._navigating = False
                continue

            # Phase2 fallback 原地旋转：优先覆盖，不求解前进 MPC
            with self._mpc_lock:
                override = self._override_cmd
                if override is not None:
                    self._last_cmd = override
                    self._has_cmd = True
            if override is not None:
                time.sleep(0.05)
                continue

            cam_x, cam_y, cam_yaw = camera_pose_from_base(base_x, base_y, base_yaw)
            with self._mpc_lock:
                mpc = self.mpc
            if mpc is None:
                time.sleep(0.05)
                continue

            try:
                opt_u, _ = mpc.solve(np.array([cam_x, cam_y, cam_yaw], dtype=np.float64))
                # 与官方一致取第 2 步控制量
                v = float(opt_u[1, 0])
                w = float(opt_u[1, 1])
                twist = Twist()
                twist.linear.x = max(0.0, min(self.speed, v))
                twist.angular.z = max(-self.speed, min(self.speed, w))
                with self._mpc_lock:
                    self._last_cmd = twist
                    self._has_cmd = True
            except Exception as exc:
                self.get_logger().warn(f'MPC 求解失败，续发上一拍速度: {exc}')

            time.sleep(0.05)

    def _control_publish(self):
        """10Hz 发布最近速度；未开始导航时不碰 /cmd_vel。"""
        if self.arrived:
            return
        if not self._navigating:
            return
        with self._mpc_lock:
            if not self._has_cmd:
                return
            twist = self._last_cmd
        self.cmd_pub.publish(twist)

    def _publish_stop(self):
        stop = Twist()
        with self._mpc_lock:
            self._last_cmd = stop
            self._has_cmd = False
            self._override_cmd = None
        self._rotate_sticky = False
        self.cmd_pub.publish(stop)

    def destroy_node(self):
        self.is_running = False
        if self._navigating or self.arrived:
            self._publish_stop()
        super().destroy_node()


def build_arg_parser():
    parser = argparse.ArgumentParser(description='NavDP PointGoal ROS2 client for TomatoBot')
    parser.add_argument('--goal_x', type=float, required=True, help='目标点世界/odom 系 X')
    parser.add_argument('--goal_y', type=float, required=True, help='目标点世界/odom 系 Y')
    parser.add_argument('--port', type=int, default=8888, help='NavDP server 端口')
    parser.add_argument('--speed', type=float, default=0.5, help='MPC 期望/最大速度')
    parser.add_argument('--stop_threshold', type=float, default=-3.0, help='传给 NavDP reset')
    parser.add_argument('--arrive_dist', type=float, default=0.3, help='到达判定距离(m)')
    parser.add_argument(
        '--navdp_root',
        type=str,
        default=os.path.expanduser('~/NavDP'),
        help='NavDP 仓库根目录，用于导入 utils_tasks.client_utils',
    )
    parser.add_argument(
        '--rgb_topic',
        type=str,
        default='/camera/image_raw',
        help='RGB 图像话题（当前仿真为 /camera/image_raw）',
    )
    parser.add_argument(
        '--depth_topic',
        type=str,
        default='/camera/depth/image_raw',
        help='Depth 图像话题',
    )
    parser.add_argument(
        '--camera_info_topic',
        type=str,
        default='/camera/camera_info',
        help='CameraInfo 话题',
    )
    parser.add_argument(
        '--baseline_csv',
        type=str,
        default='',
        help='Phase0 可选：把 all_* 基线日志追加写入该 CSV 路径；空则不写',
    )
    # Phase2 C1：默认硬编码对齐 config/safe_nav_defaults.yaml 现值（运行时不读 yaml）
    parser.add_argument(
        '--safe_mode',
        type=str,
        default='raw',
        choices=['raw', 'critic', 'clearance', 'fused'],
        help='C1 重排模式；raw=Phase0 top-1 回归',
    )
    parser.add_argument('--clearance_min', type=float, default=0.16, help='轮迹 clearance 硬拒绝阈值(m)')
    parser.add_argument('--inflate', type=float, default=0.05, help='足迹外扩安全裕度(m)')
    parser.add_argument('--alpha', type=float, default=0.5, help='fused 中 critic 权重')
    parser.add_argument('--beta', type=float, default=0.5, help='fused 中 clearance 权重')
    parser.add_argument('--bev_z_min', type=float, default=0.05, help='BEV 高度带下限(m)')
    parser.add_argument('--bev_z_max', type=float, default=1.2, help='BEV 高度带上限(m)')
    parser.add_argument('--bev_res', type=float, default=0.05, help='BEV 分辨率(m)')
    parser.add_argument('--bev_x_max', type=float, default=4.0, help='BEV 前方窗口(m)')
    parser.add_argument('--bev_y_half', type=float, default=2.0, help='BEV 侧向半宽(m)')
    parser.add_argument('--robot_base_x', type=float, default=0.32, help='车体长度(m)')
    parser.add_argument('--robot_base_y', type=float, default=0.18, help='车体宽度(m)')
    parser.add_argument('--wheel_separation', type=float, default=0.22, help='轮距(m)')
    parser.add_argument('--clearance_horizon', type=float, default=1.5, help='clearance 近场评估距离(m)，远端不参与 hard reject')
    parser.add_argument(
        '--fallback_v_scale',
        type=float,
        default=0.3,
        help='全拒 fallback 时强制降速比例',
    )
    parser.add_argument(
        '--fallback_clearance_eps',
        type=float,
        default=0.02,
        help='全拒后 clearance 仍低于该值则原地旋转',
    )
    parser.add_argument(
        '--fallback_w',
        type=float,
        default=0.4,
        help='fallback 原地旋转角速度(rad/s)',
    )
    return parser


def main(args=None):
    # 允许 ros2 run ... -- --goal_x 1.0 --goal_y 2.0
    parser = build_arg_parser()
    cli_args, ros_args = parser.parse_known_args(args=args)

    rclpy.init(args=ros_args)
    node = NavDPPointGoalClient(cli_args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.is_running = False
        # destroy_node 内会按需停车，避免未导航时误发零速抢占键盘
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
