# 中文说明：启动 robot_state_publisher，并将 TomatoBot 生成到 Gazebo Classic。
# ROS 接口：robot_description 参数；gazebo_ros/spawn_entity.py 的 /spawn_entity 服务。
# 底座尺寸默认读 config/base_size.yaml，可用 launch 参数临时覆盖。

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, TimerAction
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
import os
import yaml


def _load_base_size(pkg_share: str) -> dict:
    """读取底座尺寸配置；缺文件或缺字段时回退到防卡脚新默认。"""
    defaults = {
        'base_x': 0.32,
        'base_y': 0.28,
        'base_z': 0.18,
        'wheel_separation': 0.32,
    }
    cfg_path = os.path.join(pkg_share, 'config', 'base_size.yaml')
    if not os.path.isfile(cfg_path):
        return defaults
    with open(cfg_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    for key in defaults:
        if key in data and data[key] is not None:
            defaults[key] = float(data[key])
    return defaults


def generate_launch_description():
    pkg_tomato_bot = FindPackageShare(
        package='tomato_bot_description').find('tomato_bot_description')
    xacro_file = os.path.join(pkg_tomato_bot, 'xacro', 'tomato_bot.xacro')
    size = _load_base_size(pkg_tomato_bot)

    x = LaunchConfiguration('x')
    y = LaunchConfiguration('y')
    z = LaunchConfiguration('z')
    spawn_robot = LaunchConfiguration('spawn_robot')
    use_sim_time = LaunchConfiguration('use_sim_time')
    base_x = LaunchConfiguration('base_x')
    base_y = LaunchConfiguration('base_y')
    base_z = LaunchConfiguration('base_z')
    wheel_separation = LaunchConfiguration('wheel_separation')

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
    declare_base_x_cmd = DeclareLaunchArgument(
        name='base_x', default_value=str(size['base_x']),
        description='Base length (m), from config/base_size.yaml')
    declare_base_y_cmd = DeclareLaunchArgument(
        name='base_y', default_value=str(size['base_y']),
        description='Base width (m), from config/base_size.yaml')
    declare_base_z_cmd = DeclareLaunchArgument(
        name='base_z', default_value=str(size['base_z']),
        description='Base height (m), from config/base_size.yaml')
    declare_wheel_sep_cmd = DeclareLaunchArgument(
        name='wheel_separation', default_value=str(size['wheel_separation']),
        description='Wheel separation (m), from config/base_size.yaml')

    robot_description_cmd = Command([
        'xacro ', xacro_file,
        ' base_x:=', base_x,
        ' base_y:=', base_y,
        ' base_z:=', base_z,
        ' wheel_separation:=', wheel_separation,
    ])

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': ParameterValue(
                robot_description_cmd, value_type=str),
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

    size_log = LogInfo(msg=[
        'TomatoBot base size: base_x=', base_x,
        ' base_y=', base_y,
        ' base_z=', base_z,
        ' wheel_separation=', wheel_separation,
        ' (edit config/base_size.yaml to change; old=0.40/0.36/0.18/0.40)'
    ])

    return LaunchDescription([
        declare_x_cmd,
        declare_y_cmd,
        declare_z_cmd,
        declare_spawn_robot_cmd,
        declare_use_sim_time_cmd,
        declare_base_x_cmd,
        declare_base_y_cmd,
        declare_base_z_cmd,
        declare_wheel_sep_cmd,
        size_log,
        robot_state_publisher_node,
        delayed_spawn,
    ])
