"""
Journal integration for nightshift.
Appends execution summaries to space and personal journals.
"""

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from org_parser import OrgTask
from evaluate import EvaluationResult


def get_journal_path(data_dir: Path, space: str = '0-personal') -> Path:
    """Get the journal file path for today."""
    today = datetime.now().strftime('%Y-%m-%d')
    journal_dir = data_dir / space / 'notes' / 'journals'
    journal_dir.mkdir(parents=True, exist_ok=True)
    return journal_dir / f'{today}.md'


def append_to_journal(
    journal_path: Path,
    section: str,
    content: str
) -> None:
    """Append content to a journal section."""
    if not journal_path.exists():
        # Create new journal with basic structure
        journal_content = f"""---
date: {datetime.now().strftime('%Y-%m-%d')}
---

# {datetime.now().strftime('%A, %B %d, %Y')}

"""
        journal_path.write_text(journal_content, encoding='utf-8')

    existing = journal_path.read_text(encoding='utf-8')

    # Check if section already exists
    section_header = f"## {section}"
    if section_header in existing:
        # Append to existing section
        # Find the section and append before the next section or end
        lines = existing.split('\n')
        new_lines = []
        in_section = False
        content_added = False

        for i, line in enumerate(lines):
            new_lines.append(line)

            if line.strip() == section_header:
                in_section = True
            elif in_section and line.startswith('## ') and not content_added:
                # Hit next section, insert content before it
                new_lines.insert(-1, '')
                new_lines.insert(-1, content)
                content_added = True
                in_section = False

        # If we were in section and never hit another section
        if in_section and not content_added:
            new_lines.append('')
            new_lines.append(content)

        journal_path.write_text('\n'.join(new_lines), encoding='utf-8')
    else:
        # Add new section at the end
        new_content = existing.rstrip() + f"\n\n{section_header}\n\n{content}\n"
        journal_path.write_text(new_content, encoding='utf-8')


def write_nightshift_summary(
    data_dir: Path,
    completed_tasks: List[Dict[str, Any]],
    failed_tasks: List[Dict[str, Any]] = None,
    review_tasks: List[Dict[str, Any]] = None,
    total_duration: float = 0,
    total_tokens: int = 0
) -> None:
    """
    Write nightshift execution summary to appropriate journals.

    Writes to:
    - Each space's journal (for tasks in that space)
    - Personal journal (summary of all)
    """
    if failed_tasks is None:
        failed_tasks = []
    if review_tasks is None:
        review_tasks = []

    timestamp = datetime.now().strftime('%H:%M')

    # Group tasks by space
    tasks_by_space: Dict[str, List] = {}
    for task_data in completed_tasks + review_tasks:
        space = task_data.get('space', '0-personal')
        if space not in tasks_by_space:
            tasks_by_space[space] = []
        tasks_by_space[space].append(task_data)

    # Write to each space journal
    for space, tasks in tasks_by_space.items():
        space_journal = get_journal_path(data_dir, space)

        summary_lines = [
            f"### Nightshift Run ({timestamp})",
            "",
            f"**Tasks completed**: {len([t for t in tasks if t.get('status') in ['approved', 'approved_with_notes']])}",
            f"**Tasks for review**: {len([t for t in tasks if t.get('status') == 'needs_review'])}",
            "",
            "| Task | Score | Status | Output |",
            "|------|-------|--------|--------|",
        ]

        for task_data in tasks:
            title = task_data.get('title', 'Unknown')[:30]
            score = task_data.get('score', 0)
            status = task_data.get('status', 'unknown')
            output_path = task_data.get('output_path', '')

            # Make output path relative if possible
            if output_path:
                output_link = f"[[{Path(output_path).name}]]"
            else:
                output_link = "-"

            summary_lines.append(f"| {title} | {score:.2f} | {status} | {output_link} |")

        summary_lines.append("")

        summary = '\n'.join(summary_lines)
        append_to_journal(space_journal, 'Nightshift', summary)
        print(f"Updated journal: {space_journal}")

    # Write summary to personal journal
    personal_journal = get_journal_path(data_dir, '0-personal')

    all_completed = len(completed_tasks)
    all_review = len(review_tasks)
    all_failed = len(failed_tasks)

    personal_summary = f"""### Nightshift Summary ({timestamp})

- **Completed**: {all_completed} tasks
- **For review**: {all_review} tasks
- **Failed**: {all_failed} tasks
- **Duration**: {total_duration:.1f}s
- **Tokens**: ~{total_tokens}

"""

    if all_review > 0:
        personal_summary += "**Action required**: Review pending tasks in 0-inbox/\n"

    append_to_journal(personal_journal, 'Nightshift', personal_summary)
    print(f"Updated personal journal: {personal_journal}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python journal.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])

    # Test with mock data
    completed = [
        {'title': 'Test Task 1', 'score': 0.85, 'status': 'approved', 'space': '0-personal', 'output_path': '/path/to/output1.md'},
        {'title': 'Test Task 2', 'score': 0.72, 'status': 'approved_with_notes', 'space': '0-personal', 'output_path': '/path/to/output2.md'},
    ]

    review = [
        {'title': 'Review Task', 'score': 0.65, 'status': 'needs_review', 'space': '0-personal', 'output_path': '/path/to/review.md'},
    ]

    write_nightshift_summary(
        data_dir,
        completed_tasks=completed,
        review_tasks=review,
        total_duration=120.5,
        total_tokens=15000
    )
