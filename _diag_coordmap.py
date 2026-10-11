# -*- coding: utf-8 -*-
"""诊断：验证「截图坐标 -> 屏幕坐标」的真实映射，并对比活动面板打开前后画面差异。

关键问题：ScreenshotCapture 抓的是「客户区」还是「窗口矩形(含标题栏/边框)」？
- 若为窗口矩形：  screen = GetWindowRect.left/top + 截图坐标
- 若为客户区：    screen = ClientToScreen(0,0) + 截图坐标
用「整屏抓取窗口矩形后匹配同一模板」来实测定位真值。
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import win32gui
from PIL import ImageGrab

from agent.orchestrator import AgentOrchestrator
from config.loader import ConfigLoader
from tasks.baotu_maa import BaotuMaaTask


def build_agent():
    cfg = ConfigLoader()
    wc, vc = cfg.get_window_config(), cfg.get_vision_config()
    orch = AgentOrchestrator(
        target_title_keywords=wc.get("title_keywords", ["梦幻西游"]),
        target_class_names=wc.get("class_names", ["UnityWndClass"]),
        template_dir=vc.get("template_dir", "templates"),
        blacklist_title_keywords=wc.get("blacklist_title_keywords", []) + ["梦幻西游自动化助手"],
        blacklist_class_names=wc.get("blacklist_class_names", []),
    )
    agents = orch.create_agents_for_all_windows()
    return agents[0] if agents else None


def main():
    agent = build_agent()
    if agent is None:
        print("NO_WINDOW")
        return 1
    hwnd = agent.hwnd
    wl, wt, wr, wb = win32gui.GetWindowRect(hwnd)
    cl, ct = win32gui.ClientToScreen(hwnd, (0, 0))
    print(f"hwnd={hwnd}")
    print(f"window_rect=({wl},{wt},{wr},{wb}) size={wr-wl}x{wb-wt}")
    print(f"client_origin_screen=({cl},{ct})")
    print(f"边框偏移: window_origin-client_origin = ({wl-cl}, {wt-ct})")

    # 1) 客户区截图
    img_client = agent.capture()
    print(f"\n[capture_to_cv2] size={img_client.shape[1]}x{img_client.shape[0]}")
    m_client = agent.vision.detect_template_multiscale(img_client, "activity_button", 0.60)
    print(f"  activity_button 匹配: {m_client}")

    # 2) 整屏抓取「窗口矩形」区域
    grab = ImageGrab.grab(bbox=(wl, wt, wr, wb))
    grab_bgr = cv2.cvtColor(np.array(grab), cv2.COLOR_RGB2BGR)
    cv2.imwrite(os.path.abspath("_diag_windowrect_grab.png"), grab_bgr)
    print(f"\n[ImageGrab window_rect] size={grab_bgr.shape[1]}x{grab_bgr.shape[0]}")
    m_grab = agent.vision.detect_template_multiscale(grab_bgr, "activity_button", 0.60)
    print(f"  activity_button 匹配: {m_grab}")

    # 3) 结论
    if m_client and m_grab:
        dx = m_grab[0] - m_client[0]
        dy = m_grab[1] - m_client[1]
        print(f"\n真值(窗口矩形内位置) - 截图内位置 = ({dx}, {dy})")
        print(f"  -> 截图坐标系相对窗口矩形的偏移应为 (0,0) 才说明截图含标题栏")
        print(f"  当前截图匹配点 {m_client[:2]} ; 窗口矩形内真实位置 {m_grab[:2]}")
        print(f"  边框偏移 (window-client) = ({wl-cl}, {wt-ct})")
        if abs(dx) < 3 and abs(dy) < 3:
            print("  结论: 截图 = 窗口矩形坐标系 -> 前台点击用 GetWindowRect 原点 正确")
        elif abs(dx - (wl - cl)) < 3 and abs(dy - (wt - ct)) < 3:
            print("  结论: 截图 = 客户区坐标系 -> 前台点击应改用 ClientToScreen 原点 (当前代码有偏移!)")
        else:
            print("  结论: 未知映射，需人工判断")

    # 4) 活动面板前后差异
    for a, b in (("_diag_before_activity.png", "_diag_activity_panel.png"),):
        pa, pb = os.path.abspath(a), os.path.abspath(b)
        if os.path.exists(pa) and os.path.exists(pb):
            ia, ib = cv2.imread(pa), cv2.imread(pb)
            if ia is not None and ib is not None and ia.shape == ib.shape:
                diff = cv2.absdiff(ia, ib)
                print(f"\n[{a} vs {b}] 平均像素差={diff.mean():.2f} 最大={diff.max()} "
                      f"差异>30的像素占比={(np.mean(diff.max(axis=2) > 30) * 100):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
