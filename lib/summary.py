"""
Summary report generation for nightshift.
Creates consolidated reports of nightshift execution results.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def generate_summary(
    completed_tasks: List[Dict[str, Any]],
    failed_tasks: List[Dict[str, Any]],
    review_tasks: List[Dict[str, Any]],
    total_duration: float,
    total_tokens: int
) -> str:
    """
    Generate a summary report of nightshift execution.

    Args:
        completed_tasks: List of successfully completed tasks
        failed_tasks: List of failed tasks
        review_tasks: List of tasks needing review
        total_duration: Total execution time in seconds
        total_tokens: Estimated total tokens used

    Returns:
        Markdown content for the summary report
    """
    today = datetime.utcnow().strftime('%Y-%m-%d')
    total_tasks = len(completed_tasks) + len(failed_tasks) + len(review_tasks)

    # Calculate percentages
    approved_pct = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
    review_pct = (len(review_tasks) / total_tasks * 100) if total_tasks > 0 else 0
    failed_pct = (len(failed_tasks) / total_tasks * 100) if total_tasks > 0 else 0

    # Format duration
    hours = int(total_duration // 3600)
    minutes = int((total_duration % 3600) // 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m"
    else:
        duration_str = f"{minutes}m"

    # Estimate cost (rough: $0.015 per 1K tokens for Claude)
    est_cost = (total_tokens / 1000) * 0.015

    content_parts = []

    # Frontmatter
    content_parts.append('---')
    content_parts.append('type: nightshift-summary')
    content_parts.append(f'date: {today}')
    content_parts.append(f'total_tasks: {total_tasks}')
    content_parts.append(f'approved: {len(completed_tasks)}')
    content_parts.append(f'review: {len(review_tasks)}')
    content_parts.append(f'failed: {len(failed_tasks)}')
    content_parts.append('---')
    content_parts.append('')

    # Header
    content_parts.append(f'# Nightshift Summary - {today}')
    content_parts.append('')

    # Quick stats table
    content_parts.append('## Quick Stats')
    content_parts.append('')
    content_parts.append('| Metric | Value |')
    content_parts.append('|--------|-------|')
    content_parts.append(f'| Tasks Executed | {total_tasks} |')
    content_parts.append(f'| Approved | {len(completed_tasks)} ({approved_pct:.0f}%) |')
    content_parts.append(f'| Needs Review | {len(review_tasks)} ({review_pct:.0f}%) |')
    content_parts.append(f'| Failed | {len(failed_tasks)} ({failed_pct:.0f}%) |')
    content_parts.append(f'| Duration | {duration_str} |')
    content_parts.append(f'| Est. Cost | ~${est_cost:.2f} |')
    content_parts.append('')

    # Group tasks by space
    all_tasks = []
    for task in completed_tasks:
        task['category'] = 'approved'
        all_tasks.append(task)
    for task in review_tasks:
        task['category'] = 'review'
        all_tasks.append(task)
    for task in failed_tasks:
        task['category'] = 'failed'
        all_tasks.append(task)

    spaces = {}
    for task in all_tasks:
        space = task.get('space') or '0-personal'
        if space not in spaces:
            spaces[space] = []
        spaces[space].append(task)

    # Results by space
    content_parts.append('## Results by Space')
    content_parts.append('')

    for space, tasks in sorted(spaces.items()):
        approved = [t for t in tasks if t['category'] == 'approved']
        review = [t for t in tasks if t['category'] == 'review']
        failed = [t for t in tasks if t['category'] == 'failed']

        content_parts.append(f'### {space}')
        content_parts.append('')

        if approved or review:
            content_parts.append('| Task | Score | Status | Output |')
            content_parts.append('|------|-------|--------|--------|')

            for task in approved:
                output_link = f"[[{Path(task.get('output_path', '')).name}]]"
                content_parts.append(f"| {task['title'][:50]} | {task.get('score', 0):.2f} | approved | {output_link} |")

            for task in review:
                output_link = f"[[{Path(task.get('output_path', '')).name}]]"
                content_parts.append(f"| {task['title'][:50]} | {task.get('score', 0):.2f} | **review** | {output_link} |")

            content_parts.append('')

        if failed:
            content_parts.append('**Failed:**')
            for task in failed:
                error = task.get('error', 'Unknown error')[:60]
                content_parts.append(f"- {task['title'][:50]} - `{error}`")
            content_parts.append('')

    # Needs review section (highlighted)
    if review_tasks:
        content_parts.append('## Needs Review')
        content_parts.append('')
        content_parts.append('| Task | Score | Reason | Output |')
        content_parts.append('|------|-------|--------|--------|')
        for task in review_tasks:
            reason = "Low consensus" if task.get('score', 0) < 0.7 else "Evaluator disagreement"
            output_link = f"[[{Path(task.get('output_path', '')).name}]]"
            content_parts.append(f"| {task['title'][:50]} | {task.get('score', 0):.2f} | {reason} | {output_link} |")
        content_parts.append('')

    # Action items
    content_parts.append('## Action Required')
    content_parts.append('')
    if review_tasks:
        content_parts.append(f'- [ ] Review {len(review_tasks)} flagged items')
    if completed_tasks:
        content_parts.append(f'- [ ] Process {len(completed_tasks)} approved outputs')
    if failed_tasks:
        content_parts.append(f'- [ ] Investigate {len(failed_tasks)} failures')
    content_parts.append('')

    return '\n'.join(content_parts)


def generate_journal_summary(
    completed_tasks: List[Dict[str, Any]],
    failed_tasks: List[Dict[str, Any]],
    review_tasks: List[Dict[str, Any]],
    total_duration: float,
    total_tokens: int
) -> str:
    """
    Generate a condensed summary for journal entry.

    Returns a shorter version suitable for appending to daily journal.
    """
    total_tasks = len(completed_tasks) + len(failed_tasks) + len(review_tasks)
    today = datetime.utcnow().strftime('%Y-%m-%d')

    # Format duration
    hours = int(total_duration // 3600)
    minutes = int((total_duration % 3600) // 60)
    if hours > 0:
        duration_str = f"{hours}h {minutes}m"
    else:
        duration_str = f"{minutes}m"

    content_parts = []
    content_parts.append('### Nightshift Results')
    content_parts.append('')
    content_parts.append(f'**Run**: {datetime.utcnow().strftime("%H:%M")} UTC | **Duration**: {duration_str}')
    content_parts.append(f'**Tasks**: {total_tasks} ({len(completed_tasks)} approved, {len(review_tasks)} review, {len(failed_tasks)} failed)')
    content_parts.append('')

    if review_tasks:
        content_parts.append('**Needs Review:**')
        for task in review_tasks[:5]:  # Show max 5
            output_name = Path(task.get('output_path', '')).name
            content_parts.append(f"- [ ] {task['title'][:40]} ({task.get('score', 0):.2f}) → [[{output_name}]]")
        if len(review_tasks) > 5:
            content_parts.append(f"- ... and {len(review_tasks) - 5} more")
        content_parts.append('')

    if completed_tasks:
        content_parts.append('**Ready to Process:**')
        # Show top 3 by score
        sorted_tasks = sorted(completed_tasks, key=lambda x: x.get('score', 0), reverse=True)
        for task in sorted_tasks[:3]:
            content_parts.append(f"- {task['title'][:40]} ({task.get('score', 0):.2f})")
        if len(completed_tasks) > 3:
            content_parts.append(f"- ... and {len(completed_tasks) - 3} more")
        content_parts.append('')

    content_parts.append(f'Full report: [[nightshift-summary-{today}.md]]')
    content_parts.append('')

    return '\n'.join(content_parts)


def write_summary_file(
    data_dir: Path,
    space: str,
    completed_tasks: List[Dict[str, Any]],
    failed_tasks: List[Dict[str, Any]],
    review_tasks: List[Dict[str, Any]],
    total_duration: float,
    total_tokens: int
) -> Path:
    """
    Write summary file to space's 0-inbox directory.

    Returns path to created file.
    """
    today = datetime.utcnow().strftime('%Y-%m-%d')
    filename = f"nightshift-summary-{today}.md"

    # Determine output directory
    if space:
        output_dir = data_dir / space / '0-inbox'
    else:
        output_dir = data_dir / '0-personal' / '0-inbox'

    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename

    # Generate summary content
    content = generate_summary(
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        review_tasks=review_tasks,
        total_duration=total_duration,
        total_tokens=total_tokens
    )

    output_path.write_text(content, encoding='utf-8')
    print(f"Summary written to: {output_path}")

    return output_path


if __name__ == '__main__':
    # Test summary generation
    completed = [
        {'title': 'Research competitor X', 'space': '1-datafund', 'score': 0.93, 'output_path': '/path/nightshift-001.md'},
        {'title': 'Draft product roadmap', 'space': '1-datafund', 'score': 0.94, 'output_path': '/path/nightshift-002.md'},
    ]
    review = [
        {'title': 'Create 6-month roadmap', 'space': '1-datafund', 'score': 0.55, 'output_path': '/path/nightshift-003.md'},
    ]
    failed = [
        {'title': 'Send email to partner', 'space': '0-personal', 'error': 'No email credentials'},
    ]

    print("=== Full Summary ===")
    print(generate_summary(completed, failed, review, 3600, 50000))
    print()
    print("=== Journal Summary ===")
    print(generate_journal_summary(completed, failed, review, 3600, 50000))
