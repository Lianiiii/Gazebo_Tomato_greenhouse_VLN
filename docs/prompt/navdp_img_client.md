# navdp客户端构造

## 基本信息
- 项目frame看/home/ylubt2204/tomato_ws/docs/基本信息/tomato_frame.md

## 目前进度
- 目前point_goal的client端已构建完毕/home/ylubt2204/tomato_ws/run_navdp_pointgoal_client.sh，能让bot正确的在大棚中导航了。
## 本次需求
- 本次需要构建navdp的imagegoal的client端。
- 需要达到的效果是：在我正常启动了大棚仿真环境之后（./run_tomato_bot_test.sh），然后我会启动navdp的server服务端。然后我运行你编写的client端之后，client端会将当前bot的rgb与depth观测给navdp的server，然后bot执行navdp推理出来的轨迹在仿真中导航。给你的imggoal的路径在/home/ylubt2204/tomato_ws/docs/imgs，需要能很方便的切换图片。
- 达到目标后应该能停下来
- 可以参考pointgoal的构建/home/ylubt2204/tomato_ws/run_navdp_pointgoal_client.sh
- 你可以自行运行查看你编程效果或排查问题

## 构建限制
- 你仅仅需要构建imggoal的client端就行了，逻辑与pointgoal的逻辑一致。不允许你乱改其他地方的完好代码以及navdp服务端的代码。