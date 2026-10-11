import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import numpy as np
import win32gui
import time

# 截图坐标到客户区坐标的偏移量
SCREENSHOT_OFFSET = (-11, -39)


def find_game_window():
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
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


def save_annotated(img, matches, filepath):
    """保存标注图"""
    annotated = img.copy()
    for m in matches:
        x, y = m['x'], m['y']
        w, h = m['width'], m['height']
        color = m.get('color', (0, 255, 0))
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
        label = m.get('label', '')
        if label:
            cv2.putText(annotated, label, (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        if 'click' in m:
            cx, cy = m['click']
            cv2.circle(annotated, (cx, cy), 8, (0, 0, 255), -1)
            cv2.putText(annotated, "click", (cx + 10, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.imwrite(filepath, annotated)


class SectTask:
    """师门任务"""

    # 已知任务模板: (文件名, 任务名称)
    TASK_TEMPLATES = [
        ("cijiao_task.png", "赐教任务"),
        # 后续可添加其他任务模板:
        # ("xxx_task.png", "寻物任务"),
        # ("xxx_task.png", "捉鬼任务"),
    ]

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.screenshot = ScreenshotCapture()
        self.executor = ActionExecutor(hwnd, mode="background",
                                       screenshot_offset=SCREENSHOT_OFFSET)
        self.templates_dir = "templates"

    def step1_find_sect_module(self):
        """步骤1: 在活动界面匹配师门任务模块，点击参加"""
        print("\n[步骤1] 查找师门任务模块...")

        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print("  截图失败")
            return False

        tpl_path = os.path.join(self.templates_dir, "sectTask_module.png")
        match = match_template(img, tpl_path, 0.8)
        if not match:
            print("  ✗ 未找到师门任务模块，请确认在活动界面")
            return False

        print(f"  ✓ 师门任务模块: 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']} 置信度{match['confidence']:.3f}")

        # 计算参加按钮位置
        btn_cx, btn_cy = calc_button_position(
            match['x'], match['y'], match['width'], match['height']
        )
        print(f"  参加按钮: ({btn_cx}, {btn_cy})")

        # 保存标注图
        match['color'] = (0, 255, 0)
        match['label'] = "sect_module"
        match['click'] = (btn_cx, btn_cy)
        save_annotated(img, [match], "sect_step1_annotated.png")

        # 点击参加
        print(f"  点击参加按钮...")
        if self.executor.click(btn_cx, btn_cy):
            print(f"  ✓ 点击完成")
            return True
        else:
            print(f"  ✗ 点击失败")
            return False

    def step2_wait_sect_option(self):
        """步骤2: 等待师门选择界面出现"""
        print("\n[步骤2] 等待师门选择界面...")

        match = wait_for_template(
            self.screenshot, self.hwnd,
            os.path.join(self.templates_dir, "sect_option_page.png"),
            timeout=10, label="师门选择界面"
        )
        if not match:
            print("  师门选择界面未出现")
            return None

        print(f"  ✓ 师门选择界面: 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']}")

        # 保存界面截图
        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is not None:
            cv2.imwrite("sect_option_screenshot.png", img)
            print(f"  界面截图已保存: sect_option_screenshot.png")

        return match

    def step3_check_auto_complete(self, option_match):
        """步骤3: 用两个模板判断勾选状态"""
        print("\n[步骤3] 检测自动完成任务勾选状态...")

        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print("  截图失败")
            return False

        # 用两个模板分别匹配
        # auto_sect.png = 未勾选, already_auto_sect.png = 已勾选
        unchecked_tpl = os.path.join(self.templates_dir, "auto_sect.png")
        checked_tpl = os.path.join(self.templates_dir, "already_auto_sect.png")

        unchecked_match = match_template(img, unchecked_tpl, 0.6)
        checked_match = match_template(img, checked_tpl, 0.6)

        if checked_match:
            print(f"  ✓ 已勾选（匹配already_auto_sect）置信度{checked_match['confidence']:.3f}")
            print(f"  跳过勾选")
            return True
        elif unchecked_match:
            print(f"  未勾选（匹配auto_sect）置信度{unchecked_match['confidence']:.3f}")
            # 点击勾选框（模板左侧偏移）
            mx, my = unchecked_match['x'], unchecked_match['y']
            CHECKBOX_OFFSET_X = 18
            CHECKBOX_OFFSET_Y = 26
            cb_cx = mx + CHECKBOX_OFFSET_X
            cb_cy = my + CHECKBOX_OFFSET_Y
            print(f"  点击勾选框 ({cb_cx}, {cb_cy})...")
            self.executor.click(cb_cx, cb_cy)
            print(f"  ✓ 勾选完成")
            time.sleep(1)
            return True
        else:
            print("  ✗ 未匹配到任何勾选状态模板")
            print("  跳过勾选检测")
            return True

    def step4_find_and_click_task(self, option_match):
        """步骤4: 识别任务类型，用按钮模板匹配并点击"""
        print("\n[步骤4] 识别任务并点击按钮...")

        img = self.screenshot.capture_to_cv2(self.hwnd)
        if img is None:
            print("  截图失败")
            return False

        # 尝试匹配所有已知任务模板
        found_tasks = []
        for filename, task_name in self.TASK_TEMPLATES:
            tpl_path = os.path.join(self.templates_dir, filename)
            if not os.path.exists(tpl_path):
                print(f"  跳过 {task_name} (模板不存在: {filename})")
                continue

            match = match_template(img, tpl_path, 0.7)
            if match:
                print(f"  ✓ 找到[{task_name}]: 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']} 置信度{match['confidence']:.3f}")
                match['task_name'] = task_name
                found_tasks.append(match)

        if not found_tasks:
            print("  ✗ 未找到任何已知任务模板")
            print(f"  已知任务模板: {[t[1] for t in self.TASK_TEMPLATES]}")
            cv2.imwrite("sect_no_task_found.png", img)
            return False

        # 按钮模板路径
        btn_tpl_path = os.path.join(self.templates_dir, "sect_down_button.png")
        if not os.path.exists(btn_tpl_path):
            print("  ✗ 按钮模板不存在: sect_down_button.png")
            return False

        # 对每个找到的任务，用精确偏移计算按钮位置
        # 诊断结果: 按钮在任务模板内部底部，相对任务底部偏移(3, -35)
        BUTTON_OFFSET_X = 3   # 相对任务中心x的偏移
        BUTTON_OFFSET_Y = -35  # 相对任务底部的偏移（负数=在底部上方）

        annotations = []
        for task in found_tasks:
            task_name = task['task_name']
            tx, ty = task['x'], task['y']
            tw, th = task['width'], task['height']
            task_cx = tx + tw // 2
            task_bottom = ty + th

            # 用精确偏移计算按钮中心
            btn_cx = task_cx + BUTTON_OFFSET_X
            btn_cy = task_bottom + BUTTON_OFFSET_Y
            print(f"  [{task_name}] 按钮位置: ({btn_cx}, {btn_cy}) [任务底部偏移({BUTTON_OFFSET_X},{BUTTON_OFFSET_Y})]")

            # 标注
            annotations.append({
                'x': tx, 'y': ty, 'width': tw, 'height': th,
                'color': (0, 255, 0), 'label': task_name,
                'click': (btn_cx, btn_cy)
            })

            # 点击按钮
            print(f"  点击[{task_name}]按钮...")
            # 保存点击前截图，供步骤5差异检测用
            self.before_click_img = self.screenshot.capture_to_cv2(self.hwnd)
            self.executor.click(btn_cx, btn_cy)
            print(f"  ✓ 点击完成")

            time.sleep(2)
            self._check_confirm_dialog()

        # 保存标注图
        save_annotated(img, annotations, "sect_step4_annotated.png")
        print(f"  标注图已保存: sect_step4_annotated.png")

        return True

    def _check_confirm_dialog(self):
        """检查是否有确认对话框，如果有则点击确定"""
        # 简单方案：截图后检查是否有"确定"按钮模板
        # 这里先跳过，后续添加确认对话框模板
        pass

    def step5_select_dialogue_option(self):
        """步骤5: 多策略定位对话框 + 水平投影找第一个选项"""
        print("\n[步骤5] 检测师门对话框...")

        time.sleep(2)

        after_img = self.screenshot.capture_to_cv2(self.hwnd)
        if after_img is None:
            print("  截图失败")
            return False

        cv2.imwrite("sect_dialogue_after.png", after_img)

        h, w = after_img.shape[:2]
        screen_area = h * w

        dialogue_rect = None

        # 策略1: 模板匹配sect_dialogue.png（低阈值）
        dialogue_tpl = os.path.join(self.templates_dir, "sect_dialogue.png")
        if os.path.exists(dialogue_tpl):
            match = match_template(after_img, dialogue_tpl, 0.3)
            if match:
                dialogue_rect = (match['x'], match['y'], match['width'], match['height'])
                print(f"  ✓ 策略1(模板匹配): 位置({match['x']},{match['y']}) 尺寸{match['width']}x{match['height']} 置信度{match['confidence']:.3f}")

        # 策略2: 差异检测（只搜索上半部分，过滤太大区域）
        if not dialogue_rect and hasattr(self, 'before_click_img') and self.before_click_img is not None:
            before = self.before_click_img
            if before.shape == after_img.shape:
                diff = cv2.absdiff(before, after_img)
                gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray_diff, 40, 255, cv2.THRESH_BINARY)
                kernel = np.ones((5, 5), np.uint8)
                binary = cv2.dilate(binary, kernel, iterations=2)
                cv2.imwrite("sect_dialogue_diff.png", binary)

                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                max_area = 0
                for cnt in contours:
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    area = cw * ch
                    # 只搜索右半部分 + 过滤太大区域
                    if area > max_area and 5000 < area < screen_area * 0.3 and x + cw // 2 > w // 2:
                        max_area = area
                        dialogue_rect = (x, y, cw, ch)

                if dialogue_rect:
                    print(f"  ✓ 策略2(差异检测): 位置({dialogue_rect[0]},{dialogue_rect[1]}) 尺寸{dialogue_rect[2]}x{dialogue_rect[3]}")

        # 策略3: 屏幕右半部分
        if not dialogue_rect:
            dialogue_rect = (w // 2, h // 8, w // 2, 3 * h // 4)
            print(f"  策略3(右半部分): 位置({dialogue_rect[0]},{dialogue_rect[1]}) 尺寸{dialogue_rect[2]}x{dialogue_rect[3]}")

        dx, dy, dw, dh = dialogue_rect

        # 用水平投影找文字行
        dialogue_region = after_img[dy:dy+dh, dx:dx+dw]
        gray = cv2.cvtColor(dialogue_region, cv2.COLOR_BGR2GRAY)

        # 用固定阈值检测亮色文字（游戏文字通常是白色/浅色）
        _, text_binary = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)

        # 水平投影
        row_proj = np.sum(text_binary > 0, axis=1)

        # 找文字行
        proj_threshold = max(np.max(row_proj) * 0.1, 3)
        text_lines = []
        in_text = False
        start = 0
        for i, val in enumerate(row_proj):
            if val > proj_threshold and not in_text:
                in_text = True
                start = i
            elif val <= proj_threshold and in_text:
                in_text = False
                if i - start > 5:  # 过滤太短的行
                    text_lines.append((start, i))

        print(f"  检测到 {len(text_lines)} 个文字行:")
        for idx, (sy, ey) in enumerate(text_lines):
            print(f"    行{idx}: y={sy}-{ey} (高度{ey-sy})")

        # 第一行 = "请选择要做的事："（标题）
        # 第二行 = 第一个选项（包含"师门"）
        if len(text_lines) >= 2:
            option_y_start, option_y_end = text_lines[1]
            option_cy = dy + (option_y_start + option_y_end) // 2
            option_cx = dx + dw // 2
            print(f"  第一个选项位置: ({option_cx}, {option_cy}) [文字行1]")
        elif len(text_lines) == 1:
            option_y_start, option_y_end = text_lines[0]
            option_cy = dy + (option_y_start + option_y_end) // 2
            option_cx = dx + dw // 2
            print(f"  选项位置: ({option_cx}, {option_cy}) [唯一文字行]")
        else:
            option_cx = dx + dw // 2
            option_cy = dy + dh // 3
            print(f"  选项位置: ({option_cx}, {option_cy}) [默认上部1/3]")

        # 标注并保存
        annotated = after_img.copy()
        cv2.rectangle(annotated, (dx, dy), (dx + dw, dy + dh), (0, 255, 0), 2)
        for idx, (sy, ey) in enumerate(text_lines):
            color = (255, 0, 0) if idx == 0 else (0, 255, 255)
            cv2.rectangle(annotated, (dx, dy+sy), (dx+dw, dy+ey), color, 1)
        cv2.drawMarker(annotated, (option_cx, option_cy), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
        cv2.imwrite("sect_step5_annotated.png", annotated)

        # 点击第一个选项
        print(f"  点击第一个选项...")
        self.executor.click(option_cx, option_cy)
        print(f"  ✓ 点击完成")

        time.sleep(2)
        return True

    def step6_wait_task_complete(self):
        """步骤6: 等待任务完成弹窗 → 点击确定"""
        print("\n[步骤6] 等待任务完成...")

        # 先等对话框消失
        dialogue_tpl = os.path.join(self.templates_dir, "sect_dialogue.png")
        for i in range(5):
            time.sleep(1)
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                continue
            if os.path.exists(dialogue_tpl):
                match = match_template(img, dialogue_tpl, 0.3)
                if not match:
                    print(f"  ✓ 对话框已消失，选项已选中")
                    break

        # 等待完成弹窗出现
        complete_tpl = os.path.join(self.templates_dir, "sect_complete.png")
        confirm_tpl = os.path.join(self.templates_dir, "confirm_btn.png")

        print("  等待完成弹窗出现...")
        for i in range(60):
            time.sleep(2)
            img = self.screenshot.capture_to_cv2(self.hwnd)
            if img is None:
                continue

            # 检查完成弹窗
            if os.path.exists(complete_tpl):
                match = match_template(img, complete_tpl, 0.7)
                if match:
                    print(f"  ✓ 检测到师门任务完成弹窗!")

                    # 保存截图
                    cv2.imwrite("sect_complete_detected.png", img)

                    # 点击确定按钮
                    if os.path.exists(confirm_tpl):
                        btn_match = match_template(img, confirm_tpl, 0.7)
                        if btn_match:
                            bx = btn_match['x'] + btn_match['width'] // 2
                            by = btn_match['y'] + btn_match['height'] // 2
                            print(f"  找到确定按钮: ({bx}, {by})")
                            print(f"  点击确定按钮...")
                            self.executor.click(bx, by)
                            print(f"  ✓ 已点击确定按钮")
                            time.sleep(1)
                            return True
                        else:
                            # 按钮模板未匹配，用弹窗中心偏下位置
                            px = match['x'] + match['width'] // 2
                            py = match['y'] + match['height'] * 2 // 3
                            print(f"  未找到确定按钮模板，点击弹窗偏下位置: ({px}, {py})")
                            self.executor.click(px, py)
                            print(f"  ✓ 已点击")
                            time.sleep(1)
                            return True
                    else:
                        # 没有按钮模板，点击弹窗中心偏下
                        px = match['x'] + match['width'] // 2
                        py = match['y'] + match['height'] * 2 // 3
                        print(f"  无确定按钮模板，点击弹窗偏下位置: ({px}, {py})")
                        self.executor.click(px, py)
                        time.sleep(1)
                        return True

            # 检查是否回到活动界面
            activity_tpl = os.path.join(self.templates_dir, "activite_page.png")
            if os.path.exists(activity_tpl):
                match = match_template(img, activity_tpl, 0.8)
                if match:
                    print(f"  ✓ 已回到活动界面")
                    return True

            if i % 5 == 0 and i > 0:
                print(f"  等待中... ({i*2}秒)")

        print("  等待超时")
        return False

    def run(self):
        """执行完整师门任务流程"""
        print("=" * 60)
        print("师门任务完整流程")
        print("=" * 60)
        print("流程: 活动界面 → 师门参加 → 勾选自动完成 → 识别任务 → 点击按钮 → 对话框选第一条")
        print(f"偏移量: {SCREENSHOT_OFFSET}")
        print(f"已知任务: {[t[1] for t in self.TASK_TEMPLATES]}")

        print("\n3秒后开始...")
        time.sleep(3)

        # 步骤1: 点击师门任务参加
        if not self.step1_find_sect_module():
            print("\n✗ 师门流程失败: 步骤1")
            return False

        time.sleep(2)

        # 步骤2: 等待师门选择界面
        option_match = self.step2_wait_sect_option()
        if not option_match:
            print("\n✗ 师门流程失败: 步骤2")
            return False

        # 步骤3: 检测自动完成任务勾选状态
        self.step3_check_auto_complete(option_match)

        time.sleep(1)

        # 步骤4: 识别任务并点击按钮
        if not self.step4_find_and_click_task(option_match):
            print("\n✗ 师门流程失败: 步骤4")
            return False

        # 步骤5: 等待师门对话框，选中第一条选项
        self.step5_select_dialogue_option()

        # 步骤6: 等待任务完成
        self.step6_wait_task_complete()

        print("\n" + "=" * 60)
        print("✓ 师门任务流程执行完成！")
        print("=" * 60)
        return True


def main():
    print("=== 师门任务完整流程测试 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！请先打开游戏。")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    # 检查模板
    templates_dir = "templates"
    required = {
        "sectTask_module.png": "师门任务模块",
        "sect_option_page.png": "师门选择界面",
        "cijiao_task.png": "赐教任务",
        "sect_down_button.png": "任务按钮",
        "auto_sect.png": "自动完成任务(未勾选)",
        "already_auto_sect.png": "自动完成任务(已勾选)",
        "sect_dialogue.png": "师门对话框",
        "sect_complete.png": "师门任务完成弹窗",
        "confirm_btn.png": "确定按钮",
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

    # 执行师门任务
    task = SectTask(hwnd)
    task.run()


if __name__ == "__main__":
    main()