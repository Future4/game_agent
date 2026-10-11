# -*- coding: utf-8 -*-
"""诊断：用整合后的 OCR 引擎（Windows 内置 OCR）识别游戏截图文字 + 包围盒。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import win32gui

from core.screenshot import ScreenshotCapture
from vision.vision import Vision


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


def main():
    hwnd = find_window()
    if not hwnd:
        print("NO_WINDOW")
        return 1
    img = ScreenshotCapture().capture_to_cv2(hwnd)
    if img is None:
        print("CAPTURE_FAIL")
        return 1
    h, w = img.shape[:2]
    print(f"capture {w}x{h}")

    v = Vision(template_dir="templates", use_paddle_ocr=False)
    print("windows_ocr:", getattr(v.ocr, "windows_ocr", None))
    rows = v.get_all_text(img)
    print(f"lines={len(rows)}")
    if not rows:
        print("NO TEXT RECOGNIZED")
        return 0

    rows.sort(key=lambda r: (r["center"][1], r["center"][0]))
    dump = os.path.abspath("_diag_ocr.txt")
    with open(dump, "w", encoding="utf-8") as f:
        for r in rows:
            cx, cy = r["center"]
            box = r["box"]
            x, y = box[0][0], box[0][1]
            bw, bh = box[1][0] - x, box[2][1] - y
            f.write(f"{r['text']}\tcenter=({cx},{cy})\tbox=({x},{y},{bw},{bh})\n")
    print("text dump ->", dump)
    for r in rows:
        cx, cy = r["center"]
        box = r["box"]
        x, y = box[0][0], box[0][1]
        bw, bh = box[1][0] - x, box[2][1] - y
        flag = "   <== 宝图" if "宝图" in r["text"] else ""
        print(f"{r['text']:<24} center=({cx:4d},{cy:4d}) box=({x:4d},{y:4d},{bw:3d},{bh:3d}){flag}")

    out = img.copy()
    for r in rows:
        box = r["box"]
        x, y = box[0][0], box[0][1]
        bw, bh = box[1][0] - x, box[2][1] - y
        color = (0, 0, 255) if "宝图" in r["text"] else (0, 200, 0)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
    p = os.path.abspath("_diag_ocr.png")
    cv2.imwrite(p, out)
    print("annotated ->", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
