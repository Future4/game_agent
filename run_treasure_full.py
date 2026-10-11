"""宝图任务 + 挖宝 完整自动化流程

流程：
1. 宝图任务循环（最多10次）
   - 活动界面 → 点击参加 → 听听无妨 → 战斗 → 回到活动界面
   - 检测宝图模块底部完成次数
2. 10次完成后 → 自动挖宝
   - 打开背包 → 找藏宝图 → 使用 → 走到地点 → 循环挖宝
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
from run_treasure_task import TreasureMapTask
from run_dig_task import DigTask
import cv2
import win32gui
import time
import ctypes

SCREENSHOT_OFFSET = (-11, -39)

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


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


class TreasureFullTask:
    """宝图任务 + 挖宝 完整流程"""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"
        self.treasure_task = TreasureMapTask(hwnd)
        self.max_baotu_rounds = 10  # 宝图任务最多10次

    def is_at_activity_page(self):
        """检测是否在活动界面（宝图模块可见）"""
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            return False
        tpl_path = os.path.join(self.templates_dir, "baotu_module.png")
        match = match_template(img, tpl_path, 0.8)
        return match is not None

    def wait_activity_page(self, timeout=300, interval=3):
        """等待回到活动界面（战斗结束后）

        Args:
            timeout: 超时秒数（战斗可能较久，默认300秒=5分钟）
        """
        print(f"  等待回到活动界面... (超时{timeout}秒)")
        start = time.time()
        while time.time() - start < timeout:
            if self.is_at_activity_page():
                elapsed = time.time() - start
                print(f"  ✓ 已回到活动界面 (耗时{elapsed:.0f}秒)")
                return True
            time.sleep(interval)
        print(f"  ✗ 超时未回到活动界面")
        return False

    def run_baotu_rounds(self):
        """执行宝图任务循环（10次）"""
        print("\n" + "=" * 60)
        print("阶段1: 宝图任务（10次战斗）")
        print("=" * 60)

        for round_num in range(1, self.max_baotu_rounds + 1):
            print(f"\n{'='*40}")
            print(f"宝图任务 第 {round_num}/{self.max_baotu_rounds} 轮")
            print(f"{'='*40}")

            # 步骤1: 点击宝图参加
            print(f"\n[步骤1] 点击宝图参加...")
            if not self.treasure_task.step1_find_treasure_module():
                print(f"  ✗ 第{round_num}轮参加失败，可能任务已完成")
                # 检查是否在活动界面
                if self.is_at_activity_page():
                    print("  当前在活动界面，可能宝图次数已用完")
                    break
                # 不在活动界面，可能在战斗中，等待
                if not self.wait_activity_page(timeout=300):
                    print("  ✗ 无法回到活动界面，终止宝图任务")
                    break
                continue

            time.sleep(2)

            # 步骤2: 选择听听无妨
            print(f"\n[步骤2] 选择听听无妨...")
            if not self.treasure_task.step2_select_listen():
                print(f"  ✗ 第{round_num}轮对话失败")
                continue

            # 步骤3: 等待战斗完成，回到活动界面
            print(f"\n[步骤3] 等待战斗完成，回到活动界面...")
            if not self.wait_activity_page(timeout=300):
                print(f"  ✗ 第{round_num}轮战斗超时")
                break

            print(f"\n✓ 第{round_num}轮宝图任务完成！")
            time.sleep(2)

        print(f"\n{'='*60}")
        print(f"✓ 宝图任务阶段完成！")
        print(f"{'='*60}")

    def run(self):
        """执行完整流程：宝图任务 → 挖宝"""
        print("=" * 60)
        print("宝图任务 + 挖宝 完整自动化流程")
        print("=" * 60)
        print(f"流程: 宝图任务x10 → 挖宝")
        print(f"偏移量: {SCREENSHOT_OFFSET}")

        print("\n3秒后开始...")
        time.sleep(3)

        # 阶段1: 宝图任务循环
        self.run_baotu_rounds()

        # 阶段2: 挖宝
        print("\n" + "=" * 60)
        print("阶段2: 自动挖宝")
        print("=" * 60)
        print("等待5秒后开始挖宝...")
        time.sleep(5)

        dig_task = DigTask(self.hwnd)
        dig_task.run()

        print("\n" + "=" * 60)
        print("✓ 完整流程结束！")
        print("=" * 60)


def main():
    print("=== 宝图任务 + 挖宝 完整流程 ===")

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
        "bag_btn.png": "包裹按钮",
        "treasure_map_icon.png": "藏宝图图标",
        "use_dialog1.png": "使用对话框(图2)",
        "use_btn1.png": "使用按钮1",
        "use_dialog2.png": "使用对话框(图3)",
        "use_btn2.png": "使用按钮2",
    }
    print("\n模板检查:")
    all_ok = True
    for filename, label in required.items():
        path = os.path.join(templates_dir, filename)
        if os.path.exists(path):
            tpl = cv2.imread(path)
            if tpl is not None:
                print(f"  ✓ {label} ({filename}) {tpl.shape[1]}x{tpl.shape[0]}")
            else:
                print(f"  ✗ {label} ({filename}) 加载失败")
                all_ok = False
        else:
            print(f"  ✗ {label} ({filename}) 不存在")
            all_ok = False

    if not all_ok:
        print("\n⚠ 部分模板缺失，请先制作模板！")
        return

    # 确认
    print("\n" + "=" * 60)
    print("即将执行完整流程：")
    print("  1. 宝图任务 x10（约30-50分钟）")
    print("  2. 自动挖宝（约10-20分钟）")
    print("请确保：")
    print("  - 游戏在活动界面")
    print("  - 宝图任务次数未用完")
    print("  - 背包有足够空间")
    print("=" * 60)
    input("\n按回车开始...")

    # 执行完整流程
    task = TreasureFullTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()
