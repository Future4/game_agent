import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from vision.vision import Vision, ImagePreprocessor
import cv2
import win32gui
import msvcrt


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


def draw_box(img, x, y, w, h, label="", color=(0, 255, 0)):
    """在图像上画框"""
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
    if label:
        cv2.putText(img, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return img


def manual_crop_template(img, template_name, templates_dir="templates"):
    """交互式裁剪模板"""
    img_copy = img.copy()
    drawing = False
    start_pos = None
    end_pos = None
    
    def mouse_callback(event, x, y, flags, param):
        nonlocal drawing, start_pos, end_pos, img_copy
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            start_pos = (x, y)
            img_copy = img.copy()
        elif event == cv2.EVENT_MOUSEMOVE and drawing:
            end_pos = (x, y)
            img_copy = img.copy()
            cv2.rectangle(img_copy, start_pos, end_pos, (0, 255, 0), 2)
        elif event == cv2.EVENT_LBUTTONUP:
            drawing = False
            end_pos = (x, y)
            cv2.rectangle(img_copy, start_pos, end_pos, (0, 255, 0), 2)
    
    window_name = f"裁剪模板: {template_name} (拖拽选框, 回车确认, ESC取消)"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, mouse_callback)
    
    print(f"\n裁剪模板 '{template_name}':")
    print("  - 用鼠标拖拽选择区域")
    print("  - 按回车键确认并保存")
    print("  - 按ESC取消")
    
    while True:
        # 缩放显示（如果图太大）
        scale = 1.0
        h, w = img_copy.shape[:2]
        max_w = 1200
        if w > max_w:
            scale = max_w / w
            display = cv2.resize(img_copy, None, fx=scale, fy=scale)
        else:
            display = img_copy
        
        cv2.imshow(window_name, display)
        key = cv2.waitKey(20) & 0xFF
        
        if key == 27:  # ESC
            cv2.destroyWindow(window_name)
            return None
        elif key == 13:  # Enter
            if start_pos and end_pos:
                x1, y1 = start_pos
                x2, y2 = end_pos
                x = min(x1, x2)
                y = min(y1, y2)
                w = abs(x2 - x1)
                h = abs(y2 - y1)
                if w > 10 and h > 10:
                    template = img[y:y+h, x:x+w]
                    
                    os.makedirs(templates_dir, exist_ok=True)
                    path = os.path.join(templates_dir, f"{template_name}.png")
                    cv2.imwrite(path, template)
                    print(f"  模板已保存: {path} ({w}x{h})")
                    
                    cv2.destroyWindow(window_name)
                    return {
                        'path': path,
                        'roi': (x, y, w, h),
                        'image': template
                    }
            print("  请先选框！")
    
    cv2.destroyWindow(window_name)
    return None


def main():
    print("=== 模板制作工具 ===")
    print("1. 截取游戏画面")
    print("2. 裁剪按钮/元素为模板")
    print("3. 保存到 templates/ 目录")
    print()
    
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！请先打开游戏。")
        return
    
    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")
    
    screenshot = ScreenshotCapture()
    
    # 第一次截图
    print("\n3秒后截图...（请确保要裁剪的按钮可见）")
    import time
    time.sleep(3)
    
    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败！")
        return
    
    print(f"截图成功: {img.shape[1]}x{img.shape[0]}")
    cv2.imwrite("template_setup_screenshot.png", img)
    
    vision = Vision()
    
    templates = []
    
    # 常用按钮清单
    button_list = [
        "join_button",      # 参加按钮
        "task_button",      # 任务按钮
        "shimen_button",    # 师门按钮
        "auto_button",      # 自动按钮
        "ok_button",        # 确定按钮
        "cancel_button",    # 取消按钮
        "close_button",     # 关闭按钮
    ]
    
    print(f"\n常用按钮列表（共{len(button_list)}个）：")
    for i, name in enumerate(button_list, 1):
        print(f"  {i}. {name}")
    print(f"  0. 自定义名称")
    print(f"  q. 完成并退出")
    
    while True:
        print("\n选择要裁剪的按钮编号 (或输入自定义名称): ", end="", flush=True)
        
        # 读取输入
        line = ""
        while True:
            ch = msvcrt.getwche()
            if ch == '\r':
                print()
                break
            elif ch == '\x03':
                print("\n取消")
                return
            elif ch == '\x08':
                if line:
                    line = line[:-1]
                    print('\b \b', end="", flush=True)
            else:
                line += ch
        
        if not line:
            continue
        
        choice = line.strip()
        
        if choice.lower() == 'q':
            break
        
        # 判断选哪个
        if choice.isdigit():
            idx = int(choice)
            if idx == 0:
                template_name = input("输入模板名称: ").strip()
            elif 1 <= idx <= len(button_list):
                template_name = button_list[idx - 1]
            else:
                print("无效编号")
                continue
        else:
            template_name = choice
        
        if not template_name:
            continue
        
        result = manual_crop_template(img, template_name)
        if result:
            templates.append(result)
            # 把模板添加到vision并测试匹配
            vision.add_template(template_name, result['image'])
            match = vision.detect_template(img, template_name, threshold=0.9)
            if match:
                print(f"  自检测试: 匹配成功！位置({match[0]},{match[1]}) 置信度{match[2]:.2f}")
            else:
                print(f"  自检测试: 未匹配（阈值0.9，可以降低阈值）")
    
    print(f"\n完成！共制作 {len(templates)} 个模板。")
    print("模板保存在 templates/ 目录下。")
    print("\n接下来可以运行 test_template_match.py 测试模板匹配效果。")


if __name__ == "__main__":
    main()