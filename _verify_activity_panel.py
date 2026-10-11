# -*- coding: utf-8 -*-
"""实测验证：真实点击「活动」入口打开活动面板，检查页面内模板识别情况，然后 ESC 关闭。

这是唯一需要真实操作游戏的一步(打开/关闭一个界面)，用于校准
daily_activity / treasure_row / 参加按钮 的识别。运行后会保存调试图。
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

import cv2

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


def report(tag, task, agent, save=None):
    img = agent.capture()
    if img is None:
        print(f"{tag}: 截图失败")
        return
    h, w = img.shape[:2]
    fr = task._fraction_region
    print(f"\n[{tag}] 截图 {w}x{h}")
    print("  日常活动  :", task._match_any(agent, (task.T_DAILY_ACTIVITY,), fr(w, h, task.ROI_DAILY_LEFT), task.TH_DAILY_ACTIVITY))
    row = task._match_any(agent, task.T_TREASURE_START, fr(w, h, task.ROI_LIST), task.TH_TREASURE_START)
    print("  宝图任务行:", row)
    if row:
        scale = row[3] if len(row) > 3 else 1.0
        target = (int(row[0] + task.JOIN_BTN_OFFSET_X * scale), int(row[1]))
        print(f"  -> 参加按钮推算位置: {target}")
    print("  宝图已完成:", task._match_any(agent, task.T_TREASURE_COMPLETED, fr(w, h, task.ROI_LIST_COMPLETED), task.TH_TREASURE_COMPLETED))
    if save:
        out = img.copy()
        if row:
            cv2.drawMarker(out, (int(row[0]), int(row[1])), (0, 0, 255), cv2.MARKER_CROSS, 40, 3)
            scale = row[3] if len(row) > 3 else 1.0
            target = (int(row[0] + task.JOIN_BTN_OFFSET_X * scale), int(row[1]))
            cv2.circle(out, target, 20, (255, 0, 0), 3)
            cv2.putText(out, "join-btn", (target[0] - 60, target[1] - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
        cv2.imwrite(os.path.abspath(save), out)
        print(f"  调试图已保存: {os.path.abspath(save)}")


def main():
    agent = build_agent()
    if agent is None:
        print("NO_WINDOW")
        return 1
    task = BaotuMaaTask()
    print(f"窗口 hwnd={agent.hwnd} rect={agent.window_info.rect}")

    img = agent.capture()
    h, w = img.shape[:2]
    btn = task._match_any(agent, task.T_ACTIVITY_BUTTON,
                          task._fraction_region(w, h, task.ROI_ACTIVITY_BUTTON), task.TH_ACTIVITY_BUTTON)
    print("活动入口匹配:", btn)
    if not btn:
        print("未找到活动入口，放弃。")
        return 1

    raw = agent.capture()
    cv2.imwrite(os.path.abspath("_diag_before_activity.png"), raw)
    print("点击活动入口 ->", btn[:2])
    agent.click(btn[0], btn[1])
    time.sleep(3.0)
    report("打开活动面板后", task, agent, save="_diag_activity_panel.png")

    print("\n按 ESC 关闭活动面板并返回主界面...")
    for _ in range(3):
        agent.press_key("esc")
        time.sleep(1.0)
        if task._on_main_interface(agent):
            break
    print("回到主界面:", task._on_main_interface(agent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
