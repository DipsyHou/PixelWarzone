"""
Utility helpers shared across server modules.
"""
from __future__ import annotations
import math
from typing import Tuple, Optional


# ---------- 基础工具 ----------
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def distance_sq(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    return dx * dx + dy * dy


def normalize(x: float, y: float) -> Tuple[float, float]:
    n = math.hypot(x, y)
    if n == 0:
        return 0.0, 0.0
    return x / n, y / n


# ---------- 几何判定 ----------
def _dist_point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute the minimum distance from point (px, py) to the line segment [(x1, y1), (x2, y2)].

    Used by Iaido path checks and wall/block interactions.
    """
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def circle_aabb_overlap(cx: float, cy: float, r: float,
                        rcx: float, rcy: float,
                        half_w: float, half_h: Optional[float] = None) -> bool:
    """圆( cx,cy,r ) 与 轴对齐矩形(中心 rcx,rcy, 半宽/半高) 是否相交。
    当 half_h 为空时，使用正方形半边长 half_w。
    """
    if half_h is None:
        half_h = half_w
    # 最近点到矩形
    closest_x = clamp(cx, rcx - half_w, rcx + half_w)
    closest_y = clamp(cy, rcy - half_h, rcy + half_h)
    return distance(cx, cy, closest_x, closest_y) < r


def in_sector(px: float, py: float,
              ox: float, oy: float,
              dirx: float, diry: float,
              radius: float, half_angle_rad: float) -> bool:
    """判断点 (px,py) 是否位于以 (ox,oy) 为圆心，朝向(dirx,diry)，半角为 half_angle_rad，半径为 radius 的扇形内。"""
    vx = px - ox
    vy = py - oy
    dist = math.hypot(vx, vy)
    if dist > radius:
        return False
    ndx, ndy = normalize(dirx, diry)
    if ndx == 0 and ndy == 0:
        return False
    # 角度判定通过余弦值比较
    cos_theta = (vx * ndx + vy * ndy) / (dist or 1.0)
    return cos_theta >= math.cos(half_angle_rad)
