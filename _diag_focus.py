# -*- coding: utf-8 -*-
"""只读诊断：检查前台窗口、点击目标点下方的窗口、窗口可见性/z序。不做任何点击。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ctypes
import win32gui
import win32process
import win32con

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


def info(hwnd):
    if not hwnd:
        return "None"
    title = win32gui.GetWindowText(hwnd)
    cls = win32gui.GetClassName(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        pid = None
    try:
        proc = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(proc, 0, buf, ctypes.byref(size))
        exe = os.path.basename(buf.value)
    except Exception:
        exe = "?"
    return f"hwnd={hwnd} cls={cls!r} title={title!r} exe={exe}"


def find_game():
    res = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or cls == "UnityWndClass"):
            res.append(hwnd)
        return True

    win32gui.EnumWindows(cb, None)
    return res


def main():
    games = find_game()
    print("游戏窗口:", games)
    for g in games:
        print("  ", info(g))
        print("   rect:", win32gui.GetWindowRect(g), " visible:", win32gui.IsWindowVisible(g),
              " iconic:", win32gui.IsIconic(g))
        print("   ClientToScreen(255,31):", win32gui.ClientToScreen(g, (255, 31)))

    fg = win32gui.GetForegroundWindow()
    print("\n当前前台窗口:", info(fg))

    # 修复前会点到 (GetWindowRect.left+255, top+31) = (1238,85)
    # 修复后是 (1247,123)
    for pt in [(1247, 123), (1238, 85), (1247, 100)]:
        h = win32gui.WindowFromPoint(pt)
        # 取顶层所属窗口
        root = win32gui.GetAncestor(h, win32con.GA_ROOT)
        print(f"点 {pt} 处窗口: {info(h)}  | root: {info(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
