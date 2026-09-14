#!/usr/bin/env python3
"""
测试TomatoBot系统
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import sys
import os

class TomatoBotTest(Node):
    """测试节点"""

    def __init__(self):
        super().__init__('tomato_bot_test')

        # 测试结果
        self.test_results = {
            'tf': False,
            'robot_model': False,
            'cmd_vel': False,
            'joint_states': False,
            'camera': False
        }

        # 创建话题监听器
        self.tf_sub = self.create_subscription(
            String,
            '/tf',
            self.tf_callback,
            10
        )

        self.cmd_vel_sub = self.create_subscription(
            String,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        self.joint_states_sub = self.create_subscription(
            String,
            '/joint_states',
            self.joint_states_callback,
            10
        )

        self.camera_sub = self.create_subscription(
            String,
            '/camera/color/image_raw',
            self.camera_callback,
            10
        )

        # 创建话题发布器
        self.cmd_vel_pub = self.create_publisher(
            String,
            '/cmd_vel',
            10
        )

        self.get_logger().info('TomatoBot测试启动...')

        # 5秒后开始测试
        self.test_timer = self.create_timer(5.0, self.start_test)

    def tf_callback(self, msg):
        """TF回调"""
        self.test_results['tf'] = True
        self.get_logger().info('✓ TF话题已发布')

    def cmd_vel_callback(self, msg):
        """速度命令回调"""
        self.test_results['cmd_vel'] = True
        self.get_logger().info('✓ 速度命令话题已发布')

    def joint_states_callback(self, msg):
        """关节状态回调"""
        self.test_results['joint_states'] = True
        self.get_logger().info('✓ 关节状态话题已发布')

    def camera_callback(self, msg):
        """相机回调"""
        self.test_results['camera'] = True
        self.get_logger().info('✓ 相机话题已发布')

    def start_test(self):
        """开始测试"""
        self.get_logger().info('开始测试TomatoBot系统...')

        # 发布测试命令
        test_cmd = String()
        test_cmd.data = 'test'
        self.cmd_vel_pub.publish(test_cmd)

        # 3秒后检查结果
        self.check_timer = self.create_timer(3.0, self.check_results)

    def check_results(self):
        """检查测试结果"""
        self.get_logger().info('\n=== 测试结果 ===')
        all_passed = True

        for test_name, result in self.test_results.items():
            status = "✓" if result else "✗"
            self.get_logger().info(f'{status} {test_name}: {"通过" if result else "失败"}')
            if not result:
                all_passed = False

        if all_passed:
            self.get_logger().info('\n🎉 所有测试通过！TomatoBot系统正常工作')
        else:
            self.get_logger().info('\n⚠️  部分测试失败，请检查系统配置')

        # 销毁测试节点
        self.destroy_node()
        rclpy.shutdown()

def main(args=None):
    rclpy.init(args=args)

    test_node = TomatoBotTest()

    try:
        rclpy.spin(test_node)
    except KeyboardInterrupt:
        pass
    finally:
        if rclpy.ok():
            test_node.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()