import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import numpy as np
import win32gui
import time
import msvcrt

# 截图坐标到客户区坐标的偏移量
SCREENSHOT_OFFSET = (-11, -39)


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


def calc_button_position(module_x, module_y, module_w, module_h,
                         margin_right=10, btn_w=70, btn_h=40):
    """根据模块位置计算按钮位置"""
    module_right = module_x + module_w
    btn_right = module_right - margin_right
    btn_left = btn_right - btn_w
    btn_top = module_y + (module_h - btn_h) // 2
    btn_cx = (btn_left + btn_right) // 2
    btn_cy = btn_top + btn_h // 2
    return (btn_cx, btn_cy)


def match_template(img, template_path, threshold=0.8):
    """模板匹配"""
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
            'x': max_loc[0],
            'y': max_loc[1],
            'width': w,
            'height': h,
            'confidence': max_val,
            'center': (max_loc[0] + w // 2, max_loc[1] + h // 2)
        }
    return None


def wait_for_template(screenshot, hwnd, template_path, timeout=10, interval=0.5,
                      threshold=0.8, label=""):
    """等待模板出现"""
    print(f"  等待[{label}]出现... (超时{timeout}秒)")
    start = time.time()
    while time.time() - start < timeout:
        img = screenshot.capture_to_cv2(hwnd)
        if img is not None:
            match = match_template(img, template_path, threshold)
            if match:
                print(f"  ✓ 找到[{label}] 置信度{match['confidence']:.3f} 耗时{time.time()-start:.1f}秒")
                return match
        time.sleep(interval)
    print(f"  ✗ 超时未找到[{label}]")
    return None


