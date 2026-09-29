#!/usr/bin/env python3
"""
Differential Drive Controller for TomatoBot
接收速度命令并转换为差速轮控制
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
from nav_msgs.msg import Odometry
import math
import time


class DiffDriveController(Node):
    """差速轮控制器节点"""

    def __init__(self):
        super().__init__('diff_drive_controller')

        # 参数
        self.wheel_radius = 0.05  # 轮半径 (m)
        self.wheel_separation = 0.32  # 轮距 (m)，与 base_size.yaml 同步
        self.max_wheel_velocity = 1.0  # 最大轮速度 (rad/s)
        self.cmd_vel_topic = '/cmd_vel'
        self.joint_state_topic = '/joint_states'
        self.odometry_topic = '/odom'

        # 订阅和发布
        self.cmd_vel_sub = self.create_subscription(
            Twist,
            self.cmd_vel_topic,
            self.cmd_vel_callback,
            10
        )

        self.joint_state_pub = self.create_publisher(
            JointState,
            self.joint_state_topic,
            10
        )

        self.odometry_pub = self.create_publisher(
            Odometry,
            self.odometry_topic,
            10
        )

        # 定时器
        self.timer = self.create_timer(0.02, self.timer_callback)  # 50Hz

        # 状态变量
        self.left_wheel_angle = 0.0
        self.right_wheel_angle = 0.0
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.last_time = time.time()

        self.get_logger().info('Differential drive controller initialized')

    def cmd_vel_callback(self, twist_msg):
        """处理接收到的速度命令"""
        linear_vel = twist_msg.linear.x
        angular_vel = twist_msg.angular.z

        # 计算左右轮速度
        left_vel = linear_vel - angular_vel * self.wheel_separation / 2
        right_vel = linear_vel + angular_vel * self.wheel_separation / 2

        # 转换为轮的角速度
        left_wheel_vel = left_vel / self.wheel_radius
        right_wheel_vel = right_vel / self.wheel_radius

        # 限制最大速度
        left_wheel_vel = max(-self.max_wheel_velocity,
                            min(self.max_wheel_velocity, left_wheel_vel))
        right_wheel_vel = max(-self.max_wheel_velocity,
                             min(self.max_wheel_velocity, right_wheel_vel))

        # 存储轮速度
        self.left_wheel_vel = left_wheel_vel
        self.right_wheel_vel = right_wheel_vel

        self.get_logger().debug(f'Command: linear={linear_vel:.3f}, angular={angular_vel:.3f}')
        self.get_logger().debug(f'Wheel velocities: left={left_wheel_vel:.3f}, right={right_wheel_vel:.3f}')

    def timer_callback(self):
        """定时回调，发布关节状态和里程计"""
        current_time = time.time()
        dt = current_time - self.last_time
        self.last_time = current_time

        # 更新轮角度
        self.left_wheel_angle += self.left_wheel_vel * dt
        self.right_wheel_angle += self.right_wheel_vel * dt

        # 计算机器人位姿
        # 计算轮的线速度
        left_wheel_vel_linear = self.left_wheel_vel * self.wheel_radius
        right_wheel_vel_linear = self.right_wheel_vel * self.wheel_radius

        # 计算平均线速度和角速度
        linear_vel = (left_wheel_vel_linear + right_wheel_vel_linear) / 2
        angular_vel = (right_wheel_vel_linear - left_wheel_vel_linear) / self.wheel_separation

        # 更新位姿
        self.x += linear_vel * math.cos(self.theta) * dt
        self.y += linear_vel * math.sin(self.theta) * dt
        self.theta += angular_vel * dt

        # 发布关节状态
        joint_state = JointState()
        joint_state.header.stamp = self.get_clock().now().to_msg()
        joint_state.name = ['left_wheel_joint', 'right_wheel_joint']
        joint_state.position = [self.left_wheel_angle, self.right_wheel_angle]
        joint_state.velocity = [self.left_wheel_vel, self.right_wheel_vel]
        self.joint_state_pub.publish(joint_state)

        # 发布里程计
        odometry = Odometry()
        odometry.header.stamp = self.get_clock().now().to_msg()
        odometry.header.frame_id = 'odom'
        odometry.child_frame_id = 'base_link'

        odometry.pose.pose.position.x = self.x
        odometry.pose.pose.position.y = self.y
        odometry.pose.pose.position.z = 0.0

        # 四元数表示朝向
        quaternion = self.euler_to_quaternion(0, 0, self.theta)
        odometry.pose.pose.orientation.x = quaternion[0]
        odometry.pose.pose.orientation.y = quaternion[1]
        odometry.pose.pose.orientation.z = quaternion[2]
        odometry.pose.pose.orientation.w = quaternion[3]

        # 速度
        odometry.twist.twist.linear.x = linear_vel
        odometry.twist.twist.linear.y = 0.0
        odometry.twist.twist.linear.z = 0.0
        odometry.twist.twist.angular.x = 0.0
        odometry.twist.twist.angular.y = 0.0
        odometry.twist.twist.angular.z = angular_vel

        self.odometry_pub.publish(odometry)

    def euler_to_quaternion(self, roll, pitch, yaw):
        """将欧拉角转换为四元数"""
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)

        q = [0.0, 0.0, 0.0, 0.0]
        q[0] = cy * cp * cr + sy * sp * sr
        q[1] = cy * cp * sr - sy * sp * cr
        q[2] = sy * cp * sr + cy * sp * cr
        q[3] = sy * cp * cr - cy * sp * sr

        return q


def main(args=None):
    rclpy.init(args=args)

    controller = DiffDriveController()

    try:
        rclpy.spin(controller)
    except KeyboardInterrupt:
        pass
    finally:
        controller.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()