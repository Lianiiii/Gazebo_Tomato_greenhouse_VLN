## 验证结果（2026-09-08）
- Gazebo：大棚 + tomato_bot 正常，开局不再甩飞
- 键盘：`ros2 run tomato_bot_controller keyboard_control` 可控制移动（termios，不依赖 pynput）
- RViz：只保留 Displays + RGB Image + Depth Image
- RGB / Depth：均正常显示

## 怎么用

```bash
cd /home/ylubt2204/tomato_ws
./run_tomato_bot_test.sh
```

或：

```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 launch tomato_farm_simulator tomato_farm_world.launch.py
```

### 另开终端（键盘必须前台）
```bash
source /opt/ros/humble/setup.bash
source /home/ylubt2204/tomato_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
ros2 run tomato_bot_controller keyboard_control
```

键位：
- W/S 前进/后退
- A/D 或 Q/E 转向
- 空格 / X 停止
- R/T 线速度 ±10%，F/G 角速度 ±10%
- Ctrl+C 退出

### RViz（如需单独开）
```bash
rviz2 -d /home/ylubt2204/tomato_ws/src/tomato_bot_controller/config/tomato_bot_rviz.rviz
```
- RGB 订阅：`/camera/image_raw`
- Depth 订阅：`/camera/depth/image_raw`（Max Value=5，Normalize 关闭）

关仿真：
```bash
pkill -9 gzserver gzclient
```

## 本次关键文件
- `src/tomato_bot_controller/tomato_bot_controller/keyboard_control.py`
- `src/tomato_bot_controller/config/tomato_bot_rviz.rviz`
- `src/tomato_bot_description/launch/spawn_tomato_bot.launch.py`（生成点 2.0, 1.5, 0.25）
- `src/tomato_bot_description/xacro/tomato_bot.xacro`（depth remapping）
- `run_tomato_bot_test.sh`
