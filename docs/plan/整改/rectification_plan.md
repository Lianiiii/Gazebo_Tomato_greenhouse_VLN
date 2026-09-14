# TOMATO_WS 项目整改方案

## 1. 项目背景与整改需求

### 1.1 现状分析
- **当前项目**：TOMATO_WS 是一个基于 ROS2 Humble 的农业机器人仿真平台
- **主要功能**：生成番茄农场/温室环境，支持机器人在其中的导航和交互
- **存在问题**：项目后期迁移了 Go2 四足机器人及其复杂控制系统，不符合"简单干净"的需求
- **核心文件**：
  - 启动脚本：`run_streamvln_tomato.sh`（主启动）、`start_individual.sh`（分步启动）
  - 仿真环境：`tomato_farm_world.launch.py`
  - 导航客户端：`navdp_ros_client.py`
  - 参考控制：`teleop_pointgoal_wheeled.py`

### 1.2 整改目标
1. **移除 Go2 相关组件**：删除所有四足机器人相关的代码和依赖
2. **设计简单模型**：创建一个适合温室环境的差速轮机器人
3. **集成传感器**：在机器人头部安装 RGB-D 相机（D435 或等效）
4. **支持导航算法**：能够接收并执行 NavDP 等算法生成的轨迹或速度指令
5. **可视化支持**：在 RViz 中显示传感器数据
6. **基础控制**：至少实现键盘控制功能

## 2. 具体整改方案

### 2.1 需要删除的 Go2 相关组件

#### 2.1.1 功能包删除
```
/home/ylubt2204/tomato_ws/src/go2_description/
/home/ylubt2204/tomato_ws/src/quadropted_controller/
/home/ylubt2204/tomato_ws/src/go2_keyboard_control/
```

#### 2.1.2 文件修改
1. **`run_streamvln_tomato.sh`**：
   - 移除 Go2 URDF 生成（第77行）
   - 修改启动参数，不再依赖 Go2 相关功能

2. **`start_individual.sh`**：
   - 移除 `spawn_go2` 函数（第54-58行）
   - 修改启动流程，跳过 Go2 生成步骤

3. **`tomato_farm_world.launch.py`**：
   - 移除所有 Go2 相关节点（第74-144行）
   - 保留 Gazebo 服务器和客户端启动
   - 移除机器人状态发布器、实体生成、控制器等

#### 2.1.3 客户端脚本删除
```
/home/ylubt2204/tomato_ws/src/go2_vln_sim_client.py
```

### 2.2 新的差速轮机器人设计

#### 2.2.1 机器人模型设计
**名称**：TomatoBot（简单的差速轮机器人）

**参数配置**：
- **尺寸**：半径 0.2m，高度 0.8m（确保头部能到达植株中上部）
- **轮距**：0.4m
- **轮半径**：0.05m
- **最大速度**：0.5 m/s
- **最大角速度**：1.0 rad/s

**传感器配置**：
- **RGB-D 相机**：Intel D435 或等效，安装于机器人顶部（高度 0.7m）
- **相机参数**：
  - 分辨率：640x480
  - FOV：1.57 rad（90度）
  - RGB 话题：`/camera/color/image_raw`
  - Depth 话题：`/camera/depth/image_raw`
  - 相机信息话题：`/camera/camera_info`

#### 2.2.2 创建新功能包
```
/home/ylubt2204/tomato_ws/src/tomato_bot_description/
├── urdf/
│   ├── tomato_bot.urdf
│   └── tomato_bot.gazebo
├── xacro/
│   └── tomato_bot.xacro
├── meshes/
│   └── wheel.stl
└── launch/
    └── spawn_tomato_bot.launch.py
```

### 2.3 控制系统设计

#### 2.3.1 基于现有代码的改进
参考 `navdp_ros_client.py` 的架构：
- 保持异步规划（NavDP 算法）和控制分离的设计
- 使用 Pure Pursuit 算法进行轨迹跟踪
- 控制频率：50Hz

#### 2.3.2 差速轮运动学
- **输入**：`geometry_msgs/Twist`（linear.x, angular.z）
- **输出**：左右轮速度
- **运动学模型**：
  ```
  v = linear.x
  ω = angular.z
  v_left = v - ω * wheel_base / 2
  v_right = v + ω * wheel_base / 2
  ```

### 2.4 修改后的启动流程

#### 2.4.1 新的启动脚本
1. **简化版启动脚本**：
   - 仅启动 Gazebo 仿真环境
   - 生成 TomatoBot 机器人
   - 可选：启动导航客户端

2. **分步启动脚本**：
   - `start_gazebo`：启动番茄农场环境
   - `spawn_tomato_bot`：生成机器人
   - `start_keyboard_control`：启动键盘控制
   - `start_navdp_client`：启动 NavDP 导航客户端

#### 2.4.2 修改后的 launch 文件
**`tomato_farm_world.launch.py` 简化版**：
```python
# 仅保留 Gazebo 启动部分
# 移除所有 Go2 相关内容
```

**新的 `spawn_tomato_bot.launch.py`**：
```python
# 生成 TomatoBot 机器人
# 包含：robot_state_publisher, spawn_entity, camera_info_publisher
```

### 2.5 传感器可视化

#### 2.5.1 RViz 配置
创建 `tomato_bot_rviz.rviz` 配置文件，显示：
- RGB 图像
- 深度图像
- 点云数据
- 机器人模型
- 轨迹规划结果

