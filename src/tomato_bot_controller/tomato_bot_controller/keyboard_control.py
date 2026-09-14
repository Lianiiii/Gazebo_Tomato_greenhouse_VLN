# 中文说明：通过终端键盘发布 TomatoBot 的差速速度命令（不依赖 pynput，适合 WSL）。
# ROS 接口：发布 /cmd_vel，消息类型 geometry_msgs/msg/Twist。
# 键位：W/S 前进后退，A/D 或 Q/E 转向，空格/X 停止，Ctrl+C 退出。

import sys
import termios
import threading
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node


HELP_MSG = """
TomatoBot Keyboard Control (/cmd_vel)
-------------------------------------
  W/S : 前进 / 后退
  A/D : 左转 / 右转
  Q/E : 左转 / 右转
  空格 或 X : 停止
  R/T : 线速度 ±10%
  F/G : 角速度 ±10%
  Ctrl+C : 退出

按一次方向键会持续运动，直到按空格/X 停止。
请保持本终端处于前台焦点；不要与 navdp_pointgoal_client 同时开。
"""


class KeyboardControl(Node):
    """键盘控制节点：把终端按键映射为 /cmd_vel。"""

    def __init__(self):
        super().__init__('keyboard_control')
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.linear_speed = 0.3
        self.angular_speed = 0.8
        self._last_twist = Twist()
        # 10Hz 续发，防止其它节点偶发零速后车立刻停住
        self.create_timer(0.1, self._hold_cmd)

    def publish_twist(self, linear_x=0.0, angular_z=0.0):
        msg = Twist()
        msg.linear.x = float(linear_x)
        msg.angular.z = float(angular_z)
        self._last_twist = msg
        self.cmd_vel_pub.publish(msg)

    def _hold_cmd(self):
        self.cmd_vel_pub.publish(self._last_twist)


def get_key(settings):
    tty.setraw(sys.stdin.fileno())
    key = sys.stdin.read(1)
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key


def main(args=None):
    print(HELP_MSG)
    settings = termios.tcgetattr(sys.stdin)

    rclpy.init(args=args)
    node = KeyboardControl()
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    try:
        while rclpy.ok():
            key = get_key(settings)

            if key == '\x03':  # Ctrl+C
                node.publish_twist(0.0, 0.0)
                break

            lower = key.lower()
            if lower == 'w':
                node.publish_twist(node.linear_speed, 0.0)
            elif lower == 's':
                node.publish_twist(-node.linear_speed, 0.0)
            elif lower in ('a', 'q'):
                node.publish_twist(0.0, node.angular_speed)
            elif lower in ('d', 'e'):
                node.publish_twist(0.0, -node.angular_speed)
            elif key == ' ' or lower == 'x':
                node.publish_twist(0.0, 0.0)
            elif lower == 'r':
                node.linear_speed = round(node.linear_speed * 1.1, 4)
                print(f'\r线速度={node.linear_speed:.3f} 角速度={node.angular_speed:.3f}   ', end='', flush=True)
            elif lower == 't':
                node.linear_speed = round(max(0.05, node.linear_speed * 0.9), 4)
                print(f'\r线速度={node.linear_speed:.3f} 角速度={node.angular_speed:.3f}   ', end='', flush=True)
            elif lower == 'f':
                node.angular_speed = round(node.angular_speed * 1.1, 4)
                print(f'\r线速度={node.linear_speed:.3f} 角速度={node.angular_speed:.3f}   ', end='', flush=True)
            elif lower == 'g':
                node.angular_speed = round(max(0.05, node.angular_speed * 0.9), 4)
                print(f'\r线速度={node.linear_speed:.3f} 角速度={node.angular_speed:.3f}   ', end='', flush=True)
            else:
                # 未知键忽略，保持上一拍速度（按空格/X 才停）
                pass
    except Exception as exc:
        node.get_logger().error(f'keyboard_control error: {exc}')
    finally:
        try:
            node.publish_twist(0.0, 0.0)
        except Exception:
            pass
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        spin_thread.join(timeout=1.0)


if __name__ == '__main__':
    main()
