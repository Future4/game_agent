import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from vision.vision import Vision
from core.action_executor import ActionExecutor
import cv2
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


def main():
    print("=== 模板匹配 + 点击测试 ===")
    
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return
    
    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: {windows[0]['title']}")
    
    # 检查 templates 目录
    templates_dir = "templates"
    if not os.path.exists(templates_dir):
        print(f"\n错误: 模板目录 {templates_dir} 不存在！")
        print("请先运行 template_setup.py 制作模板。")
        return
    
    template_files = [f for f in os.listdir(templates_dir) if f.endswith(('.png', '.jpg'))]
    if not template_files:
        print(f"\n错误: 模板目录 {templates_dir} 中没有模板图片！")
        print("请先运行 template_setup.py 制作模板。")
        return
    
    print(f"\n发现 {len(template_files)} 个模板:")
    for i, f in enumerate(template_files, 1):
        name = os.path.splitext(f)[0]
        print(f"  {i}. {name}")
    
    screenshot = ScreenshotCapture()
    vision = Vision(template_dir=templates_dir)
    executor = ActionExecutor(hwnd, mode="background")
    
    print("\n3秒后开始循环检测... (按q退出)")
    time.sleep(3)
    
    import msvcrt
    last_click_time = 0
    min_click_interval = 2.0
    
    while True:
        # 检查按键
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch.lower() in [b'q', b'\x1b']:
                print("\n退出")
                break
        
        # 截图
        img = screenshot.capture_to_cv2(hwnd)
        if img is None:
            print("截图失败，重试...")
            time.sleep(0.5)
            continue
        
        result_img = img.copy()
        found_any = False
        
        # 遍历所有模板
        for template_file in template_files:
            name = os.path.splitext(template_file)[0]
            
            # 尝试不同阈值
            for threshold in [0.8, 0.7, 0.6]:
                match = vision.detect_template(img, name, threshold=threshold)
                if match:
                    cx, cy, conf = match
                    found_any = True
                    
                    # 画标记
                    cv2.circle(result_img, (cx, cy), 8, (0, 0, 255), -1)
                    cv2.putText(result_img, f"{name} ({conf:.2f})", 
                                (cx + 10, cy - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    
                    now = time.time()
                    if now - last_click_time > min_click_interval:
                        print(f"  找到 [{name}] 位置({cx},{cy}) 置信度{conf:.2f} 阈值{threshold}")
                        print(f"  点击中...")
                        if executor.click(cx, cy):
                            print(f"  ✓ 点击完成")
                            last_click_time = now
                            time.sleep(1)
                        else:
                            print(f"  ✗ 点击失败")
                    break  # 找到就不用试更低阈值了
        
        # 显示结果（缩放）
        scale = 0.8
        h, w = result_img.shape[:2]
        display = cv2.resize(result_img, (int(w * scale), int(h * scale)))
        cv2.imshow("Vision Detection (按q退出)", display)
        
        key = cv2.waitKey(100) & 0xFF
        if key in [ord('q'), 27]:
            break
    
    cv2.destroyAllWindows()
    print("测试完成。")


if __name__ == "__main__":
    main()