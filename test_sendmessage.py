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
                    'hwnd': hwnd,
                    'title': title,
                    'class_name': class_name,
                    'rect': rect
                })
        return True
    
    win32gui.EnumWindows(callback, None)
    return target_windows

def test_sendmessage_click_detailed(hwnd, x, y, desc=""):
    """详细的SendMessage点击测试"""
    print(f"\n--- 点击 ({x}, {y}) {desc} ---")
    
    pos = (y << 16) | (x & 0xFFFF)
    
    try:
        print(f"  发送 WM_LBUTTONDOWN...")
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        
        print(f"  发送 WM_LBUTTONUP...")
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        
        print(f"  ✓ 消息发送成功")
        return True
    except Exception as e:
        print(f"  ✗ 发送失败: {e}")
        return False

def test_sendmessage_with_wparam(hwnd, x, y):
    """测试不同的wParam参数"""
    pos = (y << 16) | (x & 0xFFFF)
    
    print(f"\n--- 测试不同wParam的SendMessage点击 ({x}, {y}) ---")
    
    # 测试1: MK_LBUTTON
    print("\n[测试1] wParam=MK_LBUTTON")
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.05)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        print("  ✓ 发送成功")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
    
    time.sleep(2)
    
    # 测试2: 包含MK_LBUTTON的多个键状态
    print("\n[测试2] wParam=MK_LBUTTON|MK_CONTROL")
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON | win32con.MK_CONTROL, pos)
        time.sleep(0.05)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        print("  ✓ 发送成功")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

def test_postmessage_with_child(hwnd):
    """尝试向子窗口发送消息"""
    print("\n=== 测试向子窗口发送消息 ===")
    
    child_windows = []
    
    def enum_child_proc(child_hwnd, lparam):
        child_windows.append(child_hwnd)
        return True
    
    win32gui.EnumChildWindows(hwnd, enum_child_proc, None)
    
    print(f"找到 {len(child_windows)} 个子窗口")
    
    for i, child_hwnd in enumerate(child_windows[:5]):
        child_title = win32gui.GetWindowText(child_hwnd)
        child_class = win32gui.GetClassName(child_hwnd)
        child_rect = win32gui.GetWindowRect(child_hwnd)
        print(f"  子窗口{i+1}: HWND={child_hwnd}, Title={child_title}, Class={child_class}, Rect={child_rect}")
        
        client_rect = win32gui.GetClientRect(child_hwnd)
        if client_rect[2] > 0 and client_rect[3] > 0:
            cx = (client_rect[2] - client_rect[0]) // 2
            cy = (client_rect[3] - client_rect[1]) // 2
            pos = (cy << 16) | (cx & 0xFFFF)
            
            try:
                print(f"    向子窗口发送点击 ({cx}, {cy})...")
                win32api.SendMessage(child_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
                time.sleep(0.05)
                win32api.SendMessage(child_hwnd, win32con.WM_LBUTTONUP, 0, pos)
                print(f"    ✓ 发送成功")
            except Exception as e:
                print(f"    ✗ 失败: {e}")

def test_sendmessage_various_points(hwnd):
    """测试多个不同的点击位置"""
    print("\n=== 测试多个位置SendMessage点击 ===")
    
    client_rect = win32gui.GetClientRect(hwnd)
    width = client_rect[2] - client_rect[0]
    height = client_rect[3] - client_rect[1]
    
    print(f"窗口客户区: {client_rect} (宽:{width}, 高:{height})")
    
    # 测试多个关键位置
    test_points = [
        (width // 2, height // 2, "中心"),
        (width // 4, height // 4, "左上四分之一"),
        (width * 3 // 4, height * 3 // 4, "右下四分之一"),
        (width // 2, height * 9 // 10, "底部中心"),
        (width // 2, height // 10, "顶部中心"),
    ]
    
    for x, y, desc in test_points:
        test_sendmessage_click_detailed(hwnd, x, y, desc)
        print("  等待2秒观察游戏响应...")
        time.sleep(2)

def test_sendmessage_sequence(hwnd):
    """测试连续点击序列"""
    print("\n=== 测试连续点击序列 ===")
    
    client_rect = win32gui.GetClientRect(hwnd)
    width = client_rect[2] - client_rect[0]
    height = client_rect[3] - client_rect[1]
    
    # 模拟双击
    print("\n[双击测试]")
    x, y = width // 2, height // 2
    pos = (y << 16) | (x & 0xFFFF)
    
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        time.sleep(0.1)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, pos)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        print(f"  ✓ 双击消息发送成功 ({x}, {y})")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
    
    time.sleep(3)
    
    # 模拟鼠标移动+点击
    print("\n[移动+点击测试]")
    try:
        for i in range(5):
            mx = width // 2 + i * 20
            my = height // 2 + i * 10
            mpos = (my << 16) | (mx & 0xFFFF)
            win32api.SendMessage(hwnd, win32con.WM_MOUSEMOVE, 0, mpos)
            time.sleep(0.05)
        
        final_pos = (height // 2 + 50) << 16 | ((width // 2 + 80) & 0xFFFF)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, final_pos)
        time.sleep(0.05)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, final_pos)
        print(f"  ✓ 移动+点击消息发送成功")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

def main():
    print("=== SendMessage 详细测试工具 ===")
    print("正在查找游戏窗口...")
    
    windows = find_game_window()
    
    if not windows:
        print("未找到游戏窗口！请先启动梦幻西游。")
        return
    
    print(f"\n找到 {len(windows)} 个游戏窗口:")
    for i, win in enumerate(windows):
        print(f"{i+1}. HWND: {win['hwnd']}, Title: {win['title']}, Class: {win['class_name']}, Rect: {win['rect']}")
    
    target_hwnd = windows[0]['hwnd']
    print(f"\n自动选择窗口: HWND={target_hwnd}")
    
    client_rect = win32gui.GetClientRect(target_hwnd)
    print(f"客户区: {client_rect}")
    
    print("\n" + "=" * 50)
    print("即将开始测试，请观察游戏窗口")
    print("=" * 50)
    
    # 测试1: 多位置点击
    test_sendmessage_various_points(target_hwnd)
    
    # 测试2: 不同wParam
    client_rect = win32gui.GetClientRect(target_hwnd)
    cx = (client_rect[2] - client_rect[0]) // 2
    cy = (client_rect[3] - client_rect[1]) // 2
    test_sendmessage_with_wparam(target_hwnd, cx, cy)
    
    # 测试3: 子窗口
    test_postmessage_with_child(target_hwnd)
    
    # 测试4: 连续操作
    test_sendmessage_sequence(target_hwnd)
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
    print("\n请回答以下问题:")
    print("1. 游戏窗口是否对任何SendMessage点击有响应？")
    print("2. 如果有响应，是哪些测试有响应？")
    print("3. 游戏画面是否有任何变化（如菜单弹出、角色移动等）？")

if __name__ == "__main__":
    main()