class EscortTask:
    """运镖任务"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"

    def step1_find_escort_module(self):
        """步骤1: 在活动界面找到运镖模块并点击参加"""
        print("\n[步骤1] 查找运镖模块...")

        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print("  截图失败")
            return False

        # 匹配运镖模块
        match = match_template(img, os.path.join(self.templates_dir, "escort_module.png"), 0.8)
        if not match:
            print("  ✗ 未找到运镖模块，请确认在活动界面")
            return False

        print(f"  ✓ 运镖模块: 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']} 置信度{match['confidence']:.3f}")

        # 计算参加按钮位置
        btn_cx, btn_cy = calc_button_position(
            match['x'], match['y'], match['width'], match['height']
        )
        print(f"  参加按钮: ({btn_cx}, {btn_cy})")

        # 点击参加
        print(f"  点击参加按钮...")
        if self.executor.click(btn_cx, btn_cy):
            print(f"  ✓ 点击完成")
            return True
        else:
            print(f"  ✗ 点击失败")
            return False

    def step2_select_escort(self):
        """步骤2: 等待运镖对话出现，选择押送普通镖银"""
        print("\n[步骤2] 等待运镖对话...")

        # 等待运镖对话出现
        match = wait_for_template(
            self.screenshot, self.hwnd,
            os.path.join(self.templates_dir, "escort_ask.png"),
            timeout=10, label="运镖对话"
        )
        if not match:
            print("  运镖对话未出现，请检查")
            return False

        print(f"  运镖对话区域: ({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']}")

        # 截图当前画面，保存供用户查看
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is not None:
            # 在运镖对话区域画框
            cv2.rectangle(img,
                          (match['x'], match['y']),
                          (match['x'] + match['width'], match['y'] + match['height']),
                          (0, 255, 0), 2)
            cv2.imwrite("escort_dialog.png", img)
            print(f"  对话截图已保存: escort_dialog.png")

        # 查找"押送普通镖银"选项
        # 先尝试模板匹配（如果有模板）
        escort_option_path = os.path.join(self.templates_dir, "escort_normal.png")
        if os.path.exists(escort_option_path):
            option_match = match_template(img, escort_option_path, 0.7)
            if option_match:
                print(f"  找到押送普通镖银选项: ({option_match['center'][0]}, {option_match['center'][1]})")
                print(f"  点击选项...")
                self.executor.click(option_match['center'][0], option_match['center'][1])
                return True

        # 没有模板，让用户手动选择
        print("\n  ⚠ 未找到'押送普通镖银'模板")
        print("  请将鼠标移到游戏中的【押送普通镖银】选项上，按回车确认")
        print("  (5秒后开始检测鼠标位置)")

        time.sleep(5)

        # 获取鼠标位置
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]

        while True:
            point = POINT()
            user32.GetCursorPos(ctypes.byref(point))
            client_pos = win32gui.ScreenToClient(self.hwnd, (point.x, point.y))

            # 转换回截图坐标（减去偏移）
            screenshot_x = client_pos[0] - SCREENSHOT_OFFSET[0]
            screenshot_y = client_pos[1] - SCREENSHOT_OFFSET[1]

            print(f"\r  鼠标: 客户区({client_pos[0]:4d},{client_pos[1]:4d}) 截图({screenshot_x:4d},{screenshot_y:4d})  按回车确认", end="", flush=True)

            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b'\r':
                    print()
                    print(f"  点击位置: 截图坐标({screenshot_x}, {screenshot_y})")
                    print(f"  点击中...")
                    self.executor.click(screenshot_x, screenshot_y)
                    print(f"  ✓ 点击完成")
                    return True
            time.sleep(0.1)

    def step3_confirm_escort(self):
        """步骤3: 等待确认界面，点击确定"""
        print("\n[步骤3] 等待确认运镖界面...")

        # 等待是否确认运镖界面出现
        match = wait_for_template(
            self.screenshot, self.hwnd,
            os.path.join(self.templates_dir, "isEscort.png"),
            timeout=10, label="是否确认运镖"
        )
        if not match:
            print("  确认界面未出现，请检查")
            return False

        print(f"  确认界面: ({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']}")

        # 截图保存
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is not None:
            cv2.rectangle(img,
                          (match['x'], match['y']),
                          (match['x'] + match['width'], match['y'] + match['height']),
                          (0, 255, 0), 2)
            cv2.imwrite("escort_confirm.png", img)
            print(f"  确认界面截图已保存: escort_confirm.png")

        # 点击右下方的确定按钮
        # 确定按钮通常在确认界面的右下方
        # 先尝试模板匹配
        confirm_btn_path = os.path.join(self.templates_dir, "confirm_button.png")
        if os.path.exists(confirm_btn_path):
            btn_match = match_template(img, confirm_btn_path, 0.7)
            if btn_match:
                print(f"  找到确定按钮: ({btn_match['center'][0]}, {btn_match['center'][1]})")
                self.executor.click(btn_match['center'][0], btn_match['center'][1])
                return True

        # 没有确定按钮模板，使用相对位置计算
        # 确定按钮通常在确认界面的右下角
        # 假设确定按钮在界面右下角，距离右边界和下边界各一定距离
        confirm_x = match['x'] + match['width'] - 80
        confirm_y = match['y'] + match['height'] - 40
        print(f"  计算确定按钮位置: ({confirm_x}, {confirm_y})")

        print("  ⚠ 如果位置不对，请将鼠标移到【确定】按钮上，按回车确认")
        print("  (3秒后自动点击计算位置，或提前按回车手动确认)")

        auto_click = True
        start = time.time()
        while time.time() - start < 3:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b'\r':
                    import ctypes
                    user32 = ctypes.windll.user32
                    class POINT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
                    point = POINT()
                    user32.GetCursorPos(ctypes.byref(point))
                    client_pos = win32gui.ScreenToClient(self.hwnd, (point.x, point.y))
                    confirm_x = client_pos[0] - SCREENSHOT_OFFSET[0]
                    confirm_y = client_pos[1] - SCREENSHOT_OFFSET[1]
                    auto_click = True
                    break
            time.sleep(0.1)

        if auto_click:
            print(f"  点击确定按钮: ({confirm_x}, {confirm_y})...")
            self.executor.click(confirm_x, confirm_y)
            print(f"  ✓ 点击完成")
            return True

        return False

    def run(self):
        """执行完整运镖流程"""
        print("=" * 50)
        print("运镖任务流程")
        print("=" * 50)
        print("流程: 活动界面 → 运镖参加 → 选择普通镖银 → 确认运镖")
        print(f"偏移量: {SCREENSHOT_OFFSET}")

        print("\n3秒后开始...")
        time.sleep(3)

        # 步骤1: 点击运镖参加
        if not self.step1_find_escort_module():
            print("\n✗ 运镖流程失败: 步骤1")
            return False

        time.sleep(2)

        # 步骤2: 选择押送普通镖银
        if not self.step2_select_escort():
            print("\n✗ 运镖流程失败: 步骤2")
            return False

        time.sleep(2)

        # 步骤3: 确认运镖
        if not self.step3_confirm_escort():
            print("\n✗ 运镖流程失败: 步骤3")
            return False

        print("\n" + "=" * 50)
        print("✓ 运镖任务流程完成！")
        print("=" * 50)
        return True


def main():
    print("=== 运镖任务完整流程测试 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！请先打开游戏。")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 检查模板
    templates_dir = "templates"
    required = {
        "escort_module.png": "运镖模块",
        "escort_ask.png": "运镖对话",
        "isEscort.png": "是否确认运镖",
    }
    print("\n模板检查:")
    for filename, label in required.items():
        path = os.path.join(templates_dir, filename)
        if os.path.exists(path):
            tpl = cv2.imread(path)
            if tpl is not None:
                print(f"  ✓ {label} ({filename}) {tpl.shape[1]}x{tpl.shape[0]}")
            else:
                print(f"  ✗ {label} ({filename}) 加载失败")
        else:
            print(f"  ✗ {label} ({filename}) 不存在")

    # 执行运镖任务
    task = EscortTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()