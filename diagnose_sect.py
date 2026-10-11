import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
import cv2
import win32gui
import time
import msvcrt
import ctypes
import numpy as np

SCREENSHOT_OFFSET = (-11, -39)

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]


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


def match_template(img, template_path, threshold=0.8):
    if not os.path.exists(template_path):
        return None
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        return None
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        h, w = template.shape[:2]
        return {
            'x': max_loc[0], 'y': max_loc[1],
            'width': w, 'height': h,
            'confidence': max_val,
            'center': (max_loc[0] + w // 2, max_loc[1] + h // 2)
        }
    return None


def get_cursor_client_pos(hwnd):
    """获取鼠标在客户区的坐标"""
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    client_pos = win32gui.ScreenToClient(hwnd, (point.x, point.y))
    # 转换为截图坐标
    sx = client_pos[0] - SCREENSHOT_OFFSET[0]
    sy = client_pos[1] - SCREENSHOT_OFFSET[1]
    return (sx, sy)


def wait_cursor_confirm(hwnd, label):
    """等待用户移动鼠标到目标位置并按回车"""
    print(f"\n  请将鼠标移到游戏中的【{label}】上，按回车确认")
    while True:
        sx, sy = get_cursor_client_pos(hwnd)
        print(f"\r  鼠标截图坐标: ({sx:4d}, {sy:4d})  按回车确认", end="", flush=True)
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\r':
                print()
                return (sx, sy)
        time.sleep(0.1)


def main():
    print("=== 师门任务位置诊断 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    screenshot = ScreenshotCapture()

    # 截图
    print("\n3秒后截图...")
    time.sleep(3)
    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败")
        return

    print(f"截图尺寸: {img.shape[1]}x{img.shape[0]}")

    # 匹配师门选择界面
    option_match = match_template(img, os.path.join("templates", "sect_option_page.png"), 0.7)
    if option_match:
        print(f"\n师门选择界面: 位置({option_match['x']},{option_match['y']}) 尺寸{option_match['width']}x{option_match['height']} 置信度{option_match['confidence']:.3f}")
    else:
        print("\n未找到师门选择界面模板")

    # 匹配赐教任务
    task_match = match_template(img, os.path.join("templates", "cijiao_task.png"), 0.6)
    if task_match:
        print(f"赐教任务: 位置({task_match['x']},{task_match['y']}) 尺寸{task_match['width']}x{task_match['height']} 置信度{task_match['confidence']:.3f}")
    else:
        print("未找到赐教任务模板")

    # 用户手动确认勾选框位置
    checkbox_pos = wait_cursor_confirm(hwnd, "自动完成任务勾选框")
    print(f"  ✓ 勾选框截图坐标: ({checkbox_pos[0]}, {checkbox_pos[1]})")

    # 用户手动确认任务按钮位置
    button_pos = wait_cursor_confirm(hwnd, "赐教任务下方的按钮")
    print(f"  ✓ 任务按钮截图坐标: ({button_pos[0]}, {button_pos[1]})")

    # 计算相对偏移
    print("\n=== 诊断结果 ===")
    if option_match:
        print(f"\n师门选择界面: ({option_match['x']},{option_match['y']}) 尺寸{option_match['width']}x{option_match['height']}")
        print(f"  勾选框相对界面偏移: ({checkbox_pos[0] - option_match['x']}, {checkbox_pos[1] - option_match['y']})")

    if task_match:
        task_bottom = task_match['y'] + task_match['height']
        task_cx = task_match['x'] + task_match['width'] // 2
        print(f"\n赐教任务: ({task_match['x']},{task_match['y']}) 尺寸{task_match['width']}x{task_match['height']}")
        print(f"  任务底部: y={task_bottom}")
        print(f"  任务中心x: {task_cx}")
        print(f"  按钮相对任务底部偏移: ({button_pos[0] - task_cx}, {button_pos[1] - task_bottom})")

    # 在截图上标注
    annotated = img.copy()

    # 标注师门选择界面
    if option_match:
        cv2.rectangle(annotated,
                      (option_match['x'], option_match['y']),
                      (option_match['x'] + option_match['width'], option_match['y'] + option_match['height']),
                      (0, 255, 0), 2)
        cv2.putText(annotated, "option_page", (option_match['x'], option_match['y'] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # 标注赐教任务
    if task_match:
        cv2.rectangle(annotated,
                      (task_match['x'], task_match['y']),
                      (task_match['x'] + task_match['width'], task_match['y'] + task_match['height']),
                      (255, 255, 0), 2)
        cv2.putText(annotated, "cijiao_task", (task_match['x'], task_match['y'] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    # 标注勾选框（蓝色十字）
    cv2.drawMarker(annotated, checkbox_pos, (255, 0, 0), cv2.MARKER_CROSS, 20, 2)
    cv2.putText(annotated, "checkbox", (checkbox_pos[0] + 10, checkbox_pos[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    # 标注任务按钮（红色十字）
    cv2.drawMarker(annotated, button_pos, (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
    cv2.putText(annotated, "task_button", (button_pos[0] + 10, button_pos[1]),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    cv2.imwrite("sect_diagnosis.png", annotated)
    print(f"\n标注图已保存: sect_diagnosis.png")
    print(f"  绿色框 = 师门选择界面")
    print(f"  黄色框 = 赐教任务")
    print(f"  蓝色十字 = 勾选框")
    print(f"  红色十字 = 任务按钮")


if __name__ == "__main__":
    main()