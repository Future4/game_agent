# -*- coding: utf-8 -*-
"""离线验证：不真正操作游戏，检查 baotu_maa 的模板/识别节点在实机画面上的表现。

同时统计「Maa 模板在官网客户端的匹配得分」，用于判断哪些 Maa 图片可以直接沿用。
点击/按键/滑动全部被拦截为 no-op，只跑识别逻辑。
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from agent.orchestrator import AgentOrchestrator
from config.loader import ConfigLoader
from tasks.baotu_maa import BaotuMaaTask

# Maa baotu 流程涉及的模板（相对 templates/ 的路径，与 Maa image 目录一致）
MAA_TEMPLATES = [
    "zonghe/jiahao", "zonghe/chenghao", "zonghe/baoguo", "zonghe/baoguo_man",
    "zonghe/huodong_jiemian_panduan", "zonghe/huodong1", "zonghe/huodong2",
    "zonghe/rwl_suojin", "zonghe/rwl_suojin2",
    "zonghe/zidongxunlu1", "zonghe/zidongxunlu2", "zonghe/zidongxunlu3", "zonghe/zidongxunlu4",
    "zonghe/zhandoupingheng_guanbi1", "zonghe/jiuyoudiyu", "zonghe/jiuyoudiyu2",
    "baotu/baotu1", "baotu/baotu2", "baotu/baotu3",
    "baotu/hd_baotu_wancheng", "baotu/hd_baotu_wancheng2",
    "zhandou/zidong", "zhandou/quxiao", "zhandou/zhandou1", "zhandou/zhandou2", "zhandou/zhandou3",
]
# 本机针对官网客户端采集的平铺模板
LOCAL_TEMPLATES = ["activity_button", "daily_activity", "treasure_row", "treasure_completed",
                   "treasure_obtained", "baotu_dialogue"]


def tpl_path(name: str) -> str:
    return os.path.join("templates", *name.split("/")) + ".png"


def main():
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
    if not agents:
        print("NO_WINDOW")
        return 1
    agent = agents[0]
    print(f"window hwnd={agent.hwnd} rect={agent.window_info.rect}")

    task = BaotuMaaTask()

    names = set(MAA_TEMPLATES + LOCAL_TEMPLATES)
    for attr in ("T_MAIN_INDICATORS", "T_TASKBAR_COLLAPSED", "T_ACTIVITY_PANEL", "T_ACTIVITY_BUTTON",
                 "T_TREASURE_COMPLETED", "T_POPUP_CLOSE", "T_AUTOPATH", "T_BATTLE_BTN", "T_BATTLE_ICON"):
        names.update(getattr(task, attr))
    names.update(task.T_TREASURE_START)
    names.add(task.T_DAILY_ACTIVITY)
    names.add(task.T_TREASURE_OBTAINED)
    names.add(task.T_DIALOGUE)

    print("\n=== 1) template files present ===")
    missing = [n for n in sorted(names) if not os.path.exists(tpl_path(n))]
    for n in sorted(names):
        print(f"  {'OK  ' if os.path.exists(tpl_path(n)) else 'MISS'} {n}")
    print(f"  missing={len(missing)} {missing}")

    # 拦截所有会操作游戏的动作
    calls = []
    agent.click = lambda x, y, client_coords=True: (calls.append(("click", int(x), int(y))), True)[1]
    agent.click_fixed = lambda x, y: (calls.append(("click_fixed", int(x), int(y))), True)[1]
    agent.press_key = lambda k: (calls.append(("key", k)), True)[1]
    task._swipe_vertical = lambda a, fx, f1, f2, steps=1: calls.append(("swipe", round(fx, 2), round(f1, 2), round(f2, 2)))
    task._ensure_foreground = staticmethod(lambda hwnd: True)

    img = agent.capture()
    if img is None:
        print("capture failed")
        return 1
    h, w = img.shape[:2]
    fr = task._fraction_region

    print(f"\n=== 2) Maa templates vs current official-client screen ({w}x{h}) ===")
    print("  (score = best multi-scale match anywhere on screen; >=0.80 means directly reusable)")
    for n in MAA_TEMPLATES:
        m = task._match_any(agent, (n,), None, 0.0)
        if m:
            print(f"  {n:34s} score={m[2]:.3f} scale={m[3]:.2f} center=({m[0]},{m[1]})")
        else:
            print(f"  {n:34s} NO MATCH")

    print("\n=== 3) local (official-client) templates on current screen ===")
    for n in LOCAL_TEMPLATES:
        m = task._match_any(agent, (n,), None, 0.0)
        if m:
            print(f"  {n:24s} score={m[2]:.3f} scale={m[3]:.2f} center=({m[0]},{m[1]})")
        else:
            print(f"  {n:24s} NO MATCH")

    print("\n=== 4) node detection on current screen ===")
    print("  on_main_interface :", task._on_main_interface(agent))
    print("  in_battle         :", task._in_battle(img))
    print("  activity_button   :", task._match_any(agent, task.T_ACTIVITY_BUTTON, fr(w, h, task.ROI_ACTIVITY_BUTTON), task.TH_ACTIVITY_BUTTON))
    print("  activity_panel    :", task._match_any(agent, task.T_ACTIVITY_PANEL, None, 0.75))
    print("  daily_activity    :", task._match_any(agent, (task.T_DAILY_ACTIVITY,), fr(w, h, task.ROI_DAILY_LEFT), task.TH_DAILY_ACTIVITY))
    print("  treasure_start    :", task._match_any(agent, task.T_TREASURE_START, fr(w, h, task.ROI_LIST), task.TH_TREASURE_START))
    print("  treasure_completed:", task._match_any(agent, task.T_TREASURE_COMPLETED, fr(w, h, task.ROI_LIST_COMPLETED), task.TH_TREASURE_COMPLETED))
    print("  dialogue(listen)  :", task._match_any(agent, (task.T_DIALOGUE,), fr(w, h, task.ROI_DIALOGUE), task.TH_DIALOGUE))
    print("  popup_close       :", task._match_any(agent, task.T_POPUP_CLOSE, None, task.TH_POPUP_CLOSE))
    print("  autopath          :", task._match_any(agent, task.T_AUTOPATH, fr(w, h, task.ROI_AUTOPATH), task.TH_AUTOPATH))

    print("\n=== 5) dry-run nodes (actions intercepted) ===")
    calls.clear(); print("  node1 panduan      :", task._node_panduan_zhujiemian(agent), calls)
    calls.clear(); print("  task_bar_flow      :", task._task_bar_flow(agent), calls)
    calls.clear(); print("  open_activity+daily:", task._node_open_activity_and_daily(agent), calls)
    print("  is_finished        :", task._is_finished(agent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
