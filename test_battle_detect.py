"""实时战斗状态检测脚本

循环检测当前是否在战斗中，按Ctrl+C退出。
用于验证 is_in_battle 的三组HoughCircles参数一致性判断是否准确。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
import cv2
import numpy as np
import win32gui
import time


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


def detect_battle(img):
    """三组HoughCircles参数一致性判断（与is_in_battle相同逻辑）"""
    if img is None:
        return False, [], []

    h, w = img.shape[:2]
    x1 = w // 4
    x2 = w * 3 // 4
    region = img[0:100, x1:x2]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    params_list = [
        (50, 30, 10, 40),
        (50, 25, 8, 35),
        (40, 20, 10, 40),
    ]

    all_circles = []
    results = []
    for p1, p2, minr, maxr in params_list:
        circles = cv2.HoughCircles(
            blur, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
            param1=p1, param2=p2, minRadius=minr, maxRadius=maxr
        )
        if circles is None or len(circles[0]) == 0:
            all_circles.append([])
            results.append(0)
            continue
        all_circles.append(circles[0])
        results.append(len(circles[0]))

    # 条件1: 三组都检测到圆形
    if any(c == 0 for c in results):
        return False, results, all_circles

    # 条件2: 三组圆形数量一致
    if results[0] != results[1] or results[0] != results[2]:
        return False, results, all_circles

    # 条件3&4: 三组第一个圆形位置和半径接近
    c1, c2, c3 = all_circles[0][0], all_circles[1][0], all_circles[2][0]
    pos_threshold = 10
    radius_threshold = 5

    pos_close = (abs(c1[0]-c2[0]) < pos_threshold and abs(c1[1]-c2[1]) < pos_threshold and
                 abs(c1[0]-c3[0]) < pos_threshold and abs(c1[1]-c3[1]) < pos_threshold)
    radius_close = (abs(c1[2]-c2[2]) < radius_threshold and abs(c1[2]-c3[2]) < radius_threshold)

    return (pos_close and radius_close), results, all_circles


def main():
    print("=== 实时战斗状态检测 ===")
    print("循环检测战斗状态，按Ctrl+C退出")
    print()

    results = find_game_window()
    if not results:
        print("未找到游戏窗口")
        return

    hwnd = results[0][0]
    print(f"窗口: {results[0][1]}")

    sc = ScreenshotCapture()

    try:
        while True:
            img = sc.capture_to_cv2(hwnd)
            in_battle, counts, all_circles = detect_battle(img)

            status = "⚔ 战斗中" if in_battle else "○ 非战斗中"
            # 三组检测详情
            details = []
            for i, cnt in enumerate(counts):
                if cnt > 0 and len(all_circles[i]) > 0:
                    c = all_circles[i][0]
                    details.append(f"组{i+1}:{cnt}个 首圆({c[0]:.0f},{c[1]:.0f})r{c[2]:.0f}")
                else:
                    details.append(f"组{i+1}:0个")

            print(f"\r{status} | {' | '.join(details)}", end="", flush=True)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n已退出检测")


if __name__ == "__main__":
    main()
