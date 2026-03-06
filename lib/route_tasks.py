#!/usr/bin/env python3
"""
Route :AI: tagged tasks from source org files into nightshift.org queue.

Part of the /tomorrow command flow:
1. Finds all :AI: tagged tasks in TODO/NEXT state
2. Categorizes them into nightshift.org headings
3. Writes tasks to nightshift.org with QUEUED state
4. Updates state in source files to QUEUED (prevents re-queuing)

Usage:
    python route_tasks.py <data_dir> [--dry-run] [--skip-inbox] [--skip-habits]
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

import yaml

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from nightshift_parser import OrgTask, find_ai_tasks, write_org_file


def _load_routing_config() -> dict:
    """Load routing config from routing.local.yaml (gitignored).
    Falls back to routing.example.yaml if local config doesn't exist."""
    config_dir = Path(__file__).parent.parent / 'config'
    local_config = config_dir / 'routing.local.yaml'
    example_config = config_dir / 'routing.example.yaml'

    config_path = local_config if local_config.exists() else example_config
    if config_path.exists():
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"Warning: routing config parse error in {config_path}: {e}", file=sys.stderr)
            return {}
    return {}

_ROUTING_CONFIG = _load_routing_config()
RESEARCH_CATEGORIES = _ROUTING_CONFIG.get('research_categories', {})
NIGHTSHIFT_ORG_SPACE = _ROUTING_CONFIG.get('nightshift_org_space', '0-personal')


def categorize_task(task: OrgTask) -> Tuple[str, str]:
    """Determine nightshift.org heading for a task.

    Uses routing rules from config/routing.local.yaml.

    Returns:
        (top_heading, sub_heading) - the hierarchy under which to place the task
    """
    space = task.space or ''
    source = task.file_path.stem
    tags_lower = [t.lower() for t in task.tags if t != 'AI']
    title_lower = task.title.lower()

    # Evaluate config-driven heading rules
    for rule in _ROUTING_CONFIG.get('heading_rules', []):
        # Check space_prefix match
        if 'space_prefix' in rule:
            if not space.startswith(rule['space_prefix']):
                continue
            # Special case: research source in a space with research_sub
            if 'research' in source and 'research_sub' in rule:
                return 'RESEARCH & LEARNING', rule['research_sub']
            return rule['heading'], rule.get('sub_heading', '')

        # Check exact space match
        if 'space' in rule and space != rule['space']:
            continue

        # Check source file match
        if 'source' in rule:
            if rule['source'] not in source:
                continue
            heading = rule['heading']
            if heading == 'RESEARCH & LEARNING' and not rule.get('sub_heading'):
                return heading, detect_research_category(tags_lower, title_lower)
            return heading, rule.get('sub_heading', '')

        # Check tag match
        if 'tags' in rule:
            if not any(t in tags_lower for t in rule['tags']):
                continue
            heading = rule['heading']
            if heading == 'RESEARCH & LEARNING' and not rule.get('sub_heading'):
                return heading, detect_research_category(tags_lower, title_lower)
            return heading, rule.get('sub_heading', '')

        # No matchers = matches everything (shouldn't normally happen mid-list)
        if 'space_prefix' not in rule and 'space' not in rule and 'source' not in rule and 'tags' not in rule:
            return rule['heading'], rule.get('sub_heading', '')

    # Fallback: check for research-tagged tasks
    if 'research' in tags_lower or 'research' in source:
        subcat = detect_research_category(tags_lower, title_lower)
        return 'RESEARCH & LEARNING', subcat

    # Default
    return (
        _ROUTING_CONFIG.get('default_heading', 'GENERAL'),
        _ROUTING_CONFIG.get('default_sub', ''),
    )


def detect_research_category(tags: List[str], title: str) -> str:
    """Detect research subcategory from tags and title."""
    for keyword, category in RESEARCH_CATEGORIES.items():
        if keyword in tags or keyword in title:
            return category
    return 'Technology & Innovation'  # Default research category


def format_task_for_queue(task: OrgTask) -> str:
    """Format an OrgTask as a nightshift.org QUEUED entry."""
    # Build tag string
    tags_str = ':' + ':'.join(task.tags) + ':' if task.tags else ''

    # Build the heading line
    line = f'*** QUEUED {task.title} {tags_str}'

    # Build properties drawer
    props = [':PROPERTIES:']
    # Preserve original properties
    for key, value in task.properties.items():
        props.append(f':{key}: {value}')
    # Add source tracking
    props.append(f':SOURCE_FILE: {task.file_path}')
    props.append(f':SOURCE_LINE: {task.line_number}')
    if task.space:
        props.append(f':SPACE: {task.space}')
    props.append(':END:')

    parts = [line] + props

    # Include body if present (truncated for queue)
    if task.body:
        body = task.body.strip()
        if len(body) > 500:
            body = body[:500] + '\n...(truncated)'
        parts.append(body)

    return '\n'.join(parts)


