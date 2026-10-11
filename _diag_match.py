# -*- coding: utf-8 -*-
"""诊断：对当前游戏画面做多尺度模板匹配，定位官网客户端各 UI 元素。"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import win32gui

from core.screenshot import ScreenshotCapture

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

MAA_BASE = r"D:\fuye\mcp\Maa_MHXY-main\assets\resource\base\image"


def find_window():
    res = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        cls = win32gui.GetClassName(hwnd)
        if win32gui.IsWindowVisible(hwnd) and ("梦幻西游" in title or cls == "UnityWndClass"):
            res.append(hwnd)
        return True

    win32gui.EnumWindows(cb, None)
    return res[0] if res else None


def multiscale_match(img, tpl, scales=(0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0)):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    best = None
    for s in scales:
        w = max(1, int(tpl.shape[1] * s))
        h = max(1, int(tpl.shape[0] * s))
        if h > gray.shape[0] or w > gray.shape[1]:
            continue
        r = cv2.resize(tpl_gray, (w, h), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        res = cv2.matchTemplate(gray, r, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        cand = (float(score), s, loc[0], loc[1], w, h)
        if best is None or cand[0] > best[0]:
            best = cand
    return best


def main():
    hwnd = find_window()
    if not hwnd:
        print("NO_WINDOW")
        return 1
    cap = ScreenshotCapture()
    img = cap.capture_to_cv2(hwnd)
    if img is None:
        print("CAPTURE_FAIL")
        return 1
    h, w = img.shape[:2]
    out = os.path.abspath("_diag_now.png")
    cv2.imwrite(out, img)
    print(f"CAPTURE {w}x{h} -> {out}")

    ga_templates = [
        "activity_button", "daily_activity", "treasure_row", "treasure_completed",
        "treasure_obtained", "baotu_dialogue", "baotu_module", "join_button",
        "bag_btn", "treasure_map_icon", "activite_page", "sectTask_module",
    ]
    for name in ga_templates:
        p = os.path.join("templates", name + ".png")
        if not os.path.exists(p):
            continue
        tpl = cv2.imread(p)
        if tpl is None:
            continue
        r = multiscale_match(img, tpl)
        if r and r[0] >= 0.5:
            cx, cy = r[2] + r[4] // 2, r[3] + r[5] // 2
            print(f"GA {name}: score={r[0]:.3f} scale={r[1]:.2f} center=({cx},{cy}) size={r[4]}x{r[5]}")
        else:
            print(f"GA {name}: NO best={r[0]:.3f}@{r[1]:.2f}" if r else f"GA {name}: NO")

    maa_templates = [
        "zonghe/jiahao.png", "zonghe/chenghao.png", "zonghe/baoguo.png", "zonghe/baoguo_man.png",
        "zonghe/rwl_suojin.png", "zonghe/rwl_suojin2.png", "zonghe/huodong_jiemian_panduan.png",
        "zonghe/zidongxunlu1.png", "zonghe/zidongxunlu2.png", "zonghe/zidongxunlu3.png",
        "zonghe/zhujiemian_shiyong_cha.png", "zonghe/renwu_tanchuang.png",
        "zhandou/zidong.png", "zhandou/quxiao.png", "zhandou/zhandou1.png",
        "baotu/baotu1.png", "baotu/baotu2.png", "baotu/hd_baotu_wancheng.png", "baotu/cangbaotu.png",
    ]
    for rel in maa_templates:
        p = os.path.join(MAA_BASE, rel)
        if not os.path.exists(p):
            continue
        tpl = cv2.imread(p)
        if tpl is None:
            continue
        r = multiscale_match(img, tpl)
        if r:
            cx, cy = r[2] + r[4] // 2, r[3] + r[5] // 2
            print(f"MAA {rel}: score={r[0]:.3f} scale={r[1]:.2f} center=({cx},{cy}) size={r[4]}x{r[5]}")
        else:
            print(f"MAA {rel}: NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
