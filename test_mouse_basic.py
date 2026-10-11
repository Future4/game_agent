import ctypes
import win32gui
import win32api
import win32con
import time

user32 = ctypes.windll.user32

def get_cursor_pos():
    x = ctypes.c_long()
    y = ctypes.c_long()
    user32.GetCursorPos(ctypes.byref(x), ctypes.byref(y))
    return (x.value, y.value)

def test_mouse_control():
    """测试鼠标控制是否正常工作"""
    print("=== 鼠标控制测试 ===")
    
    print("\n1. 获取当前位置:")
    pos = get_cursor_pos()
    print(f"   当前位置: {pos}")
    
    print("\n2. 移动到 (100, 100):")
    result = user32.SetCursorPos(100, 100)
    print(f"   SetCursorPos返回: {result}")
    time.sleep(0.5)
    pos = get_cursor_pos()
    print(f"   移动后位置: {pos}")
    
    print("\n3. 移动到 (200, 300):")
    result = user32.SetCursorPos(200, 300)
    print(f"   SetCursorPos返回: {result}")
    time.sleep(0.5)
    pos = get_cursor_pos()
    print(f"   移动后位置: {pos}")
    
    print("\n4. 测试鼠标点击:")
    pos = get_cursor_pos()
    print(f"   当前位置: {pos}")
    
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, pos[0], pos[1], 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, pos[0], pos[1], 0, 0)
    print("   点击已发送")
    
    print("\n5. 测试SendInput:")
    x = int(pos[0] * 65535 / (win32api.GetSystemMetrics(0) - 1))
    y = int(pos[1] * 65535 / (win32api.GetSystemMetrics(1) - 1))
    
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    INPUT_HARDWARE = 2
    
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), 
                    ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                    ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
    
    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", ctypes.c_uint32), ("_input", _INPUT)]
    
    down = INPUT()
    down.type = INPUT_MOUSE
    down.mi.dx = x
    down.mi.dy = y
    down.mi.dwFlags = 0x0002 | 0x8000  # MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE
    
    up = INPUT()
    up.type = INPUT_MOUSE
    up.mi.dx = x
    up.mi.dy = y
    up.mi.dwFlags = 0x0004 | 0x8000  # MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE
    
    inputs = (INPUT * 2)(down, up)
    result = user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    print(f"   SendInput返回: {result}")
    
    print("\n测试完成！")
    
    if get_cursor_pos() == (200, 300):
        print("\n✓ 鼠标控制正常工作")
    else:
        print("\n✗ 鼠标控制可能被拦截")

if __name__ == "__main__":
    test_mouse_control()