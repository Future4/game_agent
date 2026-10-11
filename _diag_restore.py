# -*- coding: utf-8 -*-
"""诊断：还原被最小化的游戏窗口（尽量不抢焦点），便于截图/识别。"""
import win32con
import win32gui


def restore_no_activate(hwnd) -> bool:
    try:
        wp = win32gui.GetWindowPlacement(hwnd)
        # (flags, showCmd, ptMinPosition, ptMaxPosition, rcNormalPosition)
        if wp[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.SetWindowPlacement(
                hwnd, (wp[0], win32con.SW_SHOWNOACTIVATE, wp[2], wp[3], wp[4])
            )
            return True
    except Exception as exc:
        print("SetWindowPlacement failed:", exc)
    return False


def main():
    found = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or cls == "UnityWndClass"):
            found.append(hwnd)
            print(f"hwnd={hwnd} iconic_before={win32gui.IsIconic(hwnd)}")
            if win32gui.IsIconic(hwnd):
                ok = restore_no_activate(hwnd)
                print("  SetWindowPlacement ok:", ok)
                if win32gui.IsIconic(hwnd):
                    print("  fallback ShowWindow(SW_RESTORE)")
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return True

    win32gui.EnumWindows(cb, None)
    if not found:
        print("NO_WINDOW")
        return 1
    import time
    time.sleep(1.5)
    for h in found:
        print(f"hwnd={h} iconic_after={win32gui.IsIconic(h)} rect={win32gui.GetWindowRect(h)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
