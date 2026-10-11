import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import win32gui
import time
import msvcrt
import ctypes

# 截图坐标到客户区坐标的偏移量
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


def calc_button_position(module_x, module_y, module_w, module_h,
                         margin_right=10, btn_w=70, btn_h=40):
    """根据模块位置计算按钮位置（右边界偏移）"""
    module_right = module_x + module_w
    btn_right = module_right - margin_right
    btn_left = btn_right - btn_w
    btn_top = module_y + (module_h - btn_h) // 2
    btn_cx = (btn_left + btn_right) // 2
    btn_cy = btn_top + btn_h // 2
    return (btn_cx, btn_cy)


def match_template(img, template_path, threshold=0.8):
    """多尺度模板匹配，兼容 Windows DPI/游戏窗口缩放。"""
    if not os.path.exists(template_path):
        return None
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        return None

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    best = None
    for scale in (0.50, 0.60, 0.75, 0.85, 1.0, 1.15, 1.30, 1.50, 1.75, 2.0):
        h0, w0 = tpl_gray.shape[:2]
        resized = cv2.resize(tpl_gray, (max(1, int(w0 * scale)), max(1, int(h0 * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        h, w = resized.shape[:2]
        if h > img_gray.shape[0] or w > img_gray.shape[1]:
            continue
        result = cv2.matchTemplate(img_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        candidate = {'x': loc[0], 'y': loc[1], 'width': w, 'height': h,
                     'confidence': float(score), 'scale': scale,
                     'center': (loc[0] + w // 2, loc[1] + h // 2)}
        if best is None or candidate['confidence'] > best['confidence']:
            best = candidate
    print(f"  模板最佳匹配: {os.path.basename(template_path)} {best}")
    return best if best and best['confidence'] >= threshold else None


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


def wait_for_cursor_confirm(hwnd, label="目标"):
    """等待用户手动确认鼠标位置"""
    print(f"\n  ⚠ 请将鼠标移到游戏中的【{label}】上，按回车确认")
    while True:
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        client_pos = win32gui.ScreenToClient(hwnd, (point.x, point.y))
        # 转换回截图坐标
        sx = client_pos[0] - SCREENSHOT_OFFSET[0]
        sy = client_pos[1] - SCREENSHOT_OFFSET[1]
        print(f"\r  鼠标: 客户区({client_pos[0]:4d},{client_pos[1]:4d}) 截图({sx:4d},{sy:4d})  按回车确认", end="", flush=True)

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\r':
                print()
                return (sx, sy)
        time.sleep(0.1)


class TreasureMapTask:
    """宝图任务"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"

    def step1_find_treasure_module(self):
        """步骤1: 在活动界面找到宝图任务模块并点击参加"""
        print("\n[步骤1] 查找宝图任务模块...")

        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print("  截图失败")
            return False

        tpl_path = os.path.join(self.templates_dir, "baotu_module.png")
        match = match_template(img, tpl_path, 0.8)
        if not match:
            os.makedirs("debug", exist_ok=True)
            debug_path = os.path.abspath("debug/activity_no_baotu_module.png")
            cv2.imwrite(debug_path, img)
            print(f"  ✗ 未达到匹配阈值，当前截图已保存: {debug_path}")
            return False

        print(f"  ✓ 宝图任务模块: 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']} 置信度{match['confidence']:.3f}")

        # 计算参加按钮位置
        btn_cx, btn_cy = calc_button_position(
            match['x'], match['y'], match['width'], match['height']
        )
        # 参加按钮尺寸估计
        btn_w, btn_h = 70, 40
        print(f"  参加按钮: 中心({btn_cx}, {btn_cy}) 尺寸{btn_w}x{btn_h}")

        # 拟人化点击参加
        print(f"  拟人化点击参加按钮...")
        if self.executor.click_human(btn_cx, btn_cy, btn_w, btn_h):
            print(f"  ✓ 点击完成")
            return True
        else:
            print(f"  ✗ 点击失败")
            return False

    def step2_select_listen(self):
        """步骤2: 等待宝图对话出现，选择听听无妨"""
        print("\n[步骤2] 等待宝图对话...")

        # 等待宝图对话出现
        match = wait_for_template(
            self.screenshot, self.hwnd,
            os.path.join(self.templates_dir, "baotu_dialogue.png"),
            timeout=40, label="宝图对话"
        )
        if not match:
            print("  宝图对话未出现，请检查")
            return False

        print(f"  宝图对话区域: ({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']}")

        # 截图保存
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is not None:
            cv2.rectangle(img,
                          (match['x'], match['y']),
                          (match['x'] + match['width'], match['y'] + match['height']),
                          (0, 255, 0), 2)
            cv2.imwrite("treasure_dialog.png", img)
            print(f"  对话截图已保存: treasure_dialog.png")

        # 尝试模板匹配"听听无妨"选项
        listen_tpl = os.path.join(self.templates_dir, "listen_option.png")
        if os.path.exists(listen_tpl):
            option = match_template(img, listen_tpl, 0.7)
            if option:
                print(f"  找到听听无妨选项: 中心({option['center'][0]}, {option['center'][1]}) 尺寸{option['width']}x{option['height']}")
                self.executor.click_human(option['center'][0], option['center'][1], option['width'], option['height'])
                print(f"  ✓ 点击完成")
                return True

        # 无模板，用对话区域相对偏移计算"听听无妨"位置
        # 实测偏移: 选项中心在对话区域 (107, 24) 处
        LISTEN_OFFSET_X = 107
        LISTEN_OFFSET_Y = 24
        listen_x = match['x'] + LISTEN_OFFSET_X
        listen_y = match['y'] + LISTEN_OFFSET_Y
        # 听听无妨选项尺寸估计
        listen_w, listen_h = 100, 30
        print(f"  听听无妨位置: 中心({listen_x}, {listen_y}) 尺寸{listen_w}x{listen_h} [对话区域+偏移({LISTEN_OFFSET_X},{LISTEN_OFFSET_Y})]")

        print(f"  拟人化点击听听无妨...")
        self.executor.click_human(listen_x, listen_y, listen_w, listen_h)
        print(f"  ✓ 点击完成")
        return True

    def run(self):
        """执行完整宝图流程"""
        print("=" * 50)
        print("宝图任务流程")
        print("=" * 50)
        print("流程: 活动界面 → 宝图参加 → 选择听听无妨 → 自动执行")
        print(f"偏移量: {SCREENSHOT_OFFSET}")

        print("\n3秒后开始...")
        time.sleep(3)

        # 步骤1: 点击宝图参加
        if not self.step1_find_treasure_module():
            print("\n✗ 宝图流程失败: 步骤1")
            return False

        time.sleep(2)

        # 步骤2: 选择听听无妨
        if not self.step2_select_listen():
            print("\n✗ 宝图流程失败: 步骤2")
            return False

        print("\n" + "=" * 50)
        print("✓ 宝图任务流程完成！游戏将自动执行宝图获取。")
        print("=" * 50)
        return True


def main():
    print("=== 宝图任务完整流程测试 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！请先打开游戏。")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 检查模板
    templates_dir = "templates"
    required = {
        "baotu_module.png": "宝图任务模块",
        "baotu_dialogue.png": "宝图对话",
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

    # 执行宝图任务
    task = TreasureMapTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()