#### 2.5.2 图像显示节点
创建 `image_viewer.py` 节点：
- 订阅 `/camera/color/image_raw` 和 `/camera/depth/image_raw`
- 使用 OpenCV 显示图像
- 可选：集成到 RViz 中

## 3. 实施步骤

### 3.1 第一阶段：清理 Go2 组件（1-2天）
1. **删除 Go2 相关功能包**
   ```bash
   sudo rm -rf /home/ylubt2204/tomato_ws/src/go2_description
   sudo rm -rf /home/ylubt2204/tomato_ws/src/quadropted_controller
   sudo rm -rf /home/ylubt2204/tomato_ws/src/go2_keyboard_control
   ```

2. **修改启动脚本**
   - 修改 `run_streamvln_tomato.sh`，移除 Go2 相关代码
   - 修改 `start_individual.sh`，移除 spawn_go2 函数
   - 测试启动流程

### 3.2 第二阶段：创建 TomatoBot（2-3天）
1. **创建新功能包**
   ```bash
   cd /home/ylubt2204/tomato_ws/src
   ros2 pkg create tomato_bot_description --build-type ament_cmake
   ```

2. **设计 URDF 模型**
   - 创建简单的差速轮机器人 URDF
   - 配置 RGB-D 相机传感器
   - 添加 Gazebo 插件

3. **创建 launch 文件**
   - `spawn_tomato_bot.launch.py`
   - 包含必要的节点配置

### 3.3 第三阶段：控制系统实现（2-3天）
1. **实现基础控制**
   - 创建 `diff_drive_controller.py`
   - 实现 Twist 命令到轮速的转换
   - 发布 `/cmd_vel` 话题

2. **集成 NavDP**
   - 基于 `navdp_ros_client.py` 创建新版本
   - 适配差速轮机器人的控制
   - 保持 Pure Pursuit 轨迹跟踪

3. **实现键盘控制**
   - 创建 `keyboard_control.py`
   - 监听键盘输入，发布 Twist 命令
   - 使用 `pynput` 库

### 3.4 第四阶段：可视化与测试（1-2天）
1. **配置 RViz**
   - 创建 RViz 配置文件
   - 显示传感器数据
   - 可视化轨迹

2. **功能测试**
   - 测试键盘控制
   - 测试 NavDP 集成
   - 验证传感器数据可视化

3. **性能优化**
   - 调整控制参数
   - 优化延迟

## 4. 关键文件清单

### 4.1 需要删除的文件
- `src/go2_description/`（整个目录）
- `src/quadropted_controller/`（整个目录）
- `src/go2_keyboard_control/`（整个目录）
- `src/go2_vln_sim_client.py`

### 4.2 需要修改的文件
- `run_streamvln_tomato.sh`（移除 Go2 相关代码）
- `start_individual.sh`（移除 spawn_go2 函数）
- `src/aoc_tomato_farm/tomato_farm_simulator/launch/tomato_farm_world.launch.py`（简化，移除 Go2 内容）

### 4.3 需要创建的文件
- `src/tomato_bot_description/`（新功能包）
- `src/tomato_bot_controller/`（可选，控制功能包）
- `src/tomato_bot_viz/`（可选，可视化功能包）

## 5. 验证策略

### 5.1 基础功能验证
1. **启动测试**：
   ```bash
   # 测试环境启动
   ./start_individual.sh gazebo
   
   # 测试机器人生成
   ros2 launch tomato_bot_description spawn_tomato_bot.launch.py
   
   # 测试键盘控制
   ros2 run tomato_bot_controller keyboard_control
   ```

2. **传感器测试**：
   ```bash
   # 检查传感器话题
   ros2 topic list | grep camera
   ros2 topic echo /camera/color/image_raw --once
   ```

3. **RViz 可视化**：
   ```bash
   rviz2 -d src/tomato_bot_viz/rviz/tomato_bot_rviz.rviz
   ```

### 5.2 导航集成验证
1. **NavDP 连接**：
   ```bash
   # 启动 NavDP 客户端
   ros2 run tomato_bot_controller navdp_client
   ```

2. **轨迹跟踪**：
   - 验证机器人能否跟踪 NavDP 生成的轨迹
   - 检查控制延迟和准确性

### 5.3 性能指标
- **控制延迟**：< 100ms
- **轨迹跟踪误差**：< 5cm
- **传感器帧率**：30Hz
- **系统稳定性**：连续运行 10 分钟无崩溃

## 6. 风险与应对

### 6.1 主要风险
1. **依赖冲突**：移除 Go2 组件可能影响其他依赖
2. **传感器集成**：RGB-D 相机配置可能存在兼容性问题
3. **控制性能**：差速轮机器人的控制性能可能不如四足机器人

### 6.2 应对策略
1. **逐步迁移**：保留原始备份，分阶段删除
2. **测试优先**：每步修改后进行全面测试
3. **参数调优**：针对新机器人特性调整控制参数

## 7. 后续扩展

### 7.1 功能增强
1. **SLAM 集成**：添加 SLAM 功能，实现自主建图
2. **路径规划**：集成 A* 或 RRT 路径规划算法
3. **多机器人**：支持多个机器人在温室协作

### 7.2 性能优化
1. **硬件加速**：使用 GPU 加速深度处理
2. **实时性**：优化控制算法，降低延迟
3. **能耗优化**：改进运动控制，减少能耗