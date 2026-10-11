"""Orchestrates game agents and task plugins for the desktop client."""
import logging
import threading
from typing import Callable, Optional

from domain.tasks import TaskContext, TaskSnapshot, TaskStatus
from tasks.registry import TaskRegistry

logger = logging.getLogger(__name__)


class AutomationController:
    def __init__(self, orchestrator, registry: TaskRegistry) -> None:
        self.orchestrator = orchestrator
        self.registry = registry
        self._task = None
        self._thread: Optional[threading.Thread] = None
        self._snapshot = TaskSnapshot()
        self._listener: Optional[Callable[[TaskSnapshot], None]] = None
        self._workers = []

    def set_listener(self, listener: Callable[[TaskSnapshot], None]) -> None:
        self._listener = listener

    @property
    def snapshot(self) -> TaskSnapshot:
        return self._snapshot

    def discover_agents(self):
        self.orchestrator.create_agents_for_all_windows()
        agents = list(self.orchestrator.agents.values())
        logger.info("已发现游戏窗口：%s", [(a.hwnd, a.window_info.title) for a in agents])
        return agents

    def start(self, task_id: str, hwnd: Optional[int] = None) -> None:
        if self.is_running:
            raise RuntimeError("已有任务正在运行")
        agent = self.orchestrator.get_agent(hwnd) if hwnd else next(iter(self.orchestrator.agents.values()), None)
        if agent is None:
            raise RuntimeError("未找到梦幻西游游戏窗口")
        self._task = self.registry.create(task_id)
        self._task.reset()
        self._snapshot = self._task.snapshot
        self._task.snapshot.status = TaskStatus.RUNNING
        self._emit()
        self._thread = threading.Thread(
            target=self._run_task, args=(agent,), daemon=True, name=f"task-{task_id}"
        )
        self._thread.start()

    def start_all(self, task_id: str) -> None:
        """Start an independent task instance for every game window."""
        agents = self.discover_agents()
        if not agents:
            raise RuntimeError("未找到梦幻西游游戏窗口")
        if self.is_running:
            raise RuntimeError("已有任务正在运行")
        self._workers = []
        for agent in agents:
            task = self.registry.create(task_id)
            task.reset()
            worker = threading.Thread(
                target=self._run_independent_task,
                args=(task, agent),
                daemon=True,
                name=f"task-{task_id}-{agent.hwnd}",
            )
            self._workers.append((task, worker))
            logger.info("启动任务=%s，窗口=%s，线程=%s", task_id, agent.hwnd, worker.name)
            worker.start()

    def _run_independent_task(self, task, agent) -> None:
        try:
            logger.info("任务线程进入：任务=%s，窗口=%s", task.definition.id, agent.hwnd)
            task.run(TaskContext(agent=agent), self._on_task_update)
            logger.info("任务线程退出：任务=%s，窗口=%s，状态=%s", task.definition.id, agent.hwnd, task.snapshot.status)
        except Exception:
            logger.exception("窗口=%s 的任务执行失败", agent.hwnd)

    def _run_task(self, agent) -> None:
        try:
            self._task.run(TaskContext(agent=agent), self._on_task_update)
        except Exception as exc:
            logger.exception("任务执行失败")
            self._snapshot.status = TaskStatus.FAILED
            self._snapshot.message = str(exc)
            self._emit()

    def _on_task_update(self, snapshot: TaskSnapshot) -> None:
        self._snapshot = snapshot
        self._emit()

    def _emit(self) -> None:
        if self._listener:
            self._listener(self._snapshot)

    def stop(self) -> None:
        if self._task:
            self._task.stop()
        for task, _ in self._workers:
            task.stop()

    @property
    def is_running(self) -> bool:
        single = bool(self._thread and self._thread.is_alive() and self._task and self._task.snapshot.status in (TaskStatus.RUNNING, TaskStatus.STOPPING))
        many = any(worker.is_alive() for _, worker in self._workers)
        return single or many

    def shutdown(self) -> None:
        self.stop()
        if self._thread:
            self._thread.join(timeout=2)
        self.orchestrator.stop_all_agents()
