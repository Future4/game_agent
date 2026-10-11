import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import win32gui
import time
import ctypes
from core.screenshot import ScreenshotCapture

templates_dir = "templates"

def find_game_window():
    results = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if "梦幻西游" in title or "Unity" in class_name:
                results.append({'hwnd': hwnd, 'title': title, 'class': class_name})
    win32gui.EnumWindows(callback, None)
    return results

def capture_new(screenshot, hwnd, wait_time=5):
    """等待后重新截图"""
    print(f"  等待{wait_time}秒后重新截图...")
    time.sleep(wait_time)
    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("  截图失败")
        return None
    print(f"  ✓ 重新截图完成: {img.shape[1]}x{img.shape[0]}")
    return img

def select_and_save(img, window_name, label, filename, annotated, saved):
    """框选并保存模板"""
    print(f"\n  框选【{label}】 → 回车确认")
    display = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    roi = cv2.selectROI(window_name, display, showCrosshair=True)
    cv2.destroyAllWindows()
    
    if roi[2] > 0 and roi[3] > 0:
        x, y, w, h = roi
        crop = img[y:y+h, x:x+w]
        path = os.path.join(templates_dir, filename)
        cv2.imwrite(path, crop)
        annotated = cv2.rectangle(annotated, (x, y), (x+w, y+h), (0, 255, 0), 2)
        print(f"  ✓ {label}: 位置({x},{y}) 尺寸{w}x{h}")
        saved[filename] = (x, y, w, h)
        return crop, annotated
    else:
        print(f"  跳过【{label}】")
        return None, annotated

print("=== 制作挖宝任务模板 ===")
print("\n制作流程：")
print("1. 每个模板框选前会等待5秒让你切换游戏界面")
print("2. 在弹出的窗口中用鼠标拖拽框选目标区域")
print("3. 按回车确认，或按c取消\n")

input("准备好后按回车开始...")

windows = find_game_window()
if not windows:
    print("未找到游戏窗口")
    exit()

hwnd = windows[0]['hwnd']
print(f"游戏窗口: {windows[0]['title']}")

# 初始化截图器
screenshot = ScreenshotCapture()
annotated = None
saved = {}

# 步骤1: 包裹按钮
print("\n" + "="*60)
print("步骤1: 框选【包裹按钮】")
print("请确保游戏在主界面，能看到右下方的包裹按钮")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()
annotated = img.copy()

_, annotated = select_and_save(
    img, "Select bag button", 
    "包裹按钮(右下方)", "bag_btn.png", 
    annotated, saved
)

# 步骤2: 藏宝图图标
print("\n" + "="*60)
print("步骤2: 框选【藏宝图图标】")
print("请点击包裹按钮打开物品栏，找到藏宝图")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()

_, annotated = select_and_save(
    img, "Select treasure map icon", 
    "藏宝图图标", "treasure_map_icon.png", 
    annotated, saved
)

# 步骤3: 对话框1
print("\n" + "="*60)
print("步骤3: 框选【首次使用对话框】")
print("请点击藏宝图，确保出现使用对话框(图2)")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()

_, annotated = select_and_save(
    img, "Select use dialog 1", 
    "首次使用对话框(图2)", "use_dialog1.png", 
    annotated, saved
)

# 步骤4: 使用按钮1
print("\n" + "="*60)
print("步骤4: 框选【使用按钮1】")
print("在对话框中找到右下角的使用按钮")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()

_, annotated = select_and_save(
    img, "Select use button 1", 
    "对话框1中的使用按钮", "use_btn1.png", 
    annotated, saved
)

# 步骤5: 对话框2
print("\n" + "="*60)
print("步骤5: 框选【地点使用对话框】")
print("请关闭包裹，手动走到挖宝地点")
print("确保出现地点使用对话框(图3)")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()

_, annotated = select_and_save(
    img, "Select use dialog 2", 
    "地点使用对话框(图3)", "use_dialog2.png", 
    annotated, saved
)

# 步骤6: 使用按钮2
print("\n" + "="*60)
print("步骤6: 框选【使用按钮2】")
print("在地点使用对话框中找到使用按钮")
print("="*60)
input("\n准备好后按回车...")
img = capture_new(screenshot, hwnd, 5)
if img is None: exit()

_, annotated = select_and_save(
    img, "Select use button 2", 
    "对话框2中的使用按钮", "use_btn2.png", 
    annotated, saved
)

# 保存标注图
if annotated is not None:
    cv2.imwrite("dig_templates_annotated.png", annotated)

print("\n" + "="*60)
print("✓ 模板制作完成！")
print("="*60)
for fname, rect in saved.items():
    print(f"  - {fname}: 位置({rect[0]},{rect[1]}) 尺寸{rect[2]}x{rect[3]}")

# 测试模板匹配
print("\n=== 测试模板匹配 ===")
time.sleep(1)
test_img = screenshot.capture_to_cv2(hwnd)

for tpl_file, label in [
    ("bag_btn.png", "包裹按钮"),
    ("treasure_map_icon.png", "藏宝图图标"),
]:
    tpl_path = os.path.join(templates_dir, tpl_file)
    if os.path.exists(tpl_path):
        tpl = cv2.imread(tpl_path)
        if tpl is not None:
            result = cv2.matchTemplate(test_img, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val > 0.7:
                print(f"  ✓ {label}: 位置({max_loc[0]},{max_loc[1]}) 置信度{max_val:.3f}")
            else:
                print(f"  ✗ {label}: 置信度{max_val:.3f}")
