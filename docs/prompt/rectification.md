# 项目整改

## 基本环境
- 基本环境已经配好，用的是conda的navdp环境。

## 整体需求
- 认识这个项目可以看/home/ylubt2204/tomato_ws/src/aoc_tomato_farm/README.md
- 首先我需要你看一下目前这个TOMATO_WS下的启动文件都有哪些功能，然后告诉我。（如run_streamvln_tomato.sh是干啥的，start_individual.sh这个又是干啥的），以及他们怎么用。
- 本次项目整改的需求是：以/home/ylubt2204/tomato_ws/src/aoc_tomato_farm这个功能包为基准，由于之前本项目是一个纯生成农业大棚场景的项目，现在需要你删掉我后来迁移进来的go2模型以及与go2相关的一些东西。
- 去掉go2之后，我需要你设计一个简单干净的模型，这个模型仅需要能方便收到navdp等导航算法得出来的轨迹或者由此计算出来的速度指令，能自然且顺畅的执行这些速度指令并在这个大棚当中导航
- 这个简单干净的模型最好稍微高一点点，头部大概到植株的中上部分。头顶需要配备一个深度相机如d435，或者你用你的方法让他能获取他前方当前的深度与rgb信息（因为navdp或者其他的导航算法需要这些信息才能给出导航的路径或者速度指令）
- 我要求在启动这个/home/ylubt2204/tomato_ws/src/aoc_tomato_farm/tomato_farm_simulator/launch/tomato_farm_world.launch.py仿真环境后，也能通过rviz或者其他的方式让我看到头顶的传感器的画面（深度和rgb信息）
- 需要看navdp的调用部分可以看/home/ylubt2204/NavDP/baselines/navdp/navdp_server.py
- 用于接受导航算法产生的轨迹或者速度指令来控制仿真中的模型移动的client端代码可以参考/home/ylubt2204/NavDP/teleop_pointgoal_wheeled.py
- 整改过程中，你可以自行运行检测可行性与完整性。
- 起码需要交付一个能用键盘控制结点来控制那个模型在仿真中移动的效果。如果项目太复杂可以后续持续构建。