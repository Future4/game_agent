import win32gui
import win32api
import win32con
import pyautogui
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

def get_window_info(hwnd):
    info = {}
    info['hwnd'] = hwnd
    info['title'] = win32gui.GetWindowText(hwnd)
    info['class_name'] = win32gui.GetClassName(hwnd)
    info['is_visible'] = win32gui.IsWindowVisible(hwnd)
    info['is_enabled'] = win32gui.IsWindowEnabled(hwnd)
    info['window_rect'] = win32gui.GetWindowRect(hwnd)
    info['client_rect'] = win32gui.GetClientRect(hwnd)
    
    foreground_hwnd = win32gui.GetForegroundWindow()
    info['is_foreground'] = (foreground_hwnd == hwnd)
    
    return info

def test_pyautogui_click(hwnd, client_x, client_y):
    """使用pyautogui进行点击"""
    try:
        screen_pos = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        print(f"  客户区({client_x},{client_y}) -> 屏幕({screen_pos[0]},{screen_pos[1]})")
        
        print("  检查窗口信息...")
        before = get_window_info(hwnd)
        print(f"    可见: {before['is_visible']}, 启用: {before['is_enabled']}, 前台: {before['is_foreground']}")
        
        print("  激活窗口...")
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.2)
        
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        
        after = get_window_info(hwnd)
        print(f"    激活后前台: {after['is_foreground']}")
        
        if not after['is_foreground']:
            print("  ⚠️ 警告: 窗口未能成为前台窗口")
        
        print("  移动鼠标并点击...")
        pyautogui.moveTo(screen_pos[0], screen_pos[1], duration=0.3)
        time.sleep(0.2)
        
        current_pos = pyautogui.position()
        print(f"    当前鼠标位置: {current_pos}")
        
        pyautogui.click()
        print("  ✓ pyautogui点击完成")
        
        time.sleep(0.5)
        
        pyautogui.click()
        print("  ✓ pyautogui第二次点击完成")
        
        return True
    except Exception as e:
        print(f"  ✗ pyautogui点击失败: {e}")
        return False

def test_direct_click_on_desktop(hwnd):
    """直接点击桌面测试pyautogui是否正常工作"""
    print("\n--- 测试pyautogui基本功能（点击桌面）---")
    try:
        current_pos = pyautogui.position()
        print(f"  当前鼠标位置: {current_pos}")
        
        test_x, test_y = 100, 100
        print(f"  移动到 ({test_x}, {test_y}) 并点击...")
        pyautogui.moveTo(test_x, test_y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        print("  ✓ 桌面点击成功")
        
        pyautogui.moveTo(current_pos[0], current_pos[1], duration=0.2)
        return True
    except Exception as e:
        print(f"  ✗ 桌面点击失败: {e}")
        return False

def main():
    print("=== pyautogui点击测试 ===")
    
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    info = get_window_info(hwnd)
    print(f"\n游戏窗口信息:")
    print(f"  HWND: {info['hwnd']}")
    print(f"  Title: {info['title']}")
    print(f"  Class: {info['class_name']}")
    print(f"  可见: {info['is_visible']}")
    print(f"  启用: {info['is_enabled']}")
    print(f"  前台: {info['is_foreground']}")
    print(f"  窗口矩形: {info['window_rect']}")
    print(f"  客户区: {info['client_rect']}")
    
    # 先测试桌面点击确认pyautogui正常
    test_direct_click_on_desktop(hwnd)
    
    client_x, client_y = 612, 157
    print(f"\n准备点击游戏按钮 客户区坐标: ({client_x}, {client_y})")
    print("3秒后开始...")
    time.sleep(3)
    
    print(f"\n执行pyautogui点击 ({client_x}, {client_y})...")
    test_pyautogui_click(hwnd, client_x, client_y)
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("如果游戏无响应，请尝试:")
    print("1. 以管理员身份运行终端")
    print("2. 确认游戏窗口在最前端")
    print("3. 检查坐标是否正确")

if __name__ == "__main__":
    main()