# navdp客户端构造

## 基本信息
- 项目frame看/home/ylubt2204/tomato_ws/docs/基本信息/tomato_frame.md

## 目前进度
- 目前整个仿真场景、bot、以及bot的相机rgb与depth信息都正常，键盘控制也正常

## 本次需求
- 本次需要开始构建navdp导航的client了。
- 本次先构建navdp的pointgoal的client端。
- 需要达到的效果是：在我正常启动了大棚仿真环境之后（./run_tomato_bot_test.sh），然后我会启动navdp的server服务端。然后我运行你编写的client端之后，client端会将当前bot的rgb与depth观测给navdp的server，然后bot执行navdp推理出来的轨迹在仿真中导航。
- 你可以自行运行查看你编程效果或排查问题