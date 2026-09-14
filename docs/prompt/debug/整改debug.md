# 整改debug

## 基本信息
- 上次修改结束后的结果看/home/ylubt2204/tomato_ws/docs/基本信息/大棚bot仿真整改使用.md
- 上次修改后./run_tomato_bot_test.sh能正常出现大棚和bot。但是键盘控制是有问题的。
- 上次修改后，ros2 run tomato_bot_controller keyboard_control并不能正常运行，会报错。
- 并且在启动后发现一个不知道算不算问题的bug，就是生成的bot是突然甩到大棚护栏的侧边撞停的。怀疑是机器人的生成点的问题？或者是机器人的重力方向错了？
- 并且rviz界面太复杂了，我只需要显示rgb image，depth image，displays。其他的无关紧要的选项去掉。
- rviz中depth image是全黑的，并没有深度信息。

## 本次debug需求
- 修改好键盘控制，要求键盘能控制这个简单的bot移动。
- 至于机器人甩到护栏侧面开局，如果影响不大可以不改。
- 目前的仿真是能正常启动大棚与bot的，修改的时候不要修改目前已经稳定或者正常的代码。
- 修改rviz
- 你可以自行运行检测你的代码修改效果