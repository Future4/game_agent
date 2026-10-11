"""诊断脚本：截取游戏左上角区域，帮助确认坐标显示位置"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
import cv2
import win32gui

def find_game_window():
    results = []
    def callback(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or class_name == "UnityWndClass"):
            rect = win32gui.GetWindowRect(hwnd)
            if rect[2] - rect[0] > 100 and rect[3] - rect[1] > 100:
                results.append({'hwnd': hwnd, 'title': title, 'rect': rect})
    win32gui.EnumWindows(callback, None)
    return results


windows = find_game_window()
if not windows:
    print("未找到游戏窗口！")
    exit()

hwnd = windows[0]['hwnd']
print(f"游戏窗口: {windows[0]['title']}")

screenshot = ScreenshotCapture()
img = screenshot.capture_to_cv2(hwnd)
if img is None:
    print("截图失败！")
    exit()

h, w = img.shape[:2]
print(f"截图尺寸: {w}x{h}")

# 截取左上角区域并保存（覆盖各种可能的坐标显示位置）
# 区域1: 左上角 0~200, 0~60
top_left_1 = img[0:60, 0:200]
cv2.imwrite("diag_topleft_1.png", top_left_1)
print(f"✓ 已保存 diag_topleft_1.png (0,0)~(200,60)")

# 区域2: 左上角稍大 0~300, 0~80
top_left_2 = img[0:80, 0:300]
cv2.imwrite("diag_topleft_2.png", top_left_2)
print(f"✓ 已保存 diag_topleft_2.png (0,0)~(300,80)")

# 全图也保存一份（缩小）
small = cv2.resize(img, (w//2, h//2))
cv2.imwrite("diag_full_small.png", small)
print(f"✓ 已保存 diag_full_small.png (缩小版全图)")

# 在全图上画出左上角区域的框
annotated = img.copy()
cv2.rectangle(annotated, (0, 0), (200, 60), (0, 255, 0), 2)
cv2.rectangle(annotated, (0, 0), (300, 80), (0, 255, 255), 2)
cv2.imwrite("diag_annotated.png", annotated)
print(f"✓ 已保存 diag_annotated.png (标注版)")

print("\n请查看 diag_topleft_1.png 和 diag_topleft_2.png")
print("告诉我在图中哪个位置显示了地图坐标（如 105,35）")
print("或者直接告诉我坐标文字在截图中的大概像素位置")
