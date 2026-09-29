# 中文说明：TomatoBot 车体几何参数（C1 足迹 / 轮迹 clearance 用）。
# 默认对齐 tomato_bot_description/config/base_size.yaml 当前生效值，
# 以及 PointGoal 客户端固定相机外参 CAMERA_OFFSET_*。
# 本模块无 ROS 依赖，可供单测与后续 safe_traj_rerank 使用。

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class RobotGeom:
    """车体 footprint 与相机外参。

    单位均为米。wheel_separation 用于左右轮迹横向偏置；
    inflate 为足迹外扩安全裕度（在 clearance 计算中扣除）。
    """

    base_x: float = 0.32
    base_y: float = 0.18
    wheel_separation: float = 0.22
    camera_offset_xyz: Tuple[float, float, float] = (0.12, 0.0, 0.64)
    inflate: float = 0.05

    @classmethod
    def from_defaults(cls, **overrides) -> "RobotGeom":
        """用默认值构造，允许关键字覆盖部分字段。"""
        geom = cls()
        for key, value in overrides.items():
            if not hasattr(geom, key):
                raise TypeError(f"RobotGeom 无字段: {key}")
            setattr(geom, key, value)
        return geom
