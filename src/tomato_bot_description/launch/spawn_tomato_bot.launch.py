# 中文说明：启动 robot_state_publisher，并将 TomatoBot 生成到 Gazebo Classic。
# ROS 接口：robot_description 参数；gazebo_ros/spawn_entity.py 的 /spawn_entity 服务。

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
import os


def generate_launch_description():
    pkg_tomato_bot = FindPackageShare(
        package='tomato_bot_description').find('tomato_bot_description')
    xacro_file = os.path.join(pkg_tomato_bot, 'xacro', 'tomato_bot.xacro')

    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    z = LaunchConfiguration('z')
    spawn_robot = LaunchConfiguration('spawn_robot')
    use_sim_time = LaunchConfiguration('use_sim_time')

    # 默认生成在两排作物中间过道，略抬高后落下，避免与护栏/植株碰撞弹飞
    declare_x_cmd = DeclareLaunchArgument(
        name='x', default_value='2.0', description='X coordinate of the robot')
    declare_y_cmd = DeclareLaunchArgument(
        name='y', default_value='1.5', description='Y coordinate of the robot')
    declare_z_cmd = DeclareLaunchArgument(
        name='z', default_value='0.25',
        description='Z coordinate of the robot above the ground')
    declare_spawn_robot_cmd = DeclareLaunchArgument(
        name='spawn_robot', default_value='true',
        description='Whether to spawn the robot')
    declare_use_sim_time_cmd = DeclareLaunchArgument(
        name='use_sim_time', default_value='true',
        description='Use simulation time')

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': ParameterValue(
                Command(['xacro ', xacro_file]), value_type=str),
            'use_sim_time': use_sim_time
        }]
    )

    spawn_tomato_bot_node = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-topic', 'robot_description',
            '-entity', 'tomato_bot',
            '-x', x, '-y', y, '-z', z,
            '-timeout', '120.0'
        ],
        output='screen',
        condition=IfCondition(spawn_robot)
    )

    # 等 gzserver factory 就绪后再 spawn，避免黑屏/超时
    delayed_spawn = TimerAction(
        period=8.0,
        actions=[spawn_tomato_bot_node]
    )

    return LaunchDescription([
        declare_x_cmd,
        declare_y_cmd,
        declare_z_cmd,
        declare_spawn_robot_cmd,
        declare_use_sim_time_cmd,
        robot_state_publisher_node,
        delayed_spawn,
    ])
