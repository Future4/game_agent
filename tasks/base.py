"""Extensible task plugin API."""
import logging
import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional

from domain.tasks import TaskContext, TaskDefinition, TaskSnapshot, TaskStatus

logger = logging.getLogger(__name__)


class AutomationTask(ABC):
    """A user-visible daily activity.

    Implementations should put game-specific states in ``run`` (or delegate
    them to a state machine).  They must periodically check ``stop_event`` so
    the client can stop safely.
    """

    definition: TaskDefinition

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self.snapshot = TaskSnapshot(task_id=self.definition.id)

    def stop(self) -> None:
        self._stop_event.set()
        self.snapshot.status = TaskStatus.STOPPING

    def reset(self) -> None:
        self._stop_event.clear()
        self.snapshot = TaskSnapshot(task_id=self.definition.id)

    @abstractmethod
    def run(self, context: TaskContext, on_update: Optional[Callable[[TaskSnapshot], None]] = None) -> None:
        raise NotImplementedError


class PlannedTask(AutomationTask):
    """Safe placeholder until the exact in-game flow is specified.

    This is intentionally non-interacting: it gives the UI a real task
    lifecycle while preventing accidental clicks based on guessed coordinates.
    """

    def run(self, context: TaskContext, on_update=None) -> None:
        self.snapshot.status = TaskStatus.RUNNING
        self.snapshot.message = "任务流程待配置，当前不会操作游戏"
        if on_update:
            on_update(self.snapshot)
        self._stop_event.wait()
        self.snapshot.status = TaskStatus.STOPPING
        self.snapshot.message = "已停止"
        if on_update:
            on_update(self.snapshot)


class PollingTask(AutomationTask):
    """Base for tasks that advance by polling a game screenshot."""

    poll_interval = 0.5

    def wait_for_stop(self) -> bool:
        return self._stop_event.wait(self.poll_interval)
