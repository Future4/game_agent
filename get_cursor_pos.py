import win32gui
import win32api
import win32con
import time
import sys
import msvcrt

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

def get_cursor_client_pos(hwnd, prompt):
    """等待用户按回车后获取鼠标在窗口客户区的坐标"""
    print(f"\n>>> {prompt}")
    print("    请将鼠标移动到目标位置，然后按【回车键】确认...")
    
    # 实时显示鼠标坐标
    while True:
        cursor_pos = win32gui.GetCursorPos()
        client_pos = win32gui.ScreenToClient(hwnd, cursor_pos)
        print(f"\r    当前坐标: 屏幕({cursor_pos[0]},{cursor_pos[1]}) -> 客户区({client_pos[0]},{client_pos[1]})  按回车确认", end="", flush=True)
        
        # 检查是否有按键
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\r':  # 回车键
                print()
                return client_pos
        
        time.sleep(0.1)

def main():
    windows = find_game_window()
    if not windows:
        print("未找到游戏窗口！")
        return

    hwnd = windows[0]['hwnd']
    print(f"游戏窗口: HWND={hwnd}, Title={windows[0]['title']}")
    print()

    # 第一步：获取师门任务坐标
    sm_pos = get_cursor_client_pos(hwnd, "请将鼠标移到【师门任务】文字上")
    print(f"  ✓ 师门任务 客户区坐标: ({sm_pos[0]}, {sm_pos[1]})")

    # 第二步：获取参加按钮坐标
    cj_pos = get_cursor_client_pos(hwnd, "请将鼠标移到【参加】按钮上")
    print(f"  ✓ 参加按钮 客户区坐标: ({cj_pos[0]}, {cj_pos[1]})")

    # 汇总
    print("\n" + "=" * 50)
    print("坐标汇总:")
    print(f"  师门任务: ({sm_pos[0]}, {sm_pos[1]})")
    print(f"  参加按钮: ({cj_pos[0]}, {cj_pos[1]})")
    print(f"  位置关系: dx={cj_pos[0]-sm_pos[0]}, dy={cj_pos[1]-sm_pos[1]}")
    print(f"  参加按钮在师门任务{'右' if cj_pos[0] > sm_pos[0] else '左'}侧")

    # 点击参加按钮
    print(f"\n即将点击参加按钮 ({cj_pos[0]}, {cj_pos[1]})...")
    print("3秒后点击...")
    time.sleep(3)

    x, y = cj_pos
    pos = (y << 16) | (x & 0xFFFF)
    try:
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, pos)
        time.sleep(0.1)
        win32api.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, pos)
        print(f"  ✓ SendMessage点击已发送到 ({x}, {y})")
    except Exception as e:
        print(f"  ✗ 点击失败: {e}")

    print("\n请观察游戏是否有响应（如弹出任务界面、画面切换等）")

if __name__ == "__main__":
    main()