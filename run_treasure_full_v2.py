"""宝图任务 + 挖宝 完整自动化流程

流程：
1. 宝图任务循环（最多15次）
   - 点击参加 → 听听无妨 → 战斗
   - 战斗结束判断：左上角坐标显示区域30秒无变化 → 10次全部完成
2. 挖宝阶段
   - 打开背包 → 找藏宝图 → 使用 → 走到地点 → 循环挖宝

完成判断核心：通过左上角坐标显示区域的像素稳定性检测，
30秒无变化即判定10次宝图任务已全部完成。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
from run_treasure_task import TreasureMapTask
from run_dig_task import DigTask
import cv2
import numpy as np
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


def match_template(img, template_path, threshold=0.8, search_region=None):
    """模板匹配（支持指定搜索区域）"""
    if not os.path.exists(template_path):
        return None
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        return None

    target = img
    offset_x, offset_y = 0, 0
    if search_region:
        x, y, w, h = search_region
        target = img[y:y+h, x:x+w]
        offset_x, offset_y = x, y

    img_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
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
        candidate = {'x': loc[0] + offset_x, 'y': loc[1] + offset_y,
                     'width': w, 'height': h, 'confidence': float(score), 'scale': scale,
                     'center': (loc[0] + w // 2 + offset_x, loc[1] + h // 2 + offset_y)}
        if best is None or candidate['confidence'] > best['confidence']:
            best = candidate
    print(f"  模板最佳匹配: {os.path.basename(template_path)} {best}")
    return best if best and best['confidence'] >= threshold else None


def wait_for_template(screenshot, hwnd, template_path, timeout=10, interval=0.5,
                      threshold=0.8, label="", search_region=None):
    """等待模板出现"""
    print(f"  等待[{label}]出现... (超时{timeout}秒)")
    start = time.time()
    while time.time() - start < timeout:
        img = screenshot.capture_to_cv2(hwnd)
        if img is not None:
            match = match_template(img, template_path, threshold, search_region)
            if match:
                print(f"  ✓ 找到[{label}] 置信度{match['confidence']:.3f} 耗时{time.time()-start:.1f}秒")
                return match
        time.sleep(interval)
    print(f"  ✗ 超时未找到[{label}]")
    return None


class TreasureFullTask:
    """宝图任务 + 挖宝 完整流程

    流程：
        开始
          ↓
        点击参加 → 选择"听听无妨" → 战斗
          ↓
        等待战斗结束（左上角坐标区域30秒无变化=10次全部完成）
          ↓
        全部完成！进入挖宝 ✓
    """

    # 游戏内地图坐标显示区域（截图中的像素位置）
    # 用户确认: 坐标文字显示在 (52,41)~(91,50) 矩形附近，四周留少量边距
    STABLE_CHECK_X = 47       # 监控区域左上角X坐标
    STABLE_CHECK_Y = 36       # 监控区域左上角Y坐标
    STABLE_CHECK_W = 49       # 监控区域宽度 (91-52+5+5)
    STABLE_CHECK_H = 19       # 监控区域高度 (50-41+5+5)
    STABLE_DURATION = 30      # 稳定持续时间（秒），超过此时间无变化判定任务完成
    STABLE_PIXEL_DIFF_THRESHOLD = 5  # 像素差阈值（灰度值差），低于此值视为无变化

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"
        self.treasure_task = TreasureMapTask(hwnd)
        self.max_baotu_rounds = 15  # 最多15次，防止死循环
        self.img_h = 0
        self.img_w = 0

    def _crop_status_region(self, img):
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

    def is_in_battle(self, img):
        """检测是否在战斗中（三组HoughCircles参数一致性判断）

        战斗中：阵法图案为稳定的圆形，三组参数都检测到1个圆形，位置(304,70)半径23一致
        非战斗中：无稳定圆形，三组参数检测到的圆形数量不同(3/10/22)，位置分散

        判断条件（全部满足才判定战斗中）：
        1. 三组参数都检测到至少1个圆形
        2. 三组检测到的圆形数量一致
        3. 三组第一个圆形中心位置接近（误差<10像素）
        4. 三组第一个圆形半径接近（误差<5像素）

        Args:
            img: 已截取的游戏全屏图
        Returns:
            True=战斗中, False=非战斗中
        """
        if img is None:
            return False
        h, w = img.shape[:2]
        # 顶部中间区域（回合数及阵法图案所在位置）
        x1 = w // 4
        x2 = w * 3 // 4
        region = img[0:100, x1:x2]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # 三组HoughCircles参数
        params_list = [
            (50, 30, 10, 40),  # 参数组1（最严格）
            (50, 25, 8, 35),   # 参数组2
            (40, 20, 10, 40),  # 参数组3（最宽松）
        ]

        results = []
        for p1, p2, minr, maxr in params_list:
            circles = cv2.HoughCircles(
                blur, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
                param1=p1, param2=p2, minRadius=minr, maxRadius=maxr
            )
            if circles is None or len(circles[0]) == 0:
                return False  # 任一组未检测到圆形 → 非战斗
            results.append(circles[0])  # 圆形列表 (N, 3)

        # 条件1: 三组都检测到圆形（已满足）
        # 条件2: 三组圆形数量一致
        counts = [len(r) for r in results]
        if counts[0] != counts[1] or counts[0] != counts[2]:
            return False  # 数量不一致 → 非战斗

        # 条件3&4: 三组第一个圆形位置和半径接近
        c1, c2, c3 = results[0][0], results[1][0], results[2][0]
        pos_threshold = 10
        radius_threshold = 5

        pos_close = (abs(c1[0]-c2[0]) < pos_threshold and abs(c1[1]-c2[1]) < pos_threshold and
                     abs(c1[0]-c3[0]) < pos_threshold and abs(c1[1]-c3[1]) < pos_threshold)
        radius_close = (abs(c1[2]-c2[2]) < radius_threshold and abs(c1[2]-c3[2]) < radius_threshold)

        return pos_close and radius_close

    def wait_battle_start(self, timeout=90, interval=2):
        """等待进入战斗

        点击听听无妨后，角色走路→进入战斗。
        - 检测到战斗场景 → "round_done"（进入战斗）
        - 超时未进入战斗 → "all_done"（10次全部完成，参加按钮已消失）
        """
        print(f"  等待进入战斗... (超时{timeout}秒，超时=10次全部完成)")
        start = time.time()
        last_log_time = 0

        while time.time() - start < timeout:
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is not None:
                if self.is_in_battle(img):
                    elapsed = time.time() - start
                    print(f"  ✓ 进入战斗 (走路{elapsed:.0f}秒)")
                    return "round_done"

            now = time.time()
            if now - last_log_time > 10:
                elapsed = time.time() - start
                print(f"  ...等待进入战斗 已耗时{elapsed:.0f}秒")
                last_log_time = now

            time.sleep(interval)

        print(f"  ✓ {timeout}秒未进入战斗 → 10次宝图任务全部完成！")
        return "all_done"

    def wait_battle_end(self, timeout=300, interval=3):
        """等待当前战斗结束

        已经在战斗中，等待战斗结束。
        - 战斗中 → 继续等待
        - 战斗结束 → "round_done"
        - 超时 → "timeout"
        """
        print(f"  等待战斗结束... (超时{timeout}秒)")
        print(f"  战斗检测: 三组HoughCircles参数一致性判断（圆形位置+数量一致）")
        start = time.time()
        last_log_time = 0

        while time.time() - start < timeout:
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                time.sleep(interval)
                continue

            in_battle = self.is_in_battle(img)

            if not in_battle:
                elapsed = time.time() - start
                print(f"  ✓ 战斗结束 (战斗耗时{elapsed:.0f}秒)")
                return "round_done"

            now = time.time()
            if now - last_log_time > 10:
                elapsed = time.time() - start
                print(f"  ...战斗中 已耗时{elapsed:.0f}秒")
                last_log_time = now

            time.sleep(interval)

        elapsed = time.time() - start
        print(f"  ✗ 战斗超时{timeout}秒 (已耗时{elapsed:.0f}秒)")
        return "timeout"

    def run_baotu_rounds(self):
        """执行宝图任务循环

        流程：
        1. 点击参加 → 听听无妨 → 等待进入战斗 → 等待战斗结束
        2. 战斗结束 → 继续下一轮（重新点击参加）
        3. 等待进入战斗超时(90秒) → 10次全部完成 → 进入挖宝
        """
        print("\n" + "=" * 60)
        print("阶段1: 宝图任务")
        print("=" * 60)
        print("流程: 点击参加 → 听听无妨 → 等待进入战斗 → 战斗 → 战斗结束 → 下一轮")
        print("完成判断: 等待进入战斗超时(90秒) = 10次全部完成")

        for round_num in range(1, self.max_baotu_rounds + 1):
            print(f"\n{'='*40}")
            print(f"宝图任务 第 {round_num}/{self.max_baotu_rounds} 轮")
            print(f"{'='*40}")

            # ---------- 步骤1: 点击参加 ----------
            print(f"\n[步骤1] 点击宝图参加...")
            self.treasure_task.step1_find_treasure_module()
            time.sleep(2)

            # ---------- 步骤2: 选择听听无妨 ----------
            print(f"\n[步骤2] 选择听听无妨...")
            self.treasure_task.step2_select_listen()

            # ---------- 步骤3: 等待进入战斗 ----------
            print(f"\n[步骤3] 等待进入战斗...")
            status = self.wait_battle_start(timeout=90)

            if status == "all_done":
                print(f"\n✓ 90秒未进入战斗 → 10次宝图任务全部完成！")
                break

            # ---------- 步骤4: 等待战斗结束 ----------
            print(f"\n[步骤4] 等待战斗结束...")
            status = self.wait_battle_end(timeout=300)

            if status == "timeout":
                print(f"\n⚠ 第{round_num}轮战斗超时")
                break

            time.sleep(2)

        print(f"\n{'='*60}")
        print(f"✓ 宝图任务阶段完成！")
        print(f"{'='*60}")

    def run(self):
        """执行完整流程：宝图任务 → 挖宝"""
        print("=" * 60)
        print("宝图任务 + 挖宝 完整自动化流程")
        print("=" * 60)
        print(f"流程:")
        print(f"  1. 点击参加 → 听听无妨 → 战斗")
        print(f"  2. 战斗结束判断：左上角坐标区域30秒无变化 → 10次全部完成")
        print(f"  3. 宝图任务完成 → 打开包裹 → 自动挖宝")
        print(f"偏移量: {SCREENSHOT_OFFSET}")
        print(f"最大循环次数: {self.max_baotu_rounds}")
        print(f"稳定检测: 坐标({self.STABLE_CHECK_X},{self.STABLE_CHECK_Y}) "
              f"{self.STABLE_CHECK_W}x{self.STABLE_CHECK_H}区域")

        print("\n3秒后开始...")
        time.sleep(3)

        # 阶段1: 宝图任务循环
        self.run_baotu_rounds()

        # 衔接：宝图任务 → 挖宝
        print("\n" + "=" * 60)
        print("[衔接] 宝图任务完成，进入挖宝阶段")
        print("=" * 60)
        print("等待5秒后开始挖宝...")
        time.sleep(5)

        # 阶段2: 挖宝
        try:
            dig_task = DigTask(self.hwnd)
            dig_result = dig_task.run()
            if dig_result:
                print("\n✓ 挖宝流程完成！")
            else:
                print("\n⚠ 挖宝流程提前结束")
        except Exception as e:
            print(f"\n✗ 挖宝流程异常: {e}")
            import traceback
            traceback.print_exc()

        print("\n" + "=" * 60)
        print("✓ 完整流程结束！")
        print("=" * 60)


def main():
    print("=== 宝图任务 + 挖宝 完整流程 ===")
    print()
    print("【核心逻辑】")
    print("  阶段1 - 宝图任务循环：")
    print("    · 点击参加 → 听听无妨 → 战斗")
    print("    · 战斗结束判断：左上角坐标区域30秒无变化 → 10次全部完成")
    print("  阶段2 - 自动挖宝：")
    print("    · 打开包裹 → 找藏宝图 → 使用 → 循环挖宝至用完")
    print()

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！请先打开游戏。")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 检查模板
    templates_dir = "templates"
    required = {
        "baotu_module.png": ("宝图任务模块", None),
        "baotu_dialogue.png": ("宝图对话", None),
        "bag_btn.png": ("包裹按钮", "make_dig_templates.py"),
        "treasure_map_icon.png": ("藏宝图图标", "make_dig_templates.py"),
        "use_dialog1.png": ("背包中使用对话框(图2)", "make_dig_templates.py"),
        "use_btn1.png": ("对话框1的使用按钮", "make_dig_templates.py"),
        "use_dialog2.png": ("地点使用对话框(图3)", "make_dig_templates.py"),
        "use_btn2.png": ("对话框2的使用按钮", "make_dig_templates.py"),
    }

    print("\n模板检查:")
    all_ok = True
    missing_list = []
    for filename, (label, maker) in required.items():
        path = os.path.join(templates_dir, filename)
        if os.path.exists(path):
            tpl = cv2.imread(path)
            if tpl is not None:
                print(f"  ✓ {label} ({filename}) {tpl.shape[1]}x{tpl.shape[0]}")
            else:
                print(f"  ✗ {label} ({filename}) 加载失败")
                all_ok = False
                missing_list.append((filename, label, maker))
        else:
            print(f"  ✗ {label} ({filename}) 不存在")
            all_ok = False
            missing_list.append((filename, label, maker))

    if not all_ok:
        print("\n⚠ 必要模板缺失！请先制作以下模板：")
        for fname, label, maker in missing_list:
            if maker:
                print(f"  · {label}: 运行 python {maker}")
            else:
                print(f"  · {label}: 请制作后放入 templates/ 目录")
        return

    # 确认
    print("\n即将执行完整流程：")
    print("  1. 宝图任务（最多15轮，自动判断完成）")
    print("  2. 自动挖宝（包裹 → 藏宝图 → 循环挖宝）")
    print("请确保：")
    print("  - 游戏在活动界面（可见宝图任务模块的【参加】按钮）")
    print("  - 今日宝图任务次数未用完（每天10次）")
    print("  - 以管理员权限运行（确保点击有效）")
    print("  - 监控区域(47,36) 49x19 应为游戏内坐标显示位置")
    print("=" * 60)
    print("\n5秒后自动开始...（请确保游戏就绪）")
    time.sleep(5)

    # 执行完整流程
    task = TreasureFullTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()
