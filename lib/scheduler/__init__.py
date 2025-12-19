"""
Nightshift scheduler adapters.

Platform-agnostic scheduling for autonomous task execution.
"""

from .base import (
    Schedule,
    ScheduleStatus,
    SchedulerStatus,
    SchedulerAdapter,
    detect_platform,
    get_default_adapter,
    load_schedules,
)

from .cron_adapter import CronAdapter
from .systemd_adapter import SystemdAdapter

__all__ = [
    "Schedule",
    "ScheduleStatus",
    "SchedulerStatus",
    "SchedulerAdapter",
    "CronAdapter",
    "SystemdAdapter",
    "detect_platform",
    "get_default_adapter",
    "load_schedules",
]
