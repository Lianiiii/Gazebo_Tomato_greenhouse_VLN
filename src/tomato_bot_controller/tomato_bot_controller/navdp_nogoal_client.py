# 中文说明：NavDP NoGoal ROS2 客户端。
# 从 TomatoBot 取 RGB-D 与里程计，不提供任何具体目标，调用 NavDP server 的 /nogoal_step，
# 再用官方风格 MPC 跟踪返回轨迹，发布差速速度指令，实现无目标探索/行进。
#
# ROS 接口：
#   订阅 /camera/image_raw (sensor_msgs/Image)  【兼容别名 /camera/color/image_raw】
#   订阅 /camera/depth/image_raw (sensor_msgs/Image)
#   订阅 /camera/camera_info (sensor_msgs/CameraInfo，可选)
#   订阅 /odom (nav_msgs/Odometry)
#   发布 /cmd_vel (geometry_msgs/Twist)
# HTTP：
#   POST localhost:{port}/navigator_reset
#   POST localhost:{port}/nogoal_step

import argparse
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


class NavDPNoGoalClient(Node):
    """NoGoal 探索客户端：观测 -> NavDP /nogoal_step -> MPC -> /cmd_vel。"""

    def __init__(self, args):
        super().__init__('navdp_nogoal_client')
        self.bridge = CvBridge()
        self.port = int(args.port)
        self.speed = float(args.speed)
        self.stop_threshold = float(args.stop_threshold)

        navdp_root = os.path.expanduser(args.navdp_root)
        if navdp_root not in sys.path:
            sys.path.insert(0, navdp_root)
        try:
            from utils_tasks.client_utils import navigator_reset, nogoal_step
        except ImportError as exc:
            raise RuntimeError(
                f'无法从 {navdp_root} 导入 utils_tasks.client_utils: {exc}'
            ) from exc
        self._navigator_reset = navigator_reset
        self._nogoal_step = nogoal_step

        self._data_lock = threading.Lock()
        self._mpc_lock = threading.Lock()
        self.latest_rgb = None  # RGB HxWx3 uint8
        self.latest_depth = None  # HxW float meters
        self.pose = None  # (x, y, yaw)
        self.camera_info = None
        self.intrinsic = None
        self.mpc = None
        self.is_running = True
        self._server_ready = False
        self._last_reset_error_t = 0.0
        self._last_cmd = Twist()  # 最近一次有效速度，用于平滑续发
        self._has_cmd = False
        self._navigating = False  # 仅在真正开始导航后才占用 /cmd_vel

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
            f'NoGoal client 启动: port={self.port}, speed={self.speed} '
            f'(无目标探索模式，Ctrl+C 停止)'
        )
        self.get_logger().info(
            f'话题: rgb={self.rgb_topic}, depth={self.depth_topic}, info={self.camera_info_topic}'
        )
        self.get_logger().info(
            '等待 RGB-D / odom / camera_info ...（未开始导航前不发布 /cmd_vel，避免抢占键盘）'
        )

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
            if not self._server_ready:
                time.sleep(0.05)
                continue

            with self._data_lock:
                if self.latest_rgb is None or self.latest_depth is None or self.pose is None:
                    time.sleep(0.05)
                    continue
                rgb = self.latest_rgb.copy()
                depth = self.latest_depth.copy()
                base_x, base_y, base_yaw = self.pose

            cam_x, cam_y, cam_yaw = camera_pose_from_base(base_x, base_y, base_yaw)
            rgb_batch = rgb[None, ...]
            depth_batch = depth[None, ...]

            try:
                t0 = time.time()
                traj_cam, _all_traj, all_values = self._nogoal_step(
                    rgb_batch, depth_batch, port=self.port
                )
                latency = time.time() - t0

                if traj_cam is None or len(traj_cam) == 0:
                    self.get_logger().warn('NavDP 返回空轨迹')
                    time.sleep(0.1)
                    continue

                # batch 维: (1, T, 2+) 或 (T, 2+)
                traj = np.asarray(traj_cam)
                if traj.ndim == 3:
                    traj = traj[0]
                if traj.shape[0] < 2:
                    self.get_logger().warn(f'轨迹点过少: {traj.shape}')
                    time.sleep(0.1)
                    continue

                traj_world = transform_traj_camera_to_world(traj, cam_x, cam_y, cam_yaw)
                mpc = MPC_Controller(
                    traj_world,
                    desired_v=self.speed,
                    v_max=self.speed,
                    w_max=self.speed,
                )
                with self._mpc_lock:
                    self.mpc = mpc
                self._navigating = True

                values = np.asarray(all_values)
                value_max = float(values.max()) if values.size > 0 else float('nan')
                self.get_logger().info(
                    f'规划完成 latency={latency:.3f}s '
                    f'pose=({base_x:.2f},{base_y:.2f}) '
                    f'value_max={value_max:.3f} traj_n={traj_world.shape[0]}'
                )
            except Exception as exc:
                self.get_logger().error(f'nogoal 推理失败: {exc}')
                time.sleep(0.5)
                continue

            # 规划本身耗时已提供节奏；额外短睡降低 CPU
            time.sleep(0.05)

    def _control_worker(self):
        """独立线程求解 MPC；结果写入 _last_cmd，由定时器平滑续发。"""
        while self.is_running and rclpy.ok():
            if not self._server_ready or not self._navigating:
                time.sleep(0.05)
                continue

            with self._data_lock:
                pose = self.pose
            if pose is None:
                time.sleep(0.05)
                continue

            base_x, base_y, base_yaw = pose
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
        self.cmd_pub.publish(stop)

    def destroy_node(self):
        self.is_running = False
        if self._navigating:
            self._publish_stop()
        super().destroy_node()


def build_arg_parser():
    parser = argparse.ArgumentParser(description='NavDP NoGoal ROS2 client for TomatoBot')
    parser.add_argument('--port', type=int, default=8888, help='NavDP server 端口')
    parser.add_argument('--speed', type=float, default=0.5, help='MPC 期望/最大速度')
    parser.add_argument('--stop_threshold', type=float, default=-3.0, help='传给 NavDP reset')
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
    return parser


def main(args=None):
    # 允许 ros2 run ... -- --port 8888 --speed 0.4
    parser = build_arg_parser()
    cli_args, ros_args = parser.parse_known_args(args=args)

    rclpy.init(args=ros_args)
    node = NavDPNoGoalClient(cli_args)
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
