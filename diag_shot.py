"""快速截图脚本"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.screenshot import ScreenshotCapture
import cv2, win32gui

results = []
def cb(hwnd, _):
    if win32gui.IsWindowVisible(hwnd):
        t = win32gui.GetWindowText(hwnd)
        c = win32gui.GetClassName(hwnd)
        if "梦幻西游" in t or c == "UnityWndClass":
            results.append((hwnd, t))
win32gui.EnumWindows(cb, None)

if not results:
    print("未找到游戏窗口")
    exit()

hwnd = results[0][0]
print(f"窗口: {results[0][1]}")

sc = ScreenshotCapture()
img = sc.capture_to_cv2(hwnd)
if img is None:
    print("截图失败")
    exit()

h, w = img.shape[:2]
print(f"尺寸: {w}x{h}")

# 保存全图
cv2.imwrite("diag_full.png", img)
print("已保存 diag_full.png")

# 左上角区域
crop = img[0:80, 0:300]
cv2.imwrite("diag_topleft.png", crop)
print("已保存 diag_topleft.png (0,0)~(300,80)")
