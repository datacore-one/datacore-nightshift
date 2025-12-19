"""
Systemd scheduler adapter for nightshift.

Uses systemd timers for scheduling on Linux servers.
"""

import subprocess
import shutil
from typing import List, Optional
from pathlib import Path

from .base import SchedulerAdapter, Schedule, SchedulerStatus, ScheduleStatus


class SystemdAdapter(SchedulerAdapter):
    """
    Linux systemd timer adapter.

    Manages nightshift schedules via systemd timer units.
    Requires sudo for installation (copying to /etc/systemd/system/).
    """

    # Map schedule IDs to systemd unit names
    UNIT_MAP = {
        "nightly-execution": "nightshift-overnight",
        "early-morning-batch": "nightshift-overnight",  # Same timer, two times
        "today-briefing": "nightshift-today",
    }

    def __init__(self, server_dir: Optional[Path] = None):
        """
        Initialize the systemd adapter.

        Args:
            server_dir: Path to nightshift server/ directory containing unit files.
                       Defaults to module's server/ directory.
        """
        if server_dir is None:
            # Default to the server/ directory relative to this file
            self.server_dir = Path(__file__).parent.parent.parent / "server"
        else:
            self.server_dir = Path(server_dir)

    @property
    def name(self) -> str:
        return "systemd"

    def is_available(self) -> bool:
        """Check if systemd is available."""
        return shutil.which("systemctl") is not None

    def install(self, schedule: Schedule) -> bool:
        """
        Install nightshift systemd timers.

        This installs all nightshift timers at once since they work together.
        """
        if not self.is_available():
            print("Error: systemctl not found")
            return False

        try:
            # Find all service and timer files
            service_files = list(self.server_dir.glob("nightshift-*.service"))
            timer_files = list(self.server_dir.glob("nightshift-*.timer"))

            if not service_files or not timer_files:
                print(f"Error: No unit files found in {self.server_dir}")
                return False

            # Copy files to systemd directory (requires sudo)
            systemd_dir = Path("/etc/systemd/system")

            for unit_file in service_files + timer_files:
                dest = systemd_dir / unit_file.name
                result = subprocess.run(
                    ["sudo", "cp", str(unit_file), str(dest)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    print(f"Error copying {unit_file.name}: {result.stderr}")
                    return False

            # Reload systemd daemon
            result = subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                print(f"Error reloading daemon: {result.stderr}")
                return False

            # Enable and start timers
            for timer_file in timer_files:
                timer_name = timer_file.stem  # e.g., "nightshift-overnight"

                # Enable timer
                result = subprocess.run(
                    ["sudo", "systemctl", "enable", f"{timer_name}.timer"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    print(f"Error enabling {timer_name}.timer: {result.stderr}")
                    return False

                # Start timer
                result = subprocess.run(
                    ["sudo", "systemctl", "start", f"{timer_name}.timer"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    print(f"Error starting {timer_name}.timer: {result.stderr}")
                    return False

            print("Systemd timers installed and started successfully")
            return True

        except subprocess.TimeoutExpired:
            print("Error: Command timed out")
            return False
        except Exception as e:
            print(f"Error installing systemd timers: {e}")
            return False

    def install_all(self, schedules: List[Schedule] = None) -> dict:
        """Install all nightshift timers."""
        # For systemd, we install all timers at once
        success = self.install(None)
        return {"nightshift-overnight": success, "nightshift-today": success}

    def uninstall(self, schedule_id: str = None) -> bool:
        """
        Remove nightshift systemd timers.

        Removes all nightshift timers since they work as a unit.
        """
        if not self.is_available():
            print("Error: systemctl not found")
            return False

        try:
            # Find installed timers
            timer_names = ["nightshift-overnight", "nightshift-today"]

            for timer_name in timer_names:
                # Stop timer
                subprocess.run(
                    ["sudo", "systemctl", "stop", f"{timer_name}.timer"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                # Disable timer
                subprocess.run(
                    ["sudo", "systemctl", "disable", f"{timer_name}.timer"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                # Remove files
                for suffix in [".service", ".timer"]:
                    unit_path = Path(f"/etc/systemd/system/{timer_name}{suffix}")
                    if unit_path.exists():
                        subprocess.run(
                            ["sudo", "rm", str(unit_path)],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )

            # Reload daemon
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=30
            )

            print("Systemd timers uninstalled successfully")
            return True

        except Exception as e:
            print(f"Error uninstalling systemd timers: {e}")
            return False

    def list(self) -> List[Schedule]:
        """List installed nightshift timers."""
        schedules = []

        if not self.is_available():
            return schedules

        timer_names = ["nightshift-overnight", "nightshift-today"]

        for timer_name in timer_names:
            # Check if timer is enabled
            result = subprocess.run(
                ["systemctl", "is-enabled", f"{timer_name}.timer"],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Get timer info
                info_result = subprocess.run(
                    ["systemctl", "show", f"{timer_name}.timer",
                     "--property=Description,NextElapseUSecRealtime"],
                    capture_output=True,
                    text=True
                )

                description = ""
                next_run = None

                for line in info_result.stdout.strip().split("\n"):
                    if line.startswith("Description="):
                        description = line.split("=", 1)[1]
                    elif line.startswith("NextElapseUSecRealtime="):
                        next_run = line.split("=", 1)[1]

                # Determine schedule expression based on timer
                if timer_name == "nightshift-overnight":
                    schedule_expr = "0 0,6 * * *"  # Midnight and 6am
                    command = "nightshift run"
                else:
                    schedule_expr = "0 7 * * *"  # 7am
                    command = "nightshift run --command=/today"

                schedules.append(Schedule(
                    id=timer_name,
                    description=description,
                    schedule=schedule_expr,
                    command=command,
                    enabled=True,
                    next_run=next_run,
                    status=ScheduleStatus.ACTIVE
                ))

        return schedules

    def status(self) -> SchedulerStatus:
        """Get systemd scheduler status."""
        available = self.is_available()
        schedules = self.list() if available else []

        # Check for any errors in recent runs
        error = None
        if available and not schedules:
            error = "No nightshift timers installed"

        return SchedulerStatus(
            backend="systemd",
            available=available,
            schedules=schedules,
            error=error
        )

    def get_recent_logs(self, lines: int = 50) -> str:
        """Get recent logs from nightshift services."""
        if not self.is_available():
            return "systemctl not available"

        try:
            result = subprocess.run(
                ["journalctl", "-u", "nightshift-*", "-n", str(lines), "--no-pager"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout
        except Exception as e:
            return f"Error fetching logs: {e}"
