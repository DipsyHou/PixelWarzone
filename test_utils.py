import math
from utils import _dist_point_to_segment


def approx(a, b, eps=1e-6):
    return abs(a - b) <= eps


def run_tests():
    # 1) 零长度线段：距离等于点到端点的距离
    d = _dist_point_to_segment(3, 4, 0, 0, 0, 0)
    assert approx(d, 5), f"zero-seg expected 5, got {d}"

    # 2) 水平线段，投影在线段内部
    # 线段 (0,0)-(10,0)，点(5,3) 到线段距离应为 3
    d = _dist_point_to_segment(5, 3, 0, 0, 10, 0)
    assert approx(d, 3), f"horizontal inner expected 3, got {d}"

    # 3) 水平线段，投影在线段外部，靠近右端点
    # 点(20,4) 到线段距离为到(10,0)的距离 sqrt((10)^2 + (4)^2)
    d = _dist_point_to_segment(20, 4, 0, 0, 10, 0)
    assert approx(d, math.hypot(10, 4)), f"horizontal outer expected {math.hypot(10,4)}, got {d}"

    # 4) 垂直线段，投影在线段内部
    d = _dist_point_to_segment(-2, 7, 0, 0, 0, 10)
    assert approx(d, 2), f"vertical inner expected 2, got {d}"

    # 5) 斜线段 45°： (0,0)-(10,10)，点(10,0) 到线段距离= |(10,0)到(5,5)| * sin(45°) = sqrt(50) * sqrt(2)/2 = 5
    d = _dist_point_to_segment(10, 0, 0, 0, 10, 10)
    assert approx(d, 5), f"diag inner expected 5, got {d}"

    # 6) 投影落在线段左端外侧，应取到左端点距离
    d = _dist_point_to_segment(-5, -5, 0, 0, 10, 0)
    assert approx(d, math.hypot(5, 5)), f"left outer expected {math.hypot(5,5)}, got {d}"

    print("All tests passed.")


if __name__ == "__main__":
    run_tests()
