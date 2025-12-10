"""
Base scheduler adapter interface for nightshift.

All platform-specific schedulers inherit from this.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class ScheduleStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    NOT_INSTALLED = "not_installed"


@dataclass
class Schedule:
    """A scheduled job definition."""
    id: str
    description: str
    schedule: str  # Cron syntax: "0 2 * * *"
    command: str
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    status: ScheduleStatus = ScheduleStatus.NOT_INSTALLED


@dataclass
class SchedulerStatus:
    """Overall scheduler status."""
    backend: str
    available: bool
    schedules: List[Schedule]
    error: Optional[str] = None


class SchedulerAdapter(ABC):
    """
    Abstract base class for platform-specific scheduler adapters.

    Implementations:
    - CronAdapter: Unix cron
    - LaunchdAdapter: macOS launchd
    - SystemdAdapter: Linux systemd timers
    - DaemonAdapter: In-process (APScheduler)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this scheduler backend."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this scheduler backend is available on the current platform."""
        pass

    @abstractmethod
    def install(self, schedule: Schedule) -> bool:
        """
        Install a schedule on this platform.

        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def uninstall(self, schedule_id: str) -> bool:
        """
        Remove a schedule.

        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def list(self) -> List[Schedule]:
        """List all installed nightshift schedules."""
        pass

    @abstractmethod
    def status(self) -> SchedulerStatus:
        """Get overall scheduler status."""
        pass

    def install_all(self, schedules: List[Schedule]) -> dict:
        """
        Install multiple schedules.

        Returns dict of {schedule_id: success_bool}
        """
        results = {}
        for schedule in schedules:
            if schedule.enabled:
                results[schedule.id] = self.install(schedule)
        return results

    def uninstall_all(self) -> bool:
        """Remove all nightshift schedules."""
        success = True
        for schedule in self.list():
            if not self.uninstall(schedule.id):
                success = False
        return success


def detect_platform() -> str:
    """Detect the current platform for scheduler selection."""
    import platform
    system = platform.system().lower()

    if system == "darwin":
        return "macos"
    elif system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    else:
        return "unknown"


def get_default_adapter() -> SchedulerAdapter:
    """
    Get the default scheduler adapter for the current platform.

    Priority:
    - macOS: launchd
    - Linux: systemd (fallback to cron)
    - Windows: Task Scheduler
    - Other: Daemon (in-process)
    """
    platform = detect_platform()

    if platform == "macos":
        from .launchd_adapter import LaunchdAdapter
        return LaunchdAdapter()
    elif platform == "linux":
        # Try systemd first, fall back to cron
        from .cron_adapter import CronAdapter
        return CronAdapter()
    else:
        from .daemon_adapter import DaemonAdapter
        return DaemonAdapter()


def load_schedules(config_path: str = None) -> List[Schedule]:
    """
    Load schedule definitions from config file.

    Default: .datacore/modules/nightshift/schedules.yaml
    """
    import yaml
    from pathlib import Path

    if config_path is None:
        # Find datacore root
        config_path = Path.home() / "Data" / ".datacore" / "modules" / "nightshift" / "schedules.yaml"

    if not Path(config_path).exists():
        # Return defaults
        return [
            Schedule(
                id="nightly-execution",
                description="Process overnight task queue",
                schedule="0 2 * * *",
                command="nightshift run",
                enabled=True
            ),
            Schedule(
                id="morning-briefing",
                description="Generate /today briefing",
                schedule="0 7 * * *",
                command="nightshift today",
                enabled=True
            ),
        ]

    with open(config_path) as f:
        data = yaml.safe_load(f)

    schedules = []
    for item in data.get("schedules", []):
        schedules.append(Schedule(
            id=item["id"],
            description=item.get("description", ""),
            schedule=item["schedule"],
            command=item["command"],
            enabled=item.get("enabled", True)
        ))

    return schedules