def build_nightshift_content(tasks: List[OrgTask], existing_content: str) -> str:
    """Build updated nightshift.org content with queued tasks."""
    # Categorize all tasks
    categorized: Dict[Tuple[str, str], List[OrgTask]] = defaultdict(list)
    for task in tasks:
        category = categorize_task(task)
        categorized[category].append(task)

    # Parse existing nightshift.org to find insertion points
    lines = existing_content.split('\n')

    # Build new content by inserting tasks under appropriate headings
    result_lines = []
    current_top = None
    current_sub = None

    # Track which categories we've inserted
    inserted = set()

    for line in lines:
        result_lines.append(line)

        # Track current heading context
        top_match = re.match(r'^\* (.+)', line)
        sub_match = re.match(r'^\*\* (.+)', line)

        if top_match:
            current_top = top_match.group(1).strip()
            current_sub = None
        elif sub_match:
            current_sub = sub_match.group(1).strip()

            # Check if we have tasks for this (top, sub) pair
            key = (current_top, current_sub)
            if key in categorized and key not in inserted:
                for task in categorized[key]:
                    result_lines.append(format_task_for_queue(task))
                    result_lines.append('')
                inserted.add(key)

    # Add any categories that didn't match existing headings
    for key, tasks_list in categorized.items():
        if key not in inserted:
            top, sub = key
            result_lines.append('')
            # Check if top heading exists
            top_exists = any(
                re.match(rf'^\* {re.escape(top)}', l) for l in lines
            )
            if not top_exists:
                result_lines.append(f'* {top}')
            result_lines.append(f'** {sub}')
            for task in tasks_list:
                result_lines.append(format_task_for_queue(task))
                result_lines.append('')
            inserted.add(key)

    return '\n'.join(result_lines)


def update_source_states(tasks: List[OrgTask]) -> Dict[Path, int]:
    """Update task states in source files from TODO/NEXT to QUEUED.

    Returns:
        Dict mapping file path to number of tasks updated
    """
    # Group tasks by file for efficient batch updates
    by_file: Dict[Path, List[OrgTask]] = defaultdict(list)
    for task in tasks:
        by_file[task.file_path].append(task)

    updated_counts = {}
    for file_path, file_tasks in by_file.items():
        content = file_path.read_text(encoding='utf-8')

        for task in file_tasks:
            # Use the update function for each task
            content = update_task_state_in_content(content, task, 'QUEUED')

        write_org_file(file_path, content)
        updated_counts[file_path] = len(file_tasks)

    return updated_counts


def update_task_state_in_content(content: str, task: OrgTask, new_state: str) -> str:
    """Update task state within content string (doesn't read from disk)."""
    lines = content.split('\n')
    heading_line_idx = task.line_number - 1

    if heading_line_idx < len(lines):
        line = lines[heading_line_idx]
        new_line = re.sub(
            r'^(\*+\s+)(TODO|NEXT|WORKING|DONE|REVIEW|FAILED|WAITING|QUEUED|EXECUTING)(\s+)',
            rf'\g<1>{new_state}\3',
            line
        )
        lines[heading_line_idx] = new_line

    return '\n'.join(lines)


def route_tasks(
    data_dir: Path,
    dry_run: bool = False,
    skip_inbox: bool = True,
    skip_habits: bool = True
) -> Tuple[int, Dict[str, int]]:
    """Route :AI: tasks to nightshift.org queue.

    Args:
        data_dir: Root data directory
        dry_run: If True, only print what would be done
        skip_inbox: Skip tasks from inbox.org files
        skip_habits: Skip tasks from habits.org files

    Returns:
        (total_queued, counts_by_space)
    """
    # Find all AI tasks
    all_tasks = find_ai_tasks(data_dir, states=['TODO', 'NEXT'])

    # Filter
    tasks = []
    skipped_inbox = 0
    skipped_habits = 0

    for task in all_tasks:
        source = task.file_path.stem
        if skip_inbox and source == 'inbox':
            skipped_inbox += 1
            continue
        if skip_habits and source == 'habits':
            skipped_habits += 1
            continue
        tasks.append(task)

    if skipped_inbox:
        print(f'  Skipped {skipped_inbox} inbox tasks (need GTD triage first)')
    if skipped_habits:
        print(f'  Skipped {skipped_habits} habits tasks (recurring, not for nightshift)')

    if not tasks:
        print('No tasks to queue.')
        return 0, {}

    # Read existing nightshift.org
    nightshift_path = data_dir / NIGHTSHIFT_ORG_SPACE / 'org' / 'nightshift.org'
    if nightshift_path.exists():
        existing = nightshift_path.read_text(encoding='utf-8')
    else:
        existing = '#+TITLE: Nightshift Queue\n#+TODO: QUEUED EXECUTING | DONE FAILED\n'

    # Build new content
    new_content = build_nightshift_content(tasks, existing)

    # Count by space
    counts = defaultdict(int)
    for task in tasks:
        counts[task.space or 'unknown'] += 1

    if dry_run:
        print(f'\n[DRY RUN] Would queue {len(tasks)} tasks:')
        for space, count in sorted(counts.items()):
            print(f'  {space}: {count}')
        print(f'\nNightshift.org would grow to {len(new_content)} chars')
        return len(tasks), dict(counts)

    # Write nightshift.org
    write_org_file(nightshift_path, new_content)
    print(f'  Wrote {len(tasks)} tasks to nightshift.org')

    # Update source file states
    updated = update_source_states(tasks)
    for path, count in updated.items():
        print(f'  Updated {count} tasks in {path.name} to QUEUED state')

    return len(tasks), dict(counts)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python route_tasks.py <data_dir> [--dry-run] [--skip-inbox] [--skip-habits]')
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv
    skip_inbox = '--skip-inbox' in sys.argv or '--no-inbox' not in sys.argv
    skip_habits = '--skip-habits' in sys.argv or '--no-habits' not in sys.argv

    total, counts = route_tasks(data_dir, dry_run=dry_run, skip_inbox=skip_inbox, skip_habits=skip_habits)
    print(f'\nTotal: {total} tasks queued')
