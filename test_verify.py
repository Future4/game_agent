import win32gui
import win32api
import win32con
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.screenshot import ScreenshotCapture

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

def test_postmessage_click(hwnd):
    print(f"\n=== Testing PostMessage click on HWND: {hwnd} ===")
    
    client_rect = win32gui.GetClientRect(hwnd)
    center_x = (client_rect[2] - client_rect[0]) // 2
    center_y = (client_rect[3] - client_rect[1]) // 2
    
    pos = (center_y << 16) | (center_x & 0xFFFF)
    
    print(f"Client rect: {client_rect}")
    print(f"Clicking at center: ({center_x}, {center_y})")
    
    try:
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.05)
        win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        
        print("PostMessage click sent successfully")
        print("Wait 3 seconds and check if the game responded...")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"PostMessage click failed: {e}")
        return False

def test_sendmessage_click(hwnd):
    print(f"\n=== Testing SendMessage click on HWND: {hwnd} ===")
    
    client_rect = win32gui.GetClientRect(hwnd)
    center_x = (client_rect[2] - client_rect[0]) // 2
    center_y = (client_rect[3] - client_rect[1]) // 2
    
    pos = (center_y << 16) | (center_x & 0xFFFF)
    
    print(f"Client rect: {client_rect}")
    print(f"Clicking at center: ({center_x}, {center_y})")
    
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.05)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        
        print("SendMessage click sent successfully")
        print("Wait 3 seconds and check if the game responded...")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"SendMessage click failed: {e}")
        return False

def test_foreground_click(hwnd):
    print(f"\n=== Testing foreground click on HWND: {hwnd} ===")
    
    client_rect = win32gui.GetClientRect(hwnd)
    center_x = (client_rect[2] - client_rect[0]) // 2
    center_y = (client_rect[3] - client_rect[1]) // 2
    
    screen_pos = win32gui.ClientToScreen(hwnd, (center_x, center_y))
    
    print(f"Client rect: {client_rect}")
    print(f"Screen position: {screen_pos}")
    
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        
        win32api.SetCursorPos(screen_pos)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_pos[0], screen_pos[1], 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_pos[0], screen_pos[1], 0, 0)
        
        print("Foreground click sent successfully")
        print("Wait 3 seconds and check if the game responded...")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"Foreground click failed: {e}")
        return False

def test_screenshot(hwnd):
    print(f"\n=== Testing screenshot on HWND: {hwnd} ===")
    
    capture = ScreenshotCapture()
    
    print("Testing PrintWindow with different flags...")
    
    flags = [0, 2, 3]
    for flag in flags:
        print(f"\n--- Testing flag={flag} ---")
        try:
            img = capture.capture_printwindow_with_flag(hwnd, flag)
            if img is not None:
                print(f"SUCCESS: Captured image size: {img.size}")
                save_path = f"screenshot_flag_{flag}.png"
                img.save(save_path)
                print(f"Saved to: {save_path}")
            else:
                print("FAILED: Returned None")
        except Exception as e:
            print(f"ERROR: {e}")
    
    print("\n--- Testing BitBlt ---")
    try:
        img = capture.capture_bitblt(hwnd)
        if img is not None:
            print(f"SUCCESS: Captured image size: {img.size}")
            save_path = "screenshot_bitblt.png"
            img.save(save_path)
            print(f"Saved to: {save_path}")
        else:
            print("FAILED: Returned None")
    except Exception as e:
        print(f"ERROR: {e}")

def main():
    print("=== Game Automation Verification Tool ===")
    print("Looking for game windows...")
    
    windows = find_game_window()
    
    if not windows:
        print("No game windows found!")
        print("Please launch 梦幻西游 and try again.")
        return
    
    print(f"\nFound {len(windows)} game windows:")
    for i, win in enumerate(windows):
        print(f"{i+1}. HWND: {win['hwnd']}, Title: {win['title']}, Class: {win['class_name']}, Rect: {win['rect']}")
    
    choice = int(input("\nEnter the number of the window to test: ")) - 1
    if choice < 0 or choice >= len(windows):
        print("Invalid choice")
        return
    
    target_hwnd = windows[choice]['hwnd']
    
    print("\nWhat tests would you like to run?")
    print("1. PostMessage click test")
    print("2. SendMessage click test")
    print("3. Foreground click test")
    print("4. Screenshot test")
    print("5. All tests")
    
    test_choice = int(input("\nEnter your choice: "))
    
    if test_choice == 1 or test_choice == 5:
        test_postmessage_click(target_hwnd)
    
    if test_choice == 2 or test_choice == 5:
        test_sendmessage_click(target_hwnd)
    
    if test_choice == 3 or test_choice == 5:
        test_foreground_click(target_hwnd)
    
    if test_choice == 4 or test_choice == 5:
        test_screenshot(target_hwnd)
    
    print("\n=== Test completed ===")
    print("Please review the results and check if the game responded to clicks.")
    print("If PostMessage/SendMessage doesn't work, we'll need to use foreground clicking.")

if __name__ == "__main__":
    main()