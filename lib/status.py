#!/usr/bin/env python3
"""
Status display for nightshift.
Shows current state of :AI: tasks and recent executions.
"""

import sys
from pathlib import Path
from datetime import datetime

from org_parser import find_ai_tasks


def show_status(data_dir: Path) -> None:
    """Display nightshift status."""
    print("=" * 50)
    print("Nightshift Status")
    print("=" * 50)
    print(f"Data directory: {data_dir}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Find all :AI: tasks in various states
    queued = find_ai_tasks(data_dir, states=['TODO', 'NEXT'])
    working = find_ai_tasks(data_dir, states=['WORKING'])
    review = find_ai_tasks(data_dir, states=['REVIEW'])
    done_recent = find_ai_tasks(data_dir, states=['DONE'])

    # Filter done to only those with NIGHTSHIFT_COMPLETED in last 24h
    # (simplified - just show all for now)

    print(f"## Queue")
    print(f"Tasks waiting: {len(queued)}")
    if queued:
        for task in queued[:5]:
            status = task.properties.get('NIGHTSHIFT_STATUS', '')
            marker = f" [{status}]" if status else ""
            print(f"  - [{task.state}] {task.title}{marker}")
        if len(queued) > 5:
            print(f"  ... and {len(queued) - 5} more")
    print()

    print(f"## In Progress")
    print(f"Tasks executing: {len(working)}")
    for task in working:
        executor = task.properties.get('NIGHTSHIFT_EXECUTOR', 'unknown')
        started = task.properties.get('NIGHTSHIFT_STARTED', 'unknown')
        print(f"  - {task.title}")
        print(f"    Executor: {executor}")
        print(f"    Started: {started}")
    print()

    print(f"## Needs Review")
    print(f"Tasks for review: {len(review)}")
    for task in review[:5]:
        score = task.properties.get('NIGHTSHIFT_SCORE', '?')
        output = task.properties.get('NIGHTSHIFT_OUTPUT', '')
        print(f"  - {task.title} (score: {score})")
        if output:
            print(f"    Output: {Path(output).name}")
    print()

    # Check for recent outputs in 0-inbox
    inbox_files = []
    for inbox_dir in data_dir.glob('*/0-inbox'):
        for f in inbox_dir.glob('nightshift-*.md'):
            inbox_files.append(f)

    inbox_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    print(f"## Recent Outputs")
    print(f"Files in 0-inbox: {len(inbox_files)}")
    for f in inbox_files[:5]:
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        print(f"  - {f.name} ({mtime})")
    print()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python status.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    show_status(data_dir)
