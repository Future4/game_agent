"""圆形阵法图案检测诊断脚本

用途：检测战斗界面顶部中间的"圆形阵法图案"（不同阵法图案不同，但都是圆形）。
用 HoughCircles 算法 + 位置/半径过滤判断是否在战斗中。

使用方法：
1. 在战斗中运行一次：python diagnose_circle.py
2. 在非战斗中运行一次：python diagnose_circle.py
3. 确认"是否战斗中"判断正确
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
import cv2
import numpy as np
import win32gui


def find_game_window():
    results = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            c = win32gui.GetClassName(hwnd)
            if "梦幻西游" in t or c == "UnityWndClass":
                results.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return results


# 过滤参数（与 is_in_battle 一致）
PARAM1 = 50
PARAM2 = 30
MIN_RADIUS = 10
MAX_RADIUS = 40
# 过滤：阵法图案位置（区域宽度比例）和半径
FILTER_X_MIN_RATIO = 0.55
FILTER_X_MAX_RATIO = 0.85
FILTER_R_MIN = 18
FILTER_R_MAX = 30


def main():
    print("=== 圆形阵法图案检测诊断 ===")
    print("请在战斗中或非战斗中运行，验证战斗检测是否准确")
    print()

    results = find_game_window()
    if not results:
        print("未找到游戏窗口")
        return

    hwnd = results[0][0]
    print(f"窗口: {results[0][1]}")

    sc = ScreenshotCapture()
    img = sc.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败")
        return

    h, w = img.shape[:2]
    print(f"尺寸: {w}x{h}")

    # 顶部中间区域
    x1 = w // 4
    x2 = w * 3 // 4
    region = img[0:100, x1:x2]
    region_w = x2 - x1
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    # 保存区域图
    cv2.imwrite("diag_circle_region.png", region)
    print(f"已保存 diag_circle_region.png (顶部中间 {x1}~{x2}, 高100, 宽{region_w})")

    # HoughCircles 检测
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
        param1=PARAM1, param2=PARAM2,
        minRadius=MIN_RADIUS, maxRadius=MAX_RADIUS
    )

    # 过滤参数
    min_x = region_w * FILTER_X_MIN_RATIO
    max_x = region_w * FILTER_X_MAX_RATIO
    print(f"\n过滤条件: x在[{min_x:.0f},{max_x:.0f}] (区域宽{region_w}的{FILTER_X_MIN_RATIO:.0%}~{FILTER_X_MAX_RATIO:.0%}), "
          f"半径[{FILTER_R_MIN},{FILTER_R_MAX}]")

    all_circles = []
    matched_circles = []
    if circles is not None:
        for c in circles[0]:
            cx, cy, r = c[0], c[1], c[2]
            all_circles.append((cx, cy, r))
            if min_x <= cx <= max_x and FILTER_R_MIN <= r <= FILTER_R_MAX:
                matched_circles.append((cx, cy, r))

    # 输出所有检测到的圆形
    print(f"\n检测到 {len(all_circles)} 个圆形（过滤前）:")
    for i, (cx, cy, r) in enumerate(all_circles):
        x_ratio = cx / region_w
        in_range = "✓" if (min_x <= cx <= max_x and FILTER_R_MIN <= r <= FILTER_R_MAX) else "✗"
        print(f"  圆形{i+1}: 中心({cx:.0f},{cy:.0f}) 半径{r:.0f} x比例{x_ratio:.2f} 过滤{in_range}")

    # 输出过滤后的圆形
    print(f"\n过滤后保留 {len(matched_circles)} 个圆形:")
    for cx, cy, r in matched_circles:
        print(f"  中心({cx:.0f},{cy:.0f}) 半径{r:.0f}")

    # 最终判断
    in_battle = len(matched_circles) > 0
    print(f"\n>>> 判断: {'⚔ 战斗中' if in_battle else '○ 非战斗中'}")

    # 标注图
    annotated = region.copy()
    # 画出过滤范围
    cv2.line(annotated, (int(min_x), 0), (int(min_x), 100), (255, 0, 0), 1)
    cv2.line(annotated, (int(max_x), 0), (int(max_x), 100), (255, 0, 0), 1)
    for cx, cy, r in all_circles:
        cx_i, cy_i, r_i = int(cx), int(cy), int(r)
        if (cx, cy, r) in matched_circles:
            cv2.circle(annotated, (cx_i, cy_i), r_i, (0, 255, 0), 2)  # 绿色=匹配
            cv2.circle(annotated, (cx_i, cy_i), 2, (0, 0, 255), 3)
        else:
            cv2.circle(annotated, (cx_i, cy_i), r_i, (0, 0, 255), 1)  # 红色=过滤掉
    cv2.imwrite("diag_circle_annotated.png", annotated)
    print(f"\n已保存 diag_circle_annotated.png (绿色=匹配, 红色=过滤掉, 蓝线=x范围)")


if __name__ == "__main__":
    main()
