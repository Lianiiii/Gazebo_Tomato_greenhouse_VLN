# 项目整体信息

## 基本信息描述
- 项目本体为番茄大棚生成器，readme在/home/ylubt2204/tomato_ws/src/aoc_tomato_farm/README.md
- 启动功能包在/home/ylubt2204/tomato_ws/src/aoc_tomato_farm
- 启动文件为/home/ylubt2204/tomato_ws/src/aoc_tomato_farm/tomato_farm_simulator/launch/tomato_farm_world.launch.py
- 可用环境为conda中的名为navdp环境
- 相机rgb话题为/camera/image_raw，相机depth话题为/camera/depth/image_raw，相机内参为/camera/camera_info
- 控制话题为/cmd_vel（geometry_msgs/Twist），里程计为/odom

## 项目最终目标
- 仿真大棚的初衷是为了验证各种导航算法在农业大棚中的导航能力
- 首先需要在大棚里布置一个能接收运动指令的模型。模型越简单越简介越好，不需要很花里胡哨，能执行算法给出的路径或者由路径转化的速度指令，验证导航算法的能力就行
- 导航算法后续可能会更换，目前先跑通navdp。navdp可以看/home/ylubt2204/NavDP/README.md
- - navdp的服务端代码可以看/home/ylubt2204/NavDP/baselines/navdp/navdp_server.py
- 当大棚的基本环境打通之后如果需要构建客户端了可以参考/home/ylubt2204/NavDP/teleop_imagegoal_wheeled.py

## NavDP PointGoal 客户端
- 节点：`ros2 run tomato_bot_controller navdp_pointgoal_client -- --goal_x <x> --goal_y <y>`
- 便捷脚本：`./run_navdp_pointgoal_client.sh --goal_x <x> --goal_y <y>`
- 前置：`./run_tomato_bot_test.sh` 已启动仿真，且 NavDP server 已在端口（默认 8888）运行
- 到达阈值默认 `--arrive_dist 0.3`（米）；目标请给到距当前 `/odom` 明显更远的点
- 联调时不要同时开 `keyboard_control`，避免抢占 `/cmd_vel`
- 客户端仅在收到首条有效轨迹并开始导航后才发布 `/cmd_vel`；未就绪时不发零速

## NavDP ImageGoal 客户端
- 节点：`ros2 run tomato_bot_controller navdp_imggoal_client -- --goal_image <path>`
- 便捷脚本：`./run_navdp_imggoal_client.sh [--goal_image docs/imgs/goal1.png]`
- 目标图默认目录：`docs/imgs/`；启动脚本会列出可选图片，换图用 `--goal_image`
- 到达判定：`all_values.max()` 连续 `--stop_hits`（默认 3）次低于 `--stop_threshold`（默认 -3.0）后停车
- 前置与 `/cmd_vel` 约定同 PointGoal
- 启动命令：./run_navdp_imggoal_client.sh --goal_image docs/imgs/goal1.png --port 8888 --speed 0.4

## 限制
- 不允许改navdp的server端的代码
