import win32gui
import win32api
import win32con
import ctypes
from ctypes import wintypes
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

user32 = ctypes.windll.user32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ('dx', ctypes.c_long),
                ('dy', ctypes.c_long),
                ('mouseData', ctypes.c_uint32),
                ('dwFlags', ctypes.c_uint32),
                ('time', ctypes.c_uint32),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
            ]
        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ('wVk', ctypes.c_uint16),
                ('wScan', ctypes.c_uint16),
                ('dwFlags', ctypes.c_uint32),
                ('time', ctypes.c_uint32),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
            ]
        class _HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ('uMsg', ctypes.c_uint32),
                ('wParamL', ctypes.c_uint16),
                ('wParamH', ctypes.c_uint16),
            ]
        _fields_ = [
            ('mi', _MOUSEINPUT),
            ('ki', _KEYBDINPUT),
            ('hi', _HARDWAREINPUT),
        ]
    _anonymous_ = ('_input',)
    _fields_ = [
        ('type', ctypes.c_uint32),
        ('_input', _INPUT),
    ]

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

def send_input_click(screen_x, screen_y):
    """使用SendInput模拟鼠标点击"""
    try:
        x = int(screen_x * 65535 / (win32api.GetSystemMetrics(0) - 1))
        y = int(screen_y * 65535 / (win32api.GetSystemMetrics(1) - 1))
        
        inputs = []
        
        move_input = INPUT()
        move_input.type = INPUT_MOUSE
        move_input.mi.dx = x
        move_input.mi.dy = y
        move_input.mi.mouseData = 0
        move_input.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        move_input.mi.time = 0
        move_input.mi.dwExtraInfo = None
        inputs.append(move_input)
        
        down_input = INPUT()
        down_input.type = INPUT_MOUSE
        down_input.mi.dx = x
        down_input.mi.dy = y
        down_input.mi.mouseData = 0
        down_input.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE
        down_input.mi.time = 0
        down_input.mi.dwExtraInfo = None
        inputs.append(down_input)
        
        up_input = INPUT()
        up_input.type = INPUT_MOUSE
        up_input.mi.dx = x
        up_input.mi.dy = y
        up_input.mi.mouseData = 0
        up_input.mi.dwFlags = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE
        up_input.mi.time = 0
        up_input.mi.dwExtraInfo = None
        inputs.append(up_input)
        
        n_inputs = len(inputs)
        input_array = (INPUT * n_inputs)(*inputs)
        
        result = user32.SendInput(n_inputs, ctypes.byref(input_array), ctypes.sizeof(INPUT))
        if result == n_inputs:
            print("  ✓ SendInput点击成功")
            return True
        else:
            print(f"  ✗ SendInput返回: {result}, 错误码: {ctypes.GetLastError()}")
            return False
    except Exception as e:
        print(f"  ✗ SendInput失败: {e}")
        return False

def foreground_click_sendinput(hwnd, client_x, client_y):
    """使用SendInput进行前台点击"""
    try:
        screen_pos = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        print(f"  客户区({client_x},{client_y}) -> 屏幕({screen_pos[0]},{screen_pos[1]})")
        
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.1)
        
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        
        return send_input_click(screen_pos[0], screen_pos[1])
    except Exception as e:
        print(f"  ✗ 前台激活失败: {e}")
        return False

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    
    client_x, client_y = 612, 157
    print(f"\n准备使用SendInput前台点击参加按钮 客户区坐标: ({client_x}, {client_y})")
    print("3秒后开始点击...")
    time.sleep(3)
    
    print(f"\n执行SendInput前台点击 ({client_x}, {client_y})...")
    foreground_click_sendinput(hwnd, client_x, client_y)
    
    print("\n等待2秒后再次点击...")
    time.sleep(2)
    foreground_click_sendinput(hwnd, client_x, client_y)
    
    print("\n请观察游戏是否有响应")
    print("\n如果仍然失败，可能需要以管理员权限运行脚本")
    print("请尝试右键点击终端，选择'以管理员身份运行'")

if __name__ == "__main__":
    main()