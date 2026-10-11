import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ctypes
import win32gui
import win32con
import cv2
import time
import msvcrt

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_int


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


def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)


def main():
    print("=== 偏移量诊断 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 模板匹配计算出的按钮坐标
    template_btn = (471, 203)
    print(f"\n模板匹配按钮坐标: ({template_btn[0]}, {template_btn[1]})")

    # 截图并标注
    from core.screenshot import ScreenshotCapture
    screenshot = ScreenshotCapture()
    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败！")
        return

    # 画十字线标注模板匹配位置
    cv2.drawMarker(img, template_btn, (0, 0, 255), cv2.MARKER_CROSS, 30, 3)
    cv2.putText(img, f"template ({template_btn[0]},{template_btn[1]})",
                (template_btn[0] + 20, template_btn[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.imwrite("offset_diagnosis.png", img)
    print(f"标注图已保存: offset_diagnosis.png")

    # 让用户手动定位
    print("\n" + "=" * 50)
    print("请将鼠标移到游戏中【师门任务】的参加按钮上")
    print("然后按回车键确认")
    print("=" * 50)

    while True:
        pos = get_cursor_pos()
        client_pos = win32gui.ScreenToClient(hwnd, pos)
        print(f"\r  鼠标: 屏幕({pos[0]:4d},{pos[1]:4d}) -> 客户区({client_pos[0]:4d},{client_pos[1]:4d})  按回车确认", end="", flush=True)

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\r':
                print()
                actual_btn = client_pos
                break
        time.sleep(0.1)

    # 计算偏移
    offset_x = actual_btn[0] - template_btn[0]
    offset_y = actual_btn[1] - template_btn[1]

    print(f"\n=== 偏移量结果 ===")
    print(f"模板匹配坐标: ({template_btn[0]}, {template_btn[1]})")
    print(f"实际按钮坐标: ({actual_btn[0]}, {actual_btn[1]})")
    print(f"X偏移: {offset_x}")
    print(f"Y偏移: {offset_y}")

    # 在图上同时标注两个位置
    cv2.drawMarker(img, actual_btn, (0, 255, 0), cv2.MARKER_CROSS, 30, 3)
    cv2.putText(img, f"actual ({actual_btn[0]},{actual_btn[1]})",
                (actual_btn[0] + 20, actual_btn[1] + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # 画偏移线
    cv2.arrowedLine(img, template_btn, actual_btn, (255, 0, 0), 2)
    cv2.imwrite("offset_diagnosis.png", img)
    print(f"\n对比图已保存: offset_diagnosis.png")
    print(f"红色十字 = 模板匹配位置")
    print(f"绿色十字 = 实际按钮位置")
    print(f"蓝色箭头 = 偏移方向")

    # 验证其他模块的偏移
    print(f"\n=== 应用偏移量 ===")
    print(f"师门任务按钮: ({template_btn[0]}, {template_btn[1]}) -> ({template_btn[0]+offset_x}, {template_btn[1]+offset_y})")
    print(f"运镖模块按钮: (775, 202) -> ({775+offset_x}, {202+offset_y})")
    print(f"活动界面按钮: (821, 371) -> ({821+offset_x}, {371+offset_y})")


if __name__ == "__main__":
    main()