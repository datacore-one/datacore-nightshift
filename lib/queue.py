#!/usr/bin/env python3
"""
Queue management for nightshift.
Discovers :AI: tasks and builds execution queue.
"""

import sys
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from nightshift_parser import OrgTask, find_ai_tasks


@dataclass
class QueuedTask:
    """A task ready for execution with priority score."""
    task: OrgTask
    priority_score: float
    estimated_tokens: int = 5000  # Default estimate


def calculate_priority(task: OrgTask) -> float:
    """
    Calculate priority score for a task.
    Higher score = higher priority.

    Formula: Impact * 0.35 + Urgency * 0.25 + Readiness * 0.20 + Effort * 0.10 + Intent * 0.10
    Weights sum to 1.0. Intent score from strategic alignment (default 5).
    """
    # Default values (1-10 scale)
    impact = 5
    urgency = 5
    readiness = 5
    effort = 5  # Lower effort = higher priority for this component
    intent = 5  # Strategic intent alignment (default neutral)

    # Get from properties if available
    if 'IMPACT' in task.properties:
        try:
            impact = int(task.properties['IMPACT'])
        except ValueError:
            pass

    if 'URGENCY' in task.properties:
        try:
            urgency = int(task.properties['URGENCY'])
        except ValueError:
            pass

    if 'EFFORT' in task.properties:
        try:
            # Invert effort (lower effort = better)
            effort = 10 - int(task.properties['EFFORT'])
        except ValueError:
            pass

    if 'INTENT_SCORE' in task.properties:
        try:
            intent = float(task.properties['INTENT_SCORE'])
        except ValueError:
            pass

    # Readiness based on state
    if task.state == 'NEXT':
        readiness = 10
    elif task.state == 'TODO':
        readiness = 5

    # AI tag type affects priority
    tag_boost = {
        ':AI:pm:': 1.2,
        ':AI:research:': 1.1,
        ':AI:content:': 1.0,
        ':AI:data:': 1.0,
        ':AI:code:': 0.9,
        ':AI:': 0.8,
    }
    ai_tag = task.ai_tag or ':AI:'
    multiplier = tag_boost.get(ai_tag, 1.0)

    # Calculate weighted score (weights sum to 1.0)
    score = (
        impact * 0.35 +
        urgency * 0.25 +
        readiness * 0.20 +
        effort * 0.10 +
        intent * 0.10
    ) * multiplier

    return round(score, 2)


def load_config(data_dir: Path) -> dict:
    """Load nightshift config from config.local.yaml if present."""
    import yaml
    config_path = data_dir / '.datacore' / 'modules' / 'nightshift' / 'config.local.yaml'
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def build_queue(data_dir: Path, limit: Optional[int] = None, include_pending: bool = False) -> List[QueuedTask]:
    """Build execution queue from nightshift.org QUEUED tasks, sorted by priority.

    Args:
        data_dir: Root data directory
        limit: Maximum number of tasks to return
        include_pending: If True, also include TODO/NEXT :AI: tasks not yet moved to nightshift.org
    """
    # Load config for space filtering
    config = load_config(data_dir)
    nightshift_config = config.get('nightshift', {})
    spaces = nightshift_config.get('spaces')
    exclude_spaces = nightshift_config.get('exclude_spaces')

    # Primary: Find QUEUED tasks in nightshift.org only (not source files)
    all_queued = find_ai_tasks(data_dir, states=['QUEUED'], spaces=spaces, exclude_spaces=exclude_spaces)
    tasks = [t for t in all_queued if 'nightshift.org' in t.file_path.name]

    # Optionally include :AI: tasks from other files that haven't been queued yet
    if include_pending:
        pending_tasks = find_ai_tasks(data_dir, states=['TODO', 'NEXT'], spaces=spaces, exclude_spaces=exclude_spaces)
        # Filter to only tasks NOT in nightshift.org (those are the pending ones)
        for task in pending_tasks:
            if 'nightshift.org' not in str(task.file_path):
                tasks.append(task)

    # Filter out tasks that are already being executed
    eligible = []
    for task in tasks:
        status = task.properties.get('NIGHTSHIFT_STATUS', '')
        if status not in ['executing', 'claimed']:
            eligible.append(task)

    # Calculate priorities and create queue
    queue = []
    for task in eligible:
        priority = calculate_priority(task)
        queue.append(QueuedTask(task=task, priority_score=priority))

    # Sort by priority (highest first)
    queue.sort(key=lambda q: q.priority_score, reverse=True)

    # Apply limit
    if limit:
        queue = queue[:limit]

    return queue


def print_queue(queue: List[QueuedTask]) -> None:
    """Print the queue in a readable format."""
    if not queue:
        print("No :AI: tasks in queue")
        return

    print(f"\nNightshift Queue ({len(queue)} tasks)")
    print("=" * 60)

    for i, item in enumerate(queue, 1):
        task = item.task
        print(f"\n{i}. [{task.state}] {task.title}")
        print(f"   Tag: {task.ai_tag}")
        print(f"   Priority: {item.priority_score}")
        print(f"   Space: {task.space or 'unknown'}")
        print(f"   File: {task.file_path.name}:{task.line_number}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python queue.py <data_dir> [--limit=N]")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    limit = None

    for arg in sys.argv[2:]:
        if arg.startswith('--limit='):
            limit = int(arg.split('=')[1])

    queue = build_queue(data_dir, limit=limit)
    print_queue(queue)
