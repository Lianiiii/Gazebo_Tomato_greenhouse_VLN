# 已废弃：请改用 tomato_bot_controller 的 pointgoal 客户端。
# 正确入口：
#   ros2 run tomato_bot_controller navdp_pointgoal_client -- --goal_x <x> --goal_y <y>
# 或：
#   ./run_navdp_pointgoal_client.sh --goal_x <x> --goal_y <y>
# 本文件为早期 nogoal 草稿，话题/内参约定不完整，请勿继续使用。

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist
import message_filters
from cv_bridge import CvBridge
import numpy as np
import threading
import time
import math
import sys
import os

# 动态将你的 NavDP 算法库加入路径，直接复用其底层通信 API
sys.path.append(os.path.expanduser("~/NavDP/baselines/navdp"))
try:
    from utils_tasks.client_utils import navigator_reset, nogoal_step
except ImportError as e:
    print(f"导入失败，请检查路径: {e}")

class NavDPGazeboClient(Node):
    def __init__(self):
        super().__init__('navdp_gazebo_client')
        self.bridge = CvBridge()
        self.port = 8888

        # --- 1. 初始化 AI 服务端 ---
        # Gazebo 深度相机默认参数 (FOV 1.5, 640x480)
        fx = fy = 343.3
        cx = 320.0
        cy = 240.0
        self.camera_intrinsic = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])
        
        self.get_logger().info("正在重置 NavDP 服务端...")
        try:
            # 这里的 batch_size 为 1，因为我们只有一只狗
            navigator_reset(self.camera_intrinsic, batch_size=1, stop_threshold=-3.0, port=self.port)
            self.get_logger().info("NavDP 服务端初始化成功！")
        except Exception as e:
            self.get_logger().error(f"连接服务端失败: {e}")

        # --- 2. 共享状态与锁 ---
        self.latest_rgb = None
        self.latest_depth = None
        self.target_trajectory = None
        self.data_lock = threading.Lock()

        # --- 3. ROS 2 订阅与发布 ---
        self.rgb_sub = message_filters.Subscriber(self, Image, '/camera/color/image_raw')
        self.depth_sub = message_filters.Subscriber(self, Image, '/camera/depth/image_raw')
        # 允许一定的时间误差同步 RGB 和 Depth
        self.ts = message_filters.ApproximateTimeSynchronizer([self.rgb_sub, self.depth_sub], 10, 0.1)
        self.ts.registerCallback(self.image_callback)
        
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # --- 4. 启动异步规划与高频控制线程 ---
        self.is_running = True
        self.plan_thread = threading.Thread(target=self.planning_loop, daemon=True)
        self.plan_thread.start()
        
        # 50Hz 的底层控制循环，确保持续输出速度指令
        self.control_timer = self.create_timer(0.02, self.control_loop)

    def image_callback(self, rgb_msg, depth_msg):
        """将 ROS 图像转换为 Numpy 并存入共享内存"""
        try:
            cv_rgb = self.bridge.imgmsg_to_cv2(rgb_msg, "bgr8")
            cv_depth = self.bridge.imgmsg_to_cv2(depth_msg, "32FC1") # 米

            # 扩展维度以匹配 Isaac Sim 要求的 (Batch, H, W, C) 格式
            batch_rgb = np.expand_dims(cv_rgb, axis=0)
            batch_depth = np.expand_dims(cv_depth, axis=0)

            with self.data_lock:
                self.latest_rgb = batch_rgb
                self.latest_depth = batch_depth
        except Exception as e:
            self.get_logger().error(f"图像处理错误: {e}")

    def planning_loop(self):
        """低频大模型推理线程"""
        while self.is_running:
            with self.data_lock:
                if self.latest_rgb is None or self.latest_depth is None:
                    time.sleep(0.05)
                    continue
                rgb_input = self.latest_rgb.copy()
                depth_input = self.latest_depth.copy()
            
            try:
                start_time = time.time()
                # 调用你算法库自带的推理函数
                trajectory_camera, _, _ = nogoal_step(rgb_input, depth_input, port=self.port)
                
                # 提取第一台机器人(Batch 0)的轨迹
                if trajectory_camera is not None and len(trajectory_camera) > 0:
                    with self.data_lock:
                        self.target_trajectory = trajectory_camera[0]
                
                latency = time.time() - start_time
                self.get_logger().info(f"NavDP 思考延迟: {latency:.3f}s")
            except Exception as e:
                self.get_logger().error(f"推理请求异常: {e}")
                time.sleep(0.5)

    def control_loop(self):
        """高频轨迹追踪线程 (Pure Pursuit)"""
        twist = Twist()
        with self.data_lock:
            traj = self.target_trajectory
            
        if traj is None or len(traj) < 4:
            # 没有轨迹时刹车
            self.cmd_pub.publish(twist)
            return
            
        # 选取大模型预测的前方第 3 个点作为追踪目标 (Lookahead)
        # 假设相机坐标系：traj[i][0] 是深度(X), traj[i][1] 是横向(Y)
        target_x = traj[3][0] 
        target_y = traj[3][1]
        
        # 计算航向角偏差
        target_angle = math.atan2(target_y, target_x)
        distance = math.hypot(target_x, target_y)
        
        # 简单的比例控制器 (P-Control)
        twist.angular.z = max(-0.8, min(0.8, 1.5 * target_angle))
        
        # 如果角度偏差不大，就加速往前开；否则降速转弯
        if abs(target_angle) < 0.4:
            twist.linear.x = max(0.0, min(0.4, 0.5 * distance))
        else:
            twist.linear.x = 0.05 
            
        self.cmd_pub.publish(twist)

def main(args=None):
    rclpy.init(args=args)
    node = NavDPGazeboClient()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.is_running = False
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()