"""Built-in daily task catalogue and plugin registry."""
from typing import Dict, Iterable, Optional, Type

from domain.tasks import TaskDefinition
from tasks.base import AutomationTask, PlannedTask
from tasks.treasure_map import TreasureMapBanditTask


BUILTIN_TASKS = (
    TaskDefinition("treasure_map", "宝图任务", "自动完成宝图日常任务"),
    TaskDefinition("sect", "师门任务", "自动完成师门日常任务"),
    TaskDefinition("ghost", "捉鬼任务", "自动完成捉鬼日常任务"),
    TaskDefinition("escort", "运镖任务", "自动完成运镖日常任务"),
)


class TaskRegistry:
    def __init__(self) -> None:
        self._definitions: Dict[str, TaskDefinition] = {}
        self._factories: Dict[str, Type[AutomationTask]] = {}

    def register(self, definition: TaskDefinition, factory: Type[AutomationTask] = PlannedTask) -> None:
        self._definitions[definition.id] = definition
        self._factories[definition.id] = factory

    def register_builtins(self) -> None:
        for definition in BUILTIN_TASKS:
            self.register(definition, TreasureMapBanditTask if definition.id == "treasure_map" else PlannedTask)

    def definitions(self) -> Iterable[TaskDefinition]:
        return self._definitions.values()

    def get(self, task_id: str) -> Optional[TaskDefinition]:
        return self._definitions.get(task_id)

    def create(self, task_id: str) -> AutomationTask:
        if task_id not in self._factories:
            raise KeyError(f"Unknown task: {task_id}")
        return self._factories[task_id]()
