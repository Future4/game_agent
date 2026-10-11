import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ctypes
import win32gui
import win32con
from ctypes import wintypes


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
    print("=== 坐标系诊断 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 获取DPI
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    # 获取系统DPI
    hdc = user32.GetDC(0)
    LOGPIXELSX = 88
    dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
    user32.ReleaseDC(0, hdc)
    scale_factor = dpi / 96.0
    print(f"\n系统DPI: {dpi}")
    print(f"缩放比例: {scale_factor:.2f} ({int(scale_factor*100)}%)")

    # 获取窗口矩形
    win_rect = win32gui.GetWindowRect(hwnd)
    print(f"\n窗口矩形: {win_rect}")
    print(f"  窗口尺寸: {win_rect[2]-win_rect[0]} x {win_rect[3]-win_rect[1]}")

    # 获取客户区矩形（逻辑像素）
    client_rect = win32gui.GetClientRect(hwnd)
    print(f"\n客户区矩形(逻辑): {client_rect}")
    print(f"  客户区尺寸(逻辑): {client_rect[2]} x {client_rect[3]}")

    # 客户区原点在屏幕上的位置
    client_origin = win32gui.ClientToScreen(hwnd, (0, 0))
    print(f"  客户区原点(屏幕): {client_origin}")

    # 截图尺寸（物理像素）
    # 之前测试截图尺寸是 874x656
    screenshot_w, screenshot_h = 874, 656
    print(f"\n截图尺寸(物理): {screenshot_w} x {screenshot_h}")

    # 计算缩放比例
    scale_x = screenshot_w / client_rect[2] if client_rect[2] > 0 else 1.0
    scale_y = screenshot_h / client_rect[3] if client_rect[3] > 0 else 1.0
    print(f"\n坐标缩放比例:")
    print(f"  X: 截图/客户区 = {screenshot_w}/{client_rect[2]} = {scale_x:.4f}")
    print(f"  Y: 截图/客户区 = {screenshot_h}/{client_rect[3]} = {scale_y:.4f}")

    # 师门任务按钮中心（截图坐标）
    btn_screenshot_x, btn_screenshot_y = 471, 203
    print(f"\n=== 坐标转换示例 ===")
    print(f"师门任务按钮(截图坐标): ({btn_screenshot_x}, {btn_screenshot_y})")

    # 转换为客户区坐标（PostMessage用）
    btn_client_x = int(btn_screenshot_x / scale_x)
    btn_client_y = int(btn_screenshot_y / scale_y)
    print(f"师门任务按钮(客户区坐标): ({btn_client_x}, {btn_client_y})")

    # 转换为屏幕坐标（前台点击用）
    btn_screen = win32gui.ClientToScreen(hwnd, (btn_client_x, btn_client_y))
    print(f"师门任务按钮(屏幕坐标): {btn_screen}")

    print(f"\n=== 结论 ===")
    if abs(scale_x - 1.0) > 0.01 or abs(scale_y - 1.0) > 0.01:
        print(f"⚠ 存在DPI缩放！比例 {scale_x:.2f}x{scale_y:.2f}")
        print(f"  PostMessage需要用客户区坐标: ({btn_client_x}, {btn_client_y})")
        print(f"  截图坐标需要除以 {scale_x:.2f} 才能得到客户区坐标")
    else:
        print("无DPI缩放，坐标一致")


if __name__ == "__main__":
    main()