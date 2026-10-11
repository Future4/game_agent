"""Task contracts shared by the client and automation engine.

The task layer deliberately does not know anything about Tkinter, windows, or
OpenCV.  Concrete task implementations can be added later without changing
the desktop client.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    name: str
    description: str
    enabled: bool = True


@dataclass
class TaskContext:
    """Runtime dependencies passed to a task plugin."""

    agent: Any
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSnapshot:
    task_id: Optional[str] = None
    status: TaskStatus = TaskStatus.IDLE
    message: str = ""
    completed_steps: int = 0
    total_steps: Optional[int] = None
