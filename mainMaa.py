# -*- coding: utf-8 -*-
"""Maa_MHXY 功能移植到 game_agent 官网客户端的无界面运行入口。

保留 main.py(GUI 客户端)不动；本文件用于直接运行移植过来的日常任务。

用法:
    python mainMaa.py             # 默认运行「宝图任务(获得)」
    python mainMaa.py baotu       # 同上
    python mainMaa.py baotu --all # 对所有发现的游戏窗口并行运行

后续每移植一个 Maa 日常任务，只需:
    1. 在 tasks/ 下新增移植模块(可参照 tasks/baotu_maa.py);
    2. 在下方 MAA_TASKS 中登记，即可 `python mainMaa.py <任务id>` 运行。
"""

import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.orchestrator import AgentOrchestrator
from config.loader import ConfigLoader
from domain.tasks import TaskContext
from tasks.baotu_maa import BaotuMaaTask

# 已从 Maa_MHXY 移植过来的任务登记表。
# id: (显示名, 任务类)
MAA_TASKS = {
    "baotu": ("宝图任务(获得)", BaotuMaaTask),
}


def setup_logging(config):
    log_config = config.get_logging_config()
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    file_path = log_config.get("file_path", "game_agent.log")
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(file_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def build_orchestrator(config):
    window_config = config.get_window_config()
    vision_config = config.get_vision_config()
    return AgentOrchestrator(
        target_title_keywords=window_config.get("title_keywords", ["梦幻西游"]),
        target_class_names=window_config.get("class_names", ["UnityWndClass"]),
        template_dir=vision_config.get("template_dir", "templates"),
        blacklist_title_keywords=window_config.get("blacklist_title_keywords", []) + ["梦幻西游自动化助手"],
        blacklist_class_names=window_config.get("blacklist_class_names", []),
    )


def _make_progress_printer(hwnd):
    """返回一个把任务快照打印到控制台的回调，避免刷屏只打印变化的消息。"""
    last = {}

    def printer(snapshot):
        key = (snapshot.status, snapshot.message, snapshot.completed_steps)
        if key != last.get("key"):
            last["key"] = key
            print(f"[窗口 {hwnd}] 状态={snapshot.status.value} "
                  f"步骤={snapshot.completed_steps}/{snapshot.total_steps or '-'} "
                  f"{snapshot.message}")
    return printer


def run_task_on_agent(agent, task_cls):
    task = task_cls()
    hwnd = agent.hwnd
    try:
        task.run(TaskContext(agent=agent), _make_progress_printer(hwnd))
    except KeyboardInterrupt:
        task.stop()
        raise
    except Exception:
        logging.getLogger(__name__).exception("窗口=%s 任务执行失败", hwnd)
    return task


def is_elevated() -> bool:
    """前台点击需要管理员权限：游戏(MyGame_x64r.exe)通常以管理员运行，
    非管理员进程的合成鼠标事件会被 UIPI 拦截而无效。"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main(argv):
    task_id = argv[0] if argv and not argv[0].startswith("--") else "baotu"
    run_all = "--all" in argv

    if not is_elevated():
        print("=" * 68)
        print("警告：当前不是管理员权限运行。")
        print("梦幻西游官网客户端一般以管理员启动，非管理员进程的鼠标点击会被系统拦截，")
        print("表现为“截图/识别正常但点击无效”。请用管理员身份重新运行本脚本。")
        print("=" * 68)

    if task_id not in MAA_TASKS:
        print(f"未知任务: {task_id}，可选: {', '.join(MAA_TASKS)}")
        return 1

    name, task_cls = MAA_TASKS[task_id]

    config = ConfigLoader()
    setup_logging(config)
    logger = logging.getLogger(__name__)

    orchestrator = build_orchestrator(config)
    windows = orchestrator.discover_windows()
    if not windows:
        print("未找到梦幻西游游戏窗口。请先打开官网客户端并进入游戏。")
        return 1

    print(f"发现 {len(windows)} 个游戏窗口，任务：{name}")
    for w in windows:
        print(f"  - hwnd={w.hwnd} title={w.title!r} rect={w.rect}")

    agents = orchestrator.create_agents_for_all_windows()
    selected = agents if run_all else agents[:1]
    if not run_all and len(agents) > 1:
        print(f"多窗口模式下默认只运行第一个窗口；使用 --all 运行全部窗口。")

    if len(selected) == 1:
        # 单窗口：主线程同步运行，便于 Ctrl+C 停止。
        agent = selected[0]
        print(f"\n开始运行 {name}（窗口 hwnd={agent.hwnd}），Ctrl+C 停止...")
        try:
            run_task_on_agent(agent, task_cls)
        except KeyboardInterrupt:
            print("\n收到中断，已停止。")
        return 0

    # 多窗口：每个窗口一个工作线程。
    workers = []
    for agent in selected:
        t = threading.Thread(
            target=run_task_on_agent, args=(agent, task_cls),
            daemon=True, name=f"maa-{task_id}-{agent.hwnd}",
        )
        t.start()
        workers.append(t)

    try:
        while any(t.is_alive() for t in workers):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到中断，正在停止所有窗口...")
        orchestrator.stop_all_agents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
