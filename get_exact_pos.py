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

def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    
    # 获取窗口详细信息
    win_rect = win32gui.GetWindowRect(hwnd)
    client_rect = win32gui.GetClientRect(hwnd)
    
    # ClientToScreen转换
    client_origin_screen = win32gui.ClientToScreen(hwnd, (0, 0))
    target_screen = win32gui.ClientToScreen(hwnd, (612, 157))
    
    print("=== 窗口坐标信息 ===")
    print(f"窗口矩形: {win_rect}")
    print(f"  左上: ({win_rect[0]}, {win_rect[1]})")
    print(f"  右下: ({win_rect[2]}, {win_rect[3]})")
    print(f"  尺寸: {win_rect[2]-win_rect[0]} x {win_rect[3]-win_rect[1]}")
    print(f"\n客户区矩形: {client_rect}")
    print(f"  尺寸: {client_rect[2]} x {client_rect[3]}")
    print(f"\n客户区原点(0,0)在屏幕上的位置: {client_origin_screen}")
    print(f"  即窗口边框宽度: {client_origin_screen[0]-win_rect[0]}")
    print(f"  即标题栏+边框高度: {client_origin_screen[1]-win_rect[1]}")
    print(f"\n目标点(612,157)在屏幕上的位置: {target_screen}")
    
    print("\n" + "=" * 50)
    print("请将鼠标移到游戏中的【参加】按钮上")
    print("然后按回车键确认坐标")
    print("=" * 50)
    
    while True:
        pos = get_cursor_pos()
        # 计算对应的客户区坐标
        client_pos = win32gui.ScreenToClient(hwnd, pos)
        print(f"\r  屏幕({pos[0]},{pos[1]}) -> 客户区({client_pos[0]},{client_pos[1]})  按回车确认", end="", flush=True)
        
        # 非阻塞检查按键
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\r':
                print()
                print(f"\n✓ 确认参加按钮屏幕坐标: ({pos[0]}, {pos[1]})")
                print(f"✓ 对应客户区坐标: ({client_pos[0]}, {client_pos[1]})")
                
                # 3秒后点击这个坐标
                print("\n3秒后点击这个位置...")
                time.sleep(3)
                
                user32.SetCursorPos(pos[0], pos[1])
                time.sleep(0.2)
                
                print("发送点击...")
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, pos[0], pos[1], 0, 0)
                time.sleep(0.05)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, pos[0], pos[1], 0, 0)
                print("✓ 点击完成！请观察游戏响应")
                break
        
        time.sleep(0.1)

if __name__ == "__main__":
    main()