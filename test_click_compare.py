import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import win32gui
import time


def find_game_window():
    target_windows = []
    def callback(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or class_name == "UnityWndClass"):
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] - rect[0] > 100 and rect[3] - rect[1] > 100:
                target_windows.append({'hwnd': hwnd, 'title': title, 'rect': rect})
        return True
    win32gui.EnumWindows(callback, None)
    return target_windows


def main():
    print("=== 前台vs后台点击对比测试 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    screenshot = ScreenshotCapture()

    # 师门任务按钮坐标（截图/客户区坐标）
    btn_x, btn_y = 471, 203
    print(f"目标按钮坐标: ({btn_x}, {btn_y})")

    # 转换为屏幕坐标
    screen_pos = win32gui.ClientToScreen(hwnd, (btn_x, btn_y))
    print(f"屏幕坐标: {screen_pos}")

    # 截图before
    print("\n截图 before...")
    img_before = screenshot.capture_to_cv2(hwnd)
    if img_before is None:
        print("截图失败！")
        return

    # 在before图上标注按钮位置
    img_marked = img_before.copy()
    cv2.circle(img_marked, (btn_x, btn_y), 10, (0, 0, 255), -1)
    cv2.putText(img_marked, f"target ({btn_x},{btn_y})", (btn_x + 15, btn_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imwrite("click_test_before.png", img_marked)
    print("before截图已保存: click_test_before.png")

    # 测试1: 前台点击
    print("\n=== 测试1: 前台点击 ===")
    print("3秒后前台点击...（请不要移动鼠标）")
    time.sleep(3)

    executor_fg = ActionExecutor(hwnd, mode="foreground")
    result = executor_fg.click(btn_x, btn_y)
    print(f"  前台点击返回: {result}")

    time.sleep(1)

    # 截图after (前台)
    img_after_fg = screenshot.capture_to_cv2(hwnd)
    if img_after_fg is not None:
        cv2.imwrite("click_test_after_foreground.png", img_after_fg)
        print("  after截图已保存: click_test_after_foreground.png")

    # 测试2: 后台点击
    print("\n=== 测试2: 后台点击(PostMessage) ===")
    print("3秒后后台点击...")
    time.sleep(3)

    executor_bg = ActionExecutor(hwnd, mode="background")
    result = executor_bg.click(btn_x, btn_y)
    print(f"  后台点击返回: {result}")

    time.sleep(1)

    # 截图after (后台)
    img_after_bg = screenshot.capture_to_cv2(hwnd)
    if img_after_bg is not None:
        cv2.imwrite("click_test_after_background.png", img_after_bg)
        print("  after截图已保存: click_test_after_background.png")

    # 对比
    print("\n=== 结果对比 ===")
    print("请查看以下图片对比：")
    print("  1. click_test_before.png - 点击前（红点标注目标位置）")
    print("  2. click_test_after_foreground.png - 前台点击后")
    print("  3. click_test_after_background.png - 后台点击后")
    print("\n请告诉：")
    print("  - 前台点击后游戏画面是否有变化？")
    print("  - 后台点击后游戏画面是否有变化？")


if __name__ == "__main__":
    main()