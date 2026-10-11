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

def foreground_click(hwnd, client_x, client_y):
    """前台点击：激活窗口后用真实鼠标点击"""
    try:
        screen_pos = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        print(f"  客户区({client_x},{client_y}) -> 屏幕({screen_pos[0]},{screen_pos[1]})")
        
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.1)
        
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        
        win32api.SetCursorPos(screen_pos)
        time.sleep(0.1)
        
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_pos[0], screen_pos[1], 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_pos[0], screen_pos[1], 0, 0)
        
        print("  ✓ 前台点击成功")
        return True
    except Exception as e:
        print(f"  ✗ 前台点击失败: {e}")
        return False

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    client_x, client_y = 612, 157
    print(f"\n准备前台点击参加按钮 客户区坐标: ({client_x}, {client_y})")
    print("3秒后开始点击...")
    time.sleep(3)
    
    print(f"\n执行前台点击 ({client_x}, {client_y})...")
    foreground_click(hwnd, client_x, client_y)
    
    print("\n等待2秒后再次点击...")
    time.sleep(2)
    foreground_click(hwnd, client_x, client_y)
    
    print("\n请观察游戏是否有响应")

if __name__ == "__main__":
    main()