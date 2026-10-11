import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from core.action_executor import ActionExecutor
import cv2
import numpy as np
import win32gui
import time


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
    """根据模块位置计算按钮位置
    
    按钮位于模块右侧，距离右边界margin_right个像素
    按钮宽度btn_w，高度btn_h，垂直居中
    """
    # 模块右边界
    module_right = module_x + module_w
    # 按钮右边界 = 模块右边界 - margin_right
    btn_right = module_right - margin_right
    # 按钮左边界
    btn_left = btn_right - btn_w
    # 按钮垂直居中
    btn_top = module_y + (module_h - btn_h) // 2
    btn_bottom = btn_top + btn_h
    # 按钮中心
    btn_cx = (btn_left + btn_right) // 2
    btn_cy = (btn_top + btn_bottom) // 2

    return {
        'left': btn_left,
        'top': btn_top,
        'right': btn_right,
        'bottom': btn_bottom,
        'center': (btn_cx, btn_cy),
        'width': btn_w,
        'height': btn_h
    }


def match_template(img, template, threshold=0.8):
    """模板匹配，返回模块位置"""
    # 灰度匹配
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
            'confidence': max_val
        }
    return None


def main():
    print("=== 模块按钮定位测试 ===")

    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")

    screenshot = ScreenshotCapture()
    executor = ActionExecutor(hwnd, mode="background", screenshot_offset=(-11, -39))

    # 加载模板
    templates_dir = "templates"
    template_files = {
        "活动界面": "activite_page.png",
        "师门任务模块": "sectTask_module.png",
        "运镖模块": "escort_module.png",
    }

    templates = {}
    for name, filename in template_files.items():
        path = os.path.join(templates_dir, filename)
        if os.path.exists(path):
            tpl = cv2.imread(path, cv2.IMREAD_COLOR)
            if tpl is not None:
                templates[name] = tpl
                print(f"  加载模板: {name} ({tpl.shape[1]}x{tpl.shape[0]})")
            else:
                print(f"  加载失败: {name}")
        else:
            print(f"  文件不存在: {path}")

    if not templates:
        print("没有可用模板！")
        return

    print("\n3秒后截图...")
    time.sleep(3)

    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败！")
        return

    print(f"截图成功: {img.shape[1]}x{img.shape[0]}")

    result_img = img.copy()
    found_modules = []

    # 匹配每个模板
    print("\n=== 模板匹配结果 ===")
    for name, template in templates.items():
        # 尝试不同阈值
        for threshold in [0.9, 0.8, 0.7, 0.6]:
            match = match_template(img, template, threshold=threshold)
            if match:
                print(f"\n[{name}]")
                print(f"  模块位置: ({match['x']}, {match['y']})")
                print(f"  模块尺寸: {match['width']}x{match['height']}")
                print(f"  模块右边界: {match['x'] + match['width']}")
                print(f"  置信度: {match['confidence']:.3f} (阈值{threshold})")

                # 计算按钮位置
                btn = calc_button_position(
                    match['x'], match['y'], match['width'], match['height']
                )

                print(f"  按钮位置: ({btn['left']}, {btn['top']}) -> ({btn['right']}, {btn['bottom']})")
                print(f"  按钮中心: ({btn['center'][0]}, {btn['center'][1]})")
                print(f"  按钮尺寸: {btn['width']}x{btn['height']}")

                # 画模块框（绿色）
                cv2.rectangle(result_img,
                              (match['x'], match['y']),
                              (match['x'] + match['width'], match['y'] + match['height']),
                              (0, 255, 0), 2)
                cv2.putText(result_img, name,
                            (match['x'], match['y'] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                # 画按钮框（红色）
                cv2.rectangle(result_img,
                              (btn['left'], btn['top']),
                              (btn['right'], btn['bottom']),
                              (0, 0, 255), 2)
                cv2.putText(result_img, f"{name}-btn",
                            (btn['left'], btn['top'] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                # 画按钮中心点
                cv2.circle(result_img, btn['center'], 4, (255, 0, 0), -1)

                found_modules.append({
                    'name': name,
                    'module': match,
                    'button': btn
                })
                break

    # 保存结果图
    cv2.imwrite("module_detection_result.png", result_img)
    print(f"\n结果图已保存: module_detection_result.png")

    if not found_modules:
        print("\n未匹配到任何模块！请检查：")
        print("  1. 游戏画面是否在活动界面")
        print("  2. 模板图片是否正确")
        return

    # 显示结果
    scale = 0.8
    h, w = result_img.shape[:2]
    display = cv2.resize(result_img, (int(w * scale), int(h * scale)))
    cv2.imshow("Module Detection (按任意键关闭)", display)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    # 询问是否点击
    print("\n=== 找到的模块按钮 ===")
    for i, m in enumerate(found_modules, 1):
        btn = m['button']
        print(f"  {i}. {m['name']} 按钮 -> ({btn['center'][0]}, {btn['center'][1]})")

    print(f"  0. 全部点击")
    print(f"  q. 退出")

    choice = input("\n选择要点击的按钮编号: ").strip()

    if choice.lower() == 'q':
        return

    if choice == '0':
        for m in found_modules:
            btn = m['button']
            print(f"\n点击 [{m['name']}] 按钮 ({btn['center'][0]}, {btn['center'][1]})...")
            executor.click(btn['center'][0], btn['center'][1])
            print(f"  ✓ 完成")
            time.sleep(1)
    elif choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(found_modules):
            m = found_modules[idx - 1]
            btn = m['button']
            print(f"\n点击 [{m['name']}] 按钮 ({btn['center'][0]}, {btn['center'][1]})...")
            executor.click(btn['center'][0], btn['center'][1])
            print(f"  ✓ 完成")

    print("\n测试完成。")


if __name__ == "__main__":
    main()