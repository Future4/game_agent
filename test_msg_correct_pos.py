import win32gui
import win32api
import win32con
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def find_game_window():
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

def sendmessage_click(hwnd, x, y):
    """SendMessage点击"""
    pos = (y << 16) | (x & 0xFFFF)
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        return True
    except Exception as e:
        print(f"  SendMessage失败: {e}")
        return False

def postmessage_click(hwnd, x, y):
    """PostMessage点击"""
    pos = (y << 16) | (x & 0xFFFF)
    try:
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        return True
    except Exception as e:
        print(f"  PostMessage失败: {e}")
        return False

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    # 使用验证过的正确坐标
    x, y = 501, 109
    print(f"\n参加按钮正确坐标: 客户区({x}, {y})")
    
    # 测试1: SendMessage
    print("\n=== 测试1: SendMessage ===")
    print("3秒后点击...")
    time.sleep(3)
    sendmessage_click(hwnd, x, y)
    print("  ✓ SendMessage已发送")
    print("  等待3秒观察响应...")
    time.sleep(3)
    
    # 测试2: PostMessage
    print("\n=== 测试2: PostMessage ===")
    print("3秒后点击...")
    time.sleep(3)
    postmessage_click(hwnd, x, y)
    print("  ✓ PostMessage已发送")
    print("  等待3秒观察响应...")
    time.sleep(3)
    
    # 测试3: SendMessage连续点击
    print("\n=== 测试3: SendMessage连续点击3次 ===")
    for i in range(3):
        print(f"  第{i+1}次点击...")
        sendmessage_click(hwnd, x, y)
        time.sleep(1)
    print("  等待3秒观察响应...")
    time.sleep(3)
    
    print("\n=== 测试完成 ===")
    print("请告诉游戏是否有任何响应？")

if __name__ == "__main__":
    main()