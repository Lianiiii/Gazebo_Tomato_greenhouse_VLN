# navdp客户端构造

## 基本信息
- 项目frame看/home/ylubt2204/tomato_ws/docs/基本信息/tomato_frame.md

## 目前进度
- 目前navdp的pointgoal和imggoal的client端已构建完毕/home/ylubt2204/tomato_ws/run_navdp_imggoal_client.sh，/home/ylubt2204/tomato_ws/run_navdp_pointgoal_client.sh能让bot正确的在大棚中导航了。
## 本次需求
- 本次需要构建navdp的Mixed Goal Navigation / IP Mix Goal（混合目标导航）的client端。
- 需要达到的效果是：在我正常启动了大棚仿真环境之后（./run_tomato_bot_test.sh），然后我会启动navdp的server服务端。然后我运行你编写的client端之后，client端会将当前bot的rgb与depth观测给navdp的server，然后bot执行navdp推理出来的轨迹在仿真中导航。
- Mixed Goal Navigation / IP Mix Goal（混合目标导航）：同时结合空间点坐标（Point Goal）和目标图像（Image Goal）两种条件进行导航。对应的服务端接口为 /navdp_step_ip_mixgoal，底层调用 step_point_image_goal 和 predict_ip_action 函数。
- 可以参考pointgoal的构建/home/ylubt2204/tomato_ws/run_navdp_pointgoal_client.sh和imggoal的构建/home/ylubt2204/tomato_ws/run_navdp_imggoal_client.sh
- 应该navdp的服务端给的接口是既有目标点也有图片吧。需要图片从/home/ylubt2204/tomato_ws/docs/imgs这里提取，并且能更换，目标点可以从终端输入。达到目标后应该能停下来。
- 你可以自行运行查看你编程效果或排查问题
- 你可以自行阅读navdp的server端的代码作参考

## 构建限制
- 你仅仅需要构建mix_goal的client端就行了，逻辑上与pointgoal的逻辑一致。不允许你乱改其他地方的完好代码以及navdp服务端的代码。