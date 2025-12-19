#!/usr/bin/env python3
"""
Nightshift Scheduler CLI

Manages scheduled execution of nightshift tasks.

Usage:
    nightshift scheduler status              Show installed schedules
    nightshift scheduler install             Install schedules (auto-detect platform)
    nightshift scheduler install --backend=X Force specific backend (cron, systemd)
    nightshift scheduler uninstall           Remove all schedules
    nightshift scheduler logs                Show recent execution logs (systemd only)
"""

import sys
import argparse
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from scheduler import (
    load_schedules,
    detect_platform,
    SchedulerAdapter,
)
from scheduler.cron_adapter import CronAdapter
from scheduler.systemd_adapter import SystemdAdapter


def get_adapter(backend: str = None) -> SchedulerAdapter:
    """Get the appropriate scheduler adapter."""
    if backend:
        backend = backend.lower()
        if backend == "cron":
            return CronAdapter()
        elif backend == "systemd":
            return SystemdAdapter()
        else:
            print(f"Unknown backend: {backend}")
            print("Available backends: cron, systemd")
            sys.exit(1)

    # Auto-detect platform
    platform = detect_platform()

    if platform == "linux":
        # Prefer systemd on Linux
        adapter = SystemdAdapter()
        if adapter.is_available():
            return adapter
        # Fall back to cron
        return CronAdapter()
    else:
        # macOS and others use cron
        return CronAdapter()


def cmd_status(args):
    """Show scheduler status."""
    adapter = get_adapter(args.backend)
    status = adapter.status()

    print("=" * 50)
    print("Nightshift Scheduler Status")
    print("=" * 50)
    print(f"Backend: {status.backend}")
    print(f"Available: {'Yes' if status.available else 'No'}")

    if status.error:
        print(f"Error: {status.error}")

    print()

    if status.schedules:
        print("Installed Schedules:")
        print("-" * 50)
        for schedule in status.schedules:
            status_icon = "✓" if schedule.status.value == "active" else "○"
            print(f"  {status_icon} {schedule.id}")
            print(f"    Schedule: {schedule.schedule}")
            print(f"    Command: {schedule.command}")
            if schedule.next_run:
                print(f"    Next run: {schedule.next_run}")
            print()
    else:
        print("No schedules installed.")
        print()
        print("To install schedules, run:")
        print("  nightshift scheduler install")


def cmd_install(args):
    """Install schedules."""
    adapter = get_adapter(args.backend)

    if not adapter.is_available():
        print(f"Error: {adapter.name} is not available on this system")
        sys.exit(1)

    print(f"Installing nightshift schedules using {adapter.name}...")
    print()

    # Load schedules from config
    schedules = load_schedules()

    enabled_schedules = [s for s in schedules if s.enabled]

    if not enabled_schedules:
        print("No enabled schedules found in schedules.yaml")
        sys.exit(1)

    print(f"Found {len(enabled_schedules)} enabled schedule(s):")
    for schedule in enabled_schedules:
        print(f"  - {schedule.id}: {schedule.schedule} → {schedule.command}")
    print()

    # Install
    if hasattr(adapter, 'install_all'):
        results = adapter.install_all(enabled_schedules)
    else:
        results = {}
        for schedule in enabled_schedules:
            results[schedule.id] = adapter.install(schedule)

    # Report results
    success_count = sum(1 for v in results.values() if v)
    fail_count = len(results) - success_count

    print()
    if fail_count == 0:
        print(f"Successfully installed {success_count} schedule(s)")

        # Show verification command
        if adapter.name == "systemd":
            print()
            print("Verify with:")
            print("  systemctl list-timers | grep nightshift")
        elif adapter.name == "cron":
            print()
            print("Verify with:")
            print("  crontab -l | grep nightshift")
    else:
        print(f"Installed {success_count}, failed {fail_count}")
        sys.exit(1)


def cmd_uninstall(args):
    """Uninstall schedules."""
    adapter = get_adapter(args.backend)

    if not adapter.is_available():
        print(f"Error: {adapter.name} is not available on this system")
        sys.exit(1)

    print(f"Uninstalling nightshift schedules from {adapter.name}...")

    if adapter.uninstall():
        print("Successfully uninstalled all schedules")
    else:
        print("Error uninstalling schedules")
        sys.exit(1)


def cmd_logs(args):
    """Show recent logs (systemd only)."""
    adapter = get_adapter(args.backend)

    if adapter.name != "systemd":
        print("Logs command is only available for systemd backend")
        print()
        print("For cron, check your system's mail or log files")
        sys.exit(1)

    if hasattr(adapter, 'get_recent_logs'):
        logs = adapter.get_recent_logs(args.lines)
        print(logs)
    else:
        print("Logs not available for this adapter")


def main():
    parser = argparse.ArgumentParser(
        description="Nightshift Scheduler CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nightshift scheduler status                    Show current status
  nightshift scheduler install                   Install using auto-detected backend
  nightshift scheduler install --backend=systemd Force systemd backend
  nightshift scheduler uninstall                 Remove all schedules
  nightshift scheduler logs                      Show recent execution logs
        """
    )

    parser.add_argument(
        "--backend",
        choices=["cron", "systemd"],
        help="Force specific scheduler backend"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show scheduler status")
    status_parser.set_defaults(func=cmd_status)

    # Install command
    install_parser = subparsers.add_parser("install", help="Install schedules")
    install_parser.set_defaults(func=cmd_install)

    # Uninstall command
    uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall schedules")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show recent logs")
    logs_parser.add_argument(
        "-n", "--lines",
        type=int,
        default=50,
        help="Number of log lines to show (default: 50)"
    )
    logs_parser.set_defaults(func=cmd_logs)

    # Parse args
    # Handle case where data_dir is passed as first arg
    args_to_parse = sys.argv[1:]
    if args_to_parse and not args_to_parse[0].startswith("-") and args_to_parse[0] not in ["status", "install", "uninstall", "logs"]:
        # First arg is data_dir, skip it
        args_to_parse = args_to_parse[1:]

    args = parser.parse_args(args_to_parse)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
