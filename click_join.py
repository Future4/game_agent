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

def send_click(hwnd, x, y):
    pos = (y << 16) | (x & 0xFFFF)
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        return True
    except Exception as e:
        print(f"点击失败: {e}")
        return False

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    x, y = 612, 157
    print(f"\n准备点击参加按钮 客户区坐标: ({x}, {y})")
    print("3秒后开始点击...")
    time.sleep(3)
    
    print(f"\n发送SendMessage点击 ({x}, {y})...")
    send_click(hwnd, x, y)
    print("点击已发送")
    
    print("\n等待2秒后再次点击...")
    time.sleep(2)
    send_click(hwnd, x, y)
    print("第二次点击已发送")
    
    print("\n请观察游戏是否有响应")
    print("如果游戏无响应，说明Unity不处理SendMessage消息")

if __name__ == "__main__":
    main()