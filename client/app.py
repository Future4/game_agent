"""Tkinter desktop client entry point."""
import logging
import tkinter as tk
from tkinter import messagebox, ttk

from application.controller import AutomationController
from tasks.registry import TaskRegistry

logger = logging.getLogger(__name__)


class DesktopClient:
    def __init__(self, controller: AutomationController) -> None:
        self.controller = controller
        self.controller.set_listener(self._on_snapshot)
        self.root = tk.Tk()
        self.root.title("梦幻西游自动化助手")
        self.root.geometry("620x430")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="梦幻西游自动化助手", font=("Microsoft YaHei", 16, "bold")).pack(anchor=tk.W)
        ttk.Label(frame, text="选择游戏窗口和日常任务，然后启动自动化流程。",).pack(anchor=tk.W, pady=(4, 12))
        row = ttk.Frame(frame); row.pack(fill=tk.X)
        ttk.Label(row, text="游戏窗口：").pack(side=tk.LEFT)
        self.window_var = tk.StringVar(value="扫描中...")
        self.window_box = ttk.Combobox(row, textvariable=self.window_var, state="readonly", width=45)
        self.window_box.pack(side=tk.LEFT, padx=8)
        ttk.Button(row, text="刷新", command=self.refresh_windows).pack(side=tk.LEFT)
        self.all_windows_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="全部窗口", variable=self.all_windows_var).pack(side=tk.LEFT, padx=8)
        ttk.Label(frame, text="日常任务：").pack(anchor=tk.W, pady=(14, 4))
        self.task_frame = ttk.Frame(frame); self.task_frame.pack(fill=tk.X)
        self.task_var = tk.StringVar()
        for definition in self.controller.registry.definitions():
            ttk.Radiobutton(self.task_frame, text=definition.name, value=definition.id, variable=self.task_var).pack(side=tk.LEFT, padx=(0, 12))
        self.task_var.set(next(iter(self.controller.registry.definitions())).id)
        actions = ttk.Frame(frame); actions.pack(anchor=tk.W, pady=18)
        self.start_button = ttk.Button(actions, text="开启自动任务", command=self.start); self.start_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state=tk.DISABLED); self.stop_button.pack(side=tk.LEFT, padx=8)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)
        self.refresh_windows()

    def refresh_windows(self) -> None:
        agents = self.controller.discover_agents()
        self._agents = agents
        values = [f"{a.window_info.title} ({a.hwnd})" for a in agents]
        self.window_box["values"] = values or ["未找到游戏窗口"]
        self.window_box.current(0)

    def start(self) -> None:
        try:
            logger.info("点击启动：任务=%s，全部窗口=%s，窗口数量=%s", self.task_var.get(), self.all_windows_var.get(), len(getattr(self, "_agents", [])))
            if self.all_windows_var.get():
                self.controller.start_all(self.task_var.get())
            else:
                index = self.window_box.current()
                self.controller.start(self.task_var.get(), self._agents[index].hwnd)
            self.start_button["state"] = tk.DISABLED; self.stop_button["state"] = tk.NORMAL
        except Exception as exc:
            messagebox.showerror("无法启动", str(exc))

    def stop(self) -> None:
        logger.info("点击停止")
        self.controller.stop()
        self.start_button["state"] = tk.NORMAL; self.stop_button["state"] = tk.DISABLED

    def _on_snapshot(self, snapshot) -> None:
        self.root.after(0, lambda: self.status_var.set(snapshot.message or snapshot.status.value))

    def close(self) -> None:
        self.controller.shutdown(); self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
