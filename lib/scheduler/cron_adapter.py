"""
Cron scheduler adapter for nightshift.

Uses system crontab for scheduling.
"""

import subprocess
import re
from typing import List, Optional
from pathlib import Path

from .base import SchedulerAdapter, Schedule, SchedulerStatus, ScheduleStatus


class CronAdapter(SchedulerAdapter):
    """
    Unix cron scheduler adapter.

    Manages nightshift schedules via user crontab.
    Uses marker comments to identify nightshift entries.
    """

    MARKER_START = "# NIGHTSHIFT_START"
    MARKER_END = "# NIGHTSHIFT_END"
    MARKER_JOB = "# nightshift:"

    @property
    def name(self) -> str:
        return "cron"

    def is_available(self) -> bool:
        """Check if crontab is available."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Exit code 0 or 1 (no crontab) both mean cron is available
            return result.returncode in [0, 1]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def install(self, schedule: Schedule) -> bool:
        """Install a schedule to crontab."""
        try:
            # Get current crontab
            current = self._get_crontab()

            # Remove existing nightshift entries
            cleaned = self._remove_nightshift_entries(current)

            # Get all schedules to reinstall
            existing = self.list()

            # Add/update this schedule
            found = False
            for i, s in enumerate(existing):
                if s.id == schedule.id:
                    existing[i] = schedule
                    found = True
                    break
            if not found:
                existing.append(schedule)

            # Build new crontab
            new_crontab = self._build_crontab(cleaned, existing)

            # Install
            return self._set_crontab(new_crontab)

        except Exception as e:
            print(f"Error installing cron schedule: {e}")
            return False

    def uninstall(self, schedule_id: str) -> bool:
        """Remove a schedule from crontab."""
        try:
            current = self._get_crontab()
            cleaned = self._remove_nightshift_entries(current)

            existing = [s for s in self.list() if s.id != schedule_id]

            if existing:
                new_crontab = self._build_crontab(cleaned, existing)
            else:
                new_crontab = cleaned

            return self._set_crontab(new_crontab)

        except Exception as e:
            print(f"Error uninstalling cron schedule: {e}")
            return False

    def list(self) -> List[Schedule]:
        """List installed nightshift schedules."""
        schedules = []
        current = self._get_crontab()

        in_nightshift_block = False
        for line in current.split("\n"):
            if self.MARKER_START in line:
                in_nightshift_block = True
                continue
            if self.MARKER_END in line:
                in_nightshift_block = False
                continue

            if in_nightshift_block and self.MARKER_JOB in line:
                # Parse schedule from comment
                # Format: # nightshift:id:description
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    schedule_id = parts[1]
                    description = parts[2] if len(parts) > 2 else ""

                    # Next line should be the cron entry
                    continue

            if in_nightshift_block and line.strip() and not line.startswith("#"):
                # Parse cron line
                match = re.match(r'^(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s+(.+)$', line.strip())
                if match:
                    cron_expr = match.group(1)
                    command = match.group(2)

                    # Extract id from previous comment or generate
                    schedule_id = f"cron-{len(schedules)}"

                    schedules.append(Schedule(
                        id=schedule_id,
                        description="",
                        schedule=cron_expr,
                        command=command,
                        enabled=True,
                        status=ScheduleStatus.ACTIVE
                    ))

        return schedules

    def status(self) -> SchedulerStatus:
        """Get cron scheduler status."""
        available = self.is_available()
        schedules = self.list() if available else []

        return SchedulerStatus(
            backend="cron",
            available=available,
            schedules=schedules,
            error=None if available else "crontab not available"
        )

    def _get_crontab(self) -> str:
        """Get current crontab contents."""
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        return ""

    def _set_crontab(self, content: str) -> bool:
        """Set crontab contents."""
        process = subprocess.Popen(
            ["crontab", "-"],
            stdin=subprocess.PIPE,
            text=True
        )
        process.communicate(input=content)
        return process.returncode == 0

    def _remove_nightshift_entries(self, crontab: str) -> str:
        """Remove nightshift block from crontab."""
        lines = crontab.split("\n")
        result = []
        in_block = False

        for line in lines:
            if self.MARKER_START in line:
                in_block = True
                continue
            if self.MARKER_END in line:
                in_block = False
                continue
            if not in_block:
                result.append(line)

        return "\n".join(result)

    def _build_crontab(self, existing: str, schedules: List[Schedule]) -> str:
        """Build crontab with nightshift block."""
        # Ensure existing ends with newline
        if existing and not existing.endswith("\n"):
            existing += "\n"

        # Build nightshift block
        block = [self.MARKER_START]

        for schedule in schedules:
            if schedule.enabled:
                block.append(f"{self.MARKER_JOB}{schedule.id}:{schedule.description}")

                # Build command with proper path
                datacore_root = Path.home() / "Data"
                full_command = f"cd {datacore_root} && {schedule.command}"

                block.append(f"{schedule.schedule} {full_command}")

        block.append(self.MARKER_END)

        return existing + "\n".join(block) + "\n"
