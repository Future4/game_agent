import ctypes
import win32gui
import win32api
import win32con
import time

user32 = ctypes.windll.user32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

# 设置正确的函数签名
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_int
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.c_int

def get_cursor_pos():
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)

def test_mouse_control():
    print("=== 鼠标控制测试(已修复) ===")
    
    print("\n1. 获取当前位置:")
    pos = get_cursor_pos()
    print(f"   当前位置: {pos}")
    
    print("\n2. 移动到 (100, 100):")
    result = user32.SetCursorPos(100, 100)
    print(f"   SetCursorPos返回: {result}")
    time.sleep(0.5)
    pos = get_cursor_pos()
    print(f"   移动后位置: {pos}")
    
    print("\n3. 移动到 (500, 300):")
    result = user32.SetCursorPos(500, 300)
    print(f"   SetCursorPos返回: {result}")
    time.sleep(0.5)
    pos = get_cursor_pos()
    print(f"   移动后位置: {pos}")
    
    print("\n4. 测试鼠标点击(在当前位置):")
    pos = get_cursor_pos()
    print(f"   当前位置: {pos}")
    
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, pos[0], pos[1], 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, pos[0], pos[1], 0, 0)
    print("   点击已发送")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_mouse_control()