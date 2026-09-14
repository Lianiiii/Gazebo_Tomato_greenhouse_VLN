"""
Launch Gazebo with tomato farm (2m x 3m), spawn Go2 robot with camera,
and start the StreamVLN simulation client.

Usage:
  ros2 launch tomato_farm_vln_bringup tomato_farm_vln_bringup.launch.py
  ros2 launch tomato_farm_vln_bringup tomato_farm_vln_bringup.launch.py headless:=True

IMPORTANT: This launch file must be run with DISPLAY=:0 and
LIBGL_ALWAYS_SOFTWARE=1 environment variables set.
"""
import os
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    ExecuteProcess,
    TimerAction,
    LogInfo,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression, Command
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_tomato = FindPackageShare(package='tomato_farm_simulator').find('tomato_farm_simulator')
    pkg_go2 = FindPackageShare(package='go2_description').find('go2_description')

    # ============ Arguments ============
    headless = LaunchConfiguration('headless', default='False')
    use_sim_time = LaunchConfiguration('use_sim_time', default='true')
    spawn_x = LaunchConfiguration('spawn_x', default='0.5')
    spawn_y = LaunchConfiguration('spawn_y', default='1.5')
    spawn_z = LaunchConfiguration('spawn_z', default='0.35')
    server_url = LaunchConfiguration('server_url',
                                     default='http://localhost:5801/eval_vln')
    instruction = LaunchConfiguration('instruction',
                                      default='Walk forward through the tomato farm rows. Navigate carefully between the plants.')

    declare_args = [
        DeclareLaunchArgument('headless', default_value='False'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('spawn_x', default_value='0.5'),
        DeclareLaunchArgument('spawn_y', default_value='1.5'),
        DeclareLaunchArgument('spawn_z', default_value='0.35'),
        DeclareLaunchArgument('server_url', default_value='http://localhost:5801/eval_vln'),
        DeclareLaunchArgument('instruction',
                              default_value='Walk forward through the tomato farm rows. Navigate carefully between the plants.'),
    ]

    # ============ 0. Environment ============
    set_display = SetEnvironmentVariable('DISPLAY', ':0')
    set_sw_gl = SetEnvironmentVariable('LIBGL_ALWAYS_SOFTWARE', '1')
    set_gazebo_model_path = SetEnvironmentVariable(
        'GAZEBO_MODEL_PATH',
        os.path.join(pkg_tomato, 'models'))

    # ============ 1. Gazebo with Tomato Farm (2m x 3m) ============
    farm_world_file = os.path.join(
        pkg_tomato, 'worlds', '2mx3m',
        'tomato_farm_2mx3m_gazebo_classic.world')

    gz_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                FindPackageShare(package='gazebo_ros').find('gazebo_ros'),
                'launch', 'gzserver.launch.py')),
        launch_arguments={'world': farm_world_file}.items())

    gz_client = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                FindPackageShare(package='gazebo_ros').find('gazebo_ros'),
                'launch', 'gzclient.launch.py')),
        condition=IfCondition(PythonExpression(['not ', headless])))

    # ============ 2. Spawn Go2 Robot (delayed for Gazebo init) ============
    # Use xacro-generated URDF directly (avoids XML declaration parsing issue)
    xacro_file = os.path.join(pkg_go2, 'xacro', 'robot.xacro')
    urdf_cache = '/tmp/go2_generated.urdf'
    gen_urdf = ExecuteProcess(
        cmd=['xacro', xacro_file, '-o', urdf_cache],
        output='screen')

    spawn_go2 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        name='spawn_go2',
        output='screen',
        arguments=[
            '-entity', 'go2',
            '-file', urdf_cache,
            '-x', spawn_x,
            '-y', spawn_y,
            '-z', spawn_z])

    # Delay spawning to let Gazebo fully initialize (OpenAL takes ~30s)
    # Use custom spawn wrapper (avoids env issues with lxml parsing in system spawn_entity.py)
    spawn_cmd = [
        'python3',
        '/home/ylubt2204/tomato_ws/src/spawn_go2_robot.py',
        '--x', spawn_x,
        '--y', spawn_y,
        '--z', spawn_z,
        '--urdf', urdf_cache]
    spawn_proc = ExecuteProcess(cmd=spawn_cmd, output='screen')
    delayed_spawn = TimerAction(
        period=35.0,
        actions=[gen_urdf, LogInfo(msg='Spawning Go2 robot...'), spawn_proc])

    # ============ 3. StreamVLN Client (delayed more) ============
    vln_client_cmd = [
        'python3',
        os.path.join('/home/ylubt2204/tomato_ws/src', 'go2_vln_sim_client.py'),
        '--server', server_url,
        '--instruction', instruction,
    ]

    start_vln_client = TimerAction(
        period=45.0,  # Wait for Gazebo + Go2 spawn
        actions=[
            LogInfo(msg='\U0001f680 Starting StreamVLN simulation client...'),
            ExecuteProcess(cmd=vln_client_cmd, output='screen')])

    return LaunchDescription(
        declare_args + [
            set_display,
            set_sw_gl,
            set_gazebo_model_path,
            gz_server,
            gz_client,
            delayed_spawn,
            start_vln_client,
        ])
