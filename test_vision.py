import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture
from vision.vision import Vision
import cv2
import time


def find_game_window():
    import win32gui
    target_windows = []
    def callback(hwnd, extra):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or class_name == "UnityWndClass"):
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            if width > 100 and height > 100:
                target_windows.append({
                    'hwnd': hwnd, 'title': title, 'class_name': class_name, 'rect': rect
                })
        return True
    win32gui.EnumWindows(callback, None)
    return target_windows


def main():
    print("=== 视觉识别模块测试 ===")
    
    # 查找游戏窗口
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return
    
    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    # 初始化截图和视觉模块
    screenshot = ScreenshotCapture()
    vision = Vision()
    
    print("\n3秒后开始截图测试...")
    time.sleep(3)
    
    # 截图
    img = screenshot.capture_to_cv2(hwnd)
    if img is None:
        print("截图失败！")
        return
    
    print(f"截图成功: {img.shape[1]}x{img.shape[0]}")
    
    # 保存截图
    cv2.imwrite("vision_test_screenshot.png", img)
    print("截图已保存: vision_test_screenshot.png")
    
    # 测试1: OCR识别
    print("\n=== 测试1: OCR识别 ===")
    print("正在识别图像中的文本...")
    start_time = time.time()
    texts = vision.get_all_text(img)
    elapsed = time.time() - start_time
    print(f"识别完成，耗时: {elapsed:.2f}秒")
    
    if texts:
        print(f"识别到 {len(texts)} 个文本:")
        for i, text in enumerate(texts):
            print(f"  {i+1}. '{text['text']}' (置信度: {text['confidence']:.2f}, 位置: {text['center']})")
    else:
        print("未识别到任何文本")
    
    # 测试2: 查找特定文本
    print("\n=== 测试2: 查找特定文本 ===")
    test_texts = ["任务", "师门", "参加", "开始"]
    
    for text in test_texts:
        pos = vision.detect_text(img, text)
        if pos:
            print(f"✓ 找到 '{text}' 在位置: {pos}")
        else:
            print(f"✗ 未找到 '{text}'")
    
    # 测试3: 检测游戏状态
    print("\n=== 测试3: 游戏状态检测 ===")
    state = vision.detect_state(img)
    print(f"当前游戏状态: {state}")
    
    # 测试4: 查找按钮
    print("\n=== 测试4: 按钮查找 ===")
    join_btn = vision.find_join_button(img)
    if join_btn:
        print(f"✓ 找到参加按钮在位置: {join_btn}")
    else:
        print("✗ 未找到参加按钮")
    
    task_btn = vision.find_task_button(img)
    if task_btn:
        print(f"✓ 找到任务按钮在位置: {task_btn}")
    else:
        print("✗ 未找到任务按钮")
    
    print("\n=== 测试完成 ===")
    
    # 如果找到了参加按钮，询问是否点击
    if join_btn:
        choice = input(f"\n是否点击参加按钮({join_btn})? (y/n): ")
        if choice.lower() == 'y':
            print("\n正在点击参加按钮...")
            from core.action_executor import ActionExecutor
            executor = ActionExecutor(hwnd, mode="background")
            executor.click(join_btn[0], join_btn[1])
            print("点击完成！")


if __name__ == "__main__":
    main()