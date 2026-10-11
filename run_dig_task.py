import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import numpy as np
import win32gui
import time
import ctypes

SCREENSHOT_OFFSET = (-11, -39)

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]


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


def wait_for_template(screenshot, hwnd, template_path, timeout=30, interval=1, threshold=0.8, label=""):
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


class DigTask:
    """自动挖宝任务"""

    # 游戏内地图坐标显示区域（与宝图任务一致）
    STABLE_CHECK_X = 47
    STABLE_CHECK_Y = 36
    STABLE_CHECK_W = 49
    STABLE_CHECK_H = 19
    STABLE_DURATION = 15      # 挖宝场景：坐标稳定15秒判定角色停住（比宝图任务30秒短）
    STABLE_PIXEL_DIFF_THRESHOLD = 5

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"
        self.baotu_count = 10  # 初始宝图数量

    def click_template(self, template_name, threshold=0.7, search_in=None, humanize=True):
        """匹配模板并点击其中心（支持拟人化）"""
        tpl_path = os.path.join(self.templates_dir, template_name)
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print(f"  ✗ 截图失败")
            return False

        target = img
        if search_in:
            x, y, w, h = search_in
            target = img[y:y+h, x:x+w]

        match = match_template(target, tpl_path, threshold)
        if not match:
            return False

        cx = match['center'][0] + (search_in[0] if search_in else 0)
        cy = match['center'][1] + (search_in[1] if search_in else 0)
        print(f"  匹配[{template_name}]: 位置({cx},{cy}) 置信度{match['confidence']:.3f}")

        if humanize:
            self.executor.click_human(cx, cy, match['width'], match['height'])
        else:
            self.executor.click(cx, cy)
        return True

    def _crop_coord_region(self, img):
        """从已截图中裁取游戏内坐标显示区域（左上角）"""
        if img is None:
            return None
        h, w = img.shape[:2]
        x1, y1 = self.STABLE_CHECK_X, self.STABLE_CHECK_Y
        x2, y2 = x1 + self.STABLE_CHECK_W, y1 + self.STABLE_CHECK_H
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        region = img[y1:y2, x1:x2]
        return cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    def _calc_region_diff(self, region1, region2):
        """计算两个区域的像素差均值"""
        if region1 is None or region2 is None:
            return float('inf')
        if region1.shape != region2.shape:
            return float('inf')
        diff = cv2.absdiff(region1, region2)
        return float(np.mean(diff))

    def step1_open_bag(self):
        """步骤1: 点击包裹按钮打开物品栏"""
        print("\n[步骤1] 点击包裹按钮...")
        if self.click_template("bag_btn.png", 0.7):
            print("  ✓ 包裹已打开")
            time.sleep(1)
            return True
        print("  ✗ 未找到包裹按钮")
        return False

    def step2_find_treasure_map(self):
        """步骤2: 在背包中找到藏宝图"""
        print("\n[步骤2] 查找藏宝图...")
        tpl_path = os.path.join(self.templates_dir, "treasure_map_icon.png")

        for attempt in range(5):
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                time.sleep(0.5)
                continue

            match = match_template(img, tpl_path, 0.6)
            if match:
                cx, cy = match['center']
                print(f"  ✓ 找到藏宝图: ({cx},{cy}) 置信度{match['confidence']:.3f}")
                self.executor.click_human(cx, cy, match['width'], match['height'])
                return True

            # 尝试滚动背包
            if attempt < 3:
                print(f"  未找到藏宝图，尝试滚动背包... (尝试{attempt+1}/5)")
                self.executor.hotkey('pgdn')
                time.sleep(0.5)
            else:
                print(f"  ✗ 未找到藏宝图，可能已用完")
                return False

        return False

    def step3_use_from_bag(self):
        """步骤3: 点击藏宝图后的对话框 → 使用"""
        print("\n[步骤3] 使用藏宝图...")
        dialog_path = os.path.join(self.templates_dir, "use_dialog1.png")
        btn_path = os.path.join(self.templates_dir, "use_btn1.png")

        # 等待对话框出现
        match = wait_for_template(
            self.screenshot, self.hwnd, dialog_path,
            timeout=5, label="使用对话框(图2)", threshold=0.6
        )
        if not match:
            print("  ✗ 对话框未出现")
            return False

        dx, dy, dw, dh = match['x'], match['y'], match['width'], match['height']

        # 查找使用按钮
        img = self.screenshot.capture_to_cv2(self.hwnd)
        btn_match = match_template(img, btn_path, 0.6)

        if btn_match:
            bx, by = btn_match['center']
            bw, bh = btn_match['width'], btn_match['height']
            print(f"  ✓ 找到使用按钮: ({bx},{by}) 尺寸{bw}x{bh}")
        else:
            # 按钮模板未匹配，用对话框右下角位置
            bx = dx + dw - 50
            by = dy + dh - 20
            bw, bh = 80, 30
            print(f"  未匹配使用按钮，用对话框右下角: ({bx},{by})")

        print(f"  点击使用按钮...")
        self.executor.click_human(bx, by, bw, bh)
        print(f"  ✓ 已点击使用")
        time.sleep(2)
        return True

    def step4_wait_walk(self, timeout=120):
        """步骤4: 等待角色走到挖宝地点（可能遇到战斗）"""
        print(f"\n[步骤4] 等待角色走到地点... (超时{timeout}秒，含战斗时间)")

        dialog2_path = os.path.join(self.templates_dir, "use_dialog2.png")
        start = time.time()

        while time.time() - start < timeout:
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                time.sleep(1)
                continue

            # 检查是否到达地点（对话框2出现）
            match = match_template(img, dialog2_path, 0.6)
            if match:
                print(f"  ✓ 已到达地点！耗时{time.time()-start:.1f}秒")
                return True

            time.sleep(1)

        print(f"  ✗ 超时未到达地点")
        return False

    def step5_use_at_location(self):
        """步骤5: 在地点使用藏宝图"""
        print("\n[步骤5] 在地点使用藏宝图...")
        dialog_path = os.path.join(self.templates_dir, "use_dialog2.png")
        btn_path = os.path.join(self.templates_dir, "use_btn2.png")

        # 再次截图找按钮
        img = self.screenshot.capture_to_cv2(self.hwnd)
        btn_match = match_template(img, btn_path, 0.6)

        if btn_match:
            bx, by = btn_match['center']
            bw, bh = btn_match['width'], btn_match['height']
            print(f"  ✓ 找到使用按钮: ({bx},{by}) 尺寸{bw}x{bh}")
        else:
            # 按钮模板未匹配，用对话框中心偏下
            dialog_match = match_template(img, dialog_path, 0.6)
            if dialog_match:
                bx = dialog_match['x'] + dialog_match['width'] // 2
                by = dialog_match['y'] + dialog_match['height'] * 2 // 3
                bw, bh = 80, 30
                print(f"  未匹配按钮模板，用对话框偏下位置: ({bx},{by})")
            else:
                print("  ✗ 未找到对话框")
                return False

        print(f"  点击使用...")
        self.executor.click_human(bx, by, bw, bh)
        print(f"  ✓ 已使用，等待挖宝动画...")
        time.sleep(3)
        return True

    def step5_use_and_wait_next(self):
        """在地点使用藏宝图，并等待下一地点对话框（循环挖宝）"""
        print("\n[步骤5] 检测地点对话框并使用...")
        dialog_path = os.path.join(self.templates_dir, "use_dialog2.png")
        btn_path = os.path.join(self.templates_dir, "use_btn2.png")

        # 截图找对话框
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            return False

        # 匹配对话框
        dialog_match = match_template(img, dialog_path, 0.6)
        if not dialog_match:
            # 等待对话框出现（含战斗+行走时间）
            dialog_match = wait_for_template(
                self.screenshot, self.hwnd, dialog_path,
                timeout=180, label="地点对话框", threshold=0.6
            )
            if not dialog_match:
                print("  ✗ 超时未出现对话框，宝图可能已用完")
                return None
            # 重新截图
            img = self.screenshot.capture_to_cv2(self.hwnd)

        print(f"  ✓ 找到地点对话框: ({dialog_match['x']},{dialog_match['y']}) 置信度{dialog_match['confidence']:.3f}")

        # 查找使用按钮
        btn_match = match_template(img, btn_path, 0.6)
        if btn_match:
            bx, by = btn_match['center']
            bw, bh = btn_match['width'], btn_match['height']
            print(f"  ✓ 找到使用按钮: ({bx},{by}) 尺寸{bw}x{bh}")
        else:
            bx = dialog_match['x'] + dialog_match['width'] // 2
            by = dialog_match['y'] + dialog_match['height'] * 2 // 3
            bw, bh = 80, 30
            print(f"  未匹配按钮模板，用对话框偏下位置: ({bx},{by})")

        print(f"  点击使用...")
        self.executor.click_human(bx, by, bw, bh)
        print(f"  ✓ 已使用，等待下一地点...")

        # 等待挖宝完成 + 走到下一个地点
        # 并行检测：下一地点对话框 OR 坐标稳定15秒（角色停住=挖完）
        time.sleep(3)
        return self._wait_next_or_done(dialog_path, timeout=180)

    def _wait_next_or_done(self, dialog_path, timeout=180, interval=1):
        """等待下一地点对话框 或 坐标稳定判定挖完

        - 出现下一地点对话框 → 返回 True（继续挖）
        - 坐标稳定15秒且无对话框 → 返回 None（宝图已挖完）
        - 超时 → 返回 None（宝图可能已用完）

        Args:
            dialog_path: 下一地点对话框模板路径
            timeout: 总超时（秒），含战斗+行走时间
        """
        print(f"  等待[下一地点对话框]或[坐标稳定{self.STABLE_DURATION}秒]... (超时{timeout}秒)")
        start = time.time()
        prev_region = None
        stable_since = None
        last_log_time = 0

        while time.time() - start < timeout:
            elapsed = time.time() - start

            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                time.sleep(interval)
                continue

            # 1. 检测下一地点对话框
            match = match_template(img, dialog_path, 0.6)
            if match:
                print(f"  ✓ 出现下一地点对话框，继续挖宝 (耗时{elapsed:.0f}秒)")
                return True

            # 2. 检测坐标稳定性（角色停住=挖完）
            current_region = self._crop_coord_region(img)
            if current_region is not None:
                if prev_region is not None:
                    diff = self._calc_region_diff(prev_region, current_region)
                    if diff < self.STABLE_PIXEL_DIFF_THRESHOLD:
                        if stable_since is None:
                            stable_since = time.time()
                        stable_duration = time.time() - stable_since
                        if stable_duration >= self.STABLE_DURATION:
                            print(f"  ✓ 坐标稳定{self.STABLE_DURATION}秒且无对话框 → 宝图已挖完 (耗时{elapsed:.0f}秒)")
                            return None
                    else:
                        stable_since = None
                prev_region = current_region

            # 状态日志（每15秒一次）
            now = time.time()
            if now - last_log_time > 15:
                if stable_since is not None:
                    stable_elapsed = now - stable_since
                    stable_info = f"稳定{stable_elapsed:.0f}s/{self.STABLE_DURATION}s"
                else:
                    stable_info = "移动中"
                print(f"  ...等待中 已耗时{elapsed:.0f}秒 (坐标:{stable_info})")
                last_log_time = now

            time.sleep(interval)

        print(f"  ✗ 超时{timeout}秒未出现对话框，宝图已用完")
        return None

    def step6_back_to_bag(self):
        """步骤6: 回到背包，检查剩余宝图"""
        print("\n[步骤6] 回到背包...")
        # 等待片刻，让角色停下
        time.sleep(2)
        return True

    def run(self):
        """执行自动挖宝流程"""
        print("=" * 60)
        print("自动挖宝流程")
        print("=" * 60)
        print(f"流程: 打开背包 → 找藏宝图 → 使用 → 走到地点 → 使用 → 循环检测下一地点")
        print(f"偏移量: {SCREENSHOT_OFFSET}")
        print(f"初始宝图数: {self.baotu_count}")

        print("\n3秒后开始...")
        time.sleep(3)

        round_num = 0
        max_rounds = 15  # 最多挖15次，防止死循环

        # 第一轮：打开背包 → 找藏宝图 → 使用 → 走到地点 → 使用
        round_num += 1
        print(f"\n{'='*40}")
        print(f"第 {round_num} 轮挖宝（首次）")
        print(f"{'='*40}")

        # 步骤1: 打开背包
        if not self.step1_open_bag():
            print("\n✗ 挖宝流程失败: 步骤1")
            return False

        # 步骤2: 查找藏宝图
        if not self.step2_find_treasure_map():
            print("\n✓ 背包中没有藏宝图了，任务完成！")
            return True

        # 步骤3: 点击使用（对话框1）
        if not self.step3_use_from_bag():
            print("\n✗ 挖宝流程失败: 步骤3")
            return False

        # 步骤4: 等待走到地点（含战斗时间）
        if not self.step4_wait_walk(timeout=120):
            print("\n✗ 挖宝流程失败: 步骤4")
            return False

        # 步骤5: 在地点使用 → 循环检测下一地点对话框
        while round_num < max_rounds:
            round_num += 1
            print(f"\n{'='*40}")
            print(f"第 {round_num} 轮挖宝（自动检测下一地点）")
            print(f"{'='*40}")

            result = self.step5_use_and_wait_next()
            if result == False:
                print("\n✗ 挖宝流程失败")
                return False
            elif result == None:
                print("\n✓ 未检测到下一地点对话框，宝图已用完，挖宝完成！")
                break

        print("\n" + "=" * 60)
        print(f"✓ 挖宝流程完成！共执行 {round_num} 轮")
        print("=" * 60)
        return True


def main():
    print("=== 自动挖宝任务 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 检查模板
    templates_dir = "templates"
    required = {
        "bag_btn.png": "背包按钮",
        "treasure_map_icon.png": "藏宝图图标",
        "use_dialog1.png": "使用对话框(图2)",
        "use_btn1.png": "使用按钮1",
        "use_dialog2.png": "使用对话框(图3)",
        "use_btn2.png": "使用按钮2",
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

    # 执行挖宝任务
    task = DigTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()
