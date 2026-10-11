import ctypes
import win32gui
import win32api
import win32con
import time

user32 = ctypes.windll.user32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_int
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.c_int

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

def real_click(screen_x, screen_y):
    """真实鼠标点击"""
    print(f"  移动鼠标到 ({screen_x}, {screen_y})...")
    user32.SetCursorPos(screen_x, screen_y)
    time.sleep(0.2)
    
    # 确认位置
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    print(f"  当前鼠标位置: ({point.x}, {point.y})")
    
    print("  发送点击...")
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)
    print("  ✓ 点击完成")

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    # 参加按钮的客户区坐标
    client_x, client_y = 612, 157
    
    # 转换为屏幕坐标
    screen_pos = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    print(f"\n参加按钮: 客户区({client_x},{client_y}) -> 屏幕({screen_pos[0]},{screen_pos[1]})")
    
    # 激活窗口
    print("\n激活游戏窗口...")
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(0.2)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    
    print("\n3秒后点击参加按钮...")
    time.sleep(3)
    
    # 点击
    print(f"\n执行点击:")
    real_click(screen_pos[0], screen_pos[1])
    
    print("\n等待2秒后再次点击...")
    time.sleep(2)
    real_click(screen_pos[0], screen_pos[1])
    
    print("\n请观察游戏是否有响应！")

if __name__ == "__main__":
    main()