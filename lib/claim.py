"""
Git-based task claiming for nightshift.
Implements distributed locking via git commit+push.
"""

import subprocess
import socket
from pathlib import Path
from datetime import datetime
from typing import Optional

from org_parser import OrgTask, update_task_property, update_task_state, write_org_file


def get_executor_id() -> str:
    """Get a unique identifier for this executor."""
    hostname = socket.gethostname()
    return f"server:{hostname}"


def now_iso() -> str:
    """Get current time in ISO format."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def git_pull(data_dir: Path) -> bool:
    """Pull latest changes. Returns True on success."""
    result = subprocess.run(
        ['git', 'pull', '--rebase', '--autostash'],
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def is_file_gitignored(data_dir: Path, file_path: Path) -> bool:
    """Check if a file is gitignored."""
    result = subprocess.run(
        ['git', 'check-ignore', '-q', str(file_path)],
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0  # Exit 0 means file IS ignored


def git_add(data_dir: Path, file_path: Path, force: bool = False) -> bool:
    """Stage a file. Returns True on success."""
    cmd = ['git', 'add']
    if force:
        cmd.append('-f')
    cmd.append(str(file_path))
    result = subprocess.run(
        cmd,
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def git_commit(data_dir: Path, message: str) -> bool:
    """Commit staged changes. Returns True on success."""
    result = subprocess.run(
        ['git', 'commit', '-m', message],
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def git_push(data_dir: Path) -> bool:
    """Push changes. Returns True on success."""
    result = subprocess.run(
        ['git', 'push'],
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def git_reset_hard(data_dir: Path, ref: str = 'HEAD~1') -> bool:
    """Hard reset to ref. Returns True on success."""
    result = subprocess.run(
        ['git', 'reset', '--hard', ref],
        cwd=data_dir,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def claim_task(task: OrgTask, data_dir: Path, use_git: bool = True) -> bool:
    """
    Claim a task via git commit+push (distributed lock) or locally.

    If use_git is True and the file is gitignored, falls back to local mode.

    Returns True if claim succeeded, False if someone else claimed it.
    """
    executor_id = get_executor_id()
    started_at = now_iso()

    # Check if file is gitignored - if so, skip git operations
    file_is_gitignored = is_file_gitignored(data_dir, task.file_path)
    skip_git = not use_git or file_is_gitignored

    if file_is_gitignored:
        print(f"  NOTE: File is gitignored, using local mode (no git sync)")

    # Update org file with claim properties
    content = task.file_path.read_text(encoding='utf-8')

    # Set state to WORKING
    content = update_task_state(task, 'WORKING')
    task.state = 'WORKING'  # Update in memory too

    # Reload and add properties
    task.file_path.write_text(content, encoding='utf-8')
    task = OrgTask(
        id=task.id,
        title=task.title,
        state='WORKING',
        tags=task.tags,
        properties=task.properties,
        file_path=task.file_path,
        line_number=task.line_number,
        heading_level=task.heading_level,
        body=task.body
    )

    content = update_task_property(task, 'NIGHTSHIFT_STATUS', 'executing')
    write_org_file(task.file_path, content)

    content = task.file_path.read_text(encoding='utf-8')
    task.properties['NIGHTSHIFT_STATUS'] = 'executing'

    # Find the task heading and add all properties
    final_content = content.replace(
        ':NIGHTSHIFT_STATUS: executing',
        f':NIGHTSHIFT_STATUS: executing\n:NIGHTSHIFT_EXECUTOR: {executor_id}\n:NIGHTSHIFT_STARTED: {started_at}'
    )
    write_org_file(task.file_path, final_content)

    # If skipping git, we're done - local claim successful
    if skip_git:
        print(f"CLAIMED (local): {task.id} by {executor_id}")
        return True

    # Git-based claim for distributed locking
    if not git_add(data_dir, task.file_path):
        print(f"ERROR: Failed to stage {task.file_path}")
        return False

    commit_message = f"nightshift: claim {task.id}"
    if not git_commit(data_dir, commit_message):
        print(f"ERROR: Failed to commit claim for {task.id}")
        return False

    # Push (this is the lock acquisition)
    if not git_push(data_dir):
        print(f"CONFLICT: Someone else claimed {task.id}, reverting...")
        git_reset_hard(data_dir, 'HEAD~1')
        git_pull(data_dir)
        return False

    print(f"CLAIMED: {task.id} by {executor_id}")
    return True


def complete_task(
    task: OrgTask,
    data_dir: Path,
    status: str,
    score: float,
    output_path: str
) -> bool:
    """
    Mark a task as complete with final status.

    status: approved, approved_with_notes, needs_review, failed
    """
    completed_at = now_iso()

    # Map status to org state
    state_map = {
        'approved': 'DONE',
        'approved_with_notes': 'DONE',
        'needs_review': 'REVIEW',
        'failed': 'FAILED'
    }
    new_state = state_map.get(status, 'REVIEW')

    # Update org file
    content = task.file_path.read_text(encoding='utf-8')

    # Update state
    content = update_task_state(task, new_state)
    write_org_file(task.file_path, content)

    # Update properties
    task.state = new_state
    content = task.file_path.read_text(encoding='utf-8')

    # Add completion properties
    props_to_add = [
        ('NIGHTSHIFT_STATUS', status),
        ('NIGHTSHIFT_COMPLETED', completed_at),
        ('NIGHTSHIFT_SCORE', str(score)),
        ('NIGHTSHIFT_OUTPUT', output_path),
    ]

    for prop_name, prop_value in props_to_add:
        content = content.replace(
            ':NIGHTSHIFT_STATUS: executing',
            f':NIGHTSHIFT_STATUS: {status}'
        )

    # Just append the properties (simplified)
    # Find :NIGHTSHIFT_STATUS: line and add after it
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if ':NIGHTSHIFT_STATUS:' in line:
            insert_lines = [
                f':NIGHTSHIFT_COMPLETED: {completed_at}',
                f':NIGHTSHIFT_SCORE: {score}',
                f':NIGHTSHIFT_OUTPUT: {output_path}'
            ]
            for j, new_line in enumerate(insert_lines):
                lines.insert(i + 1 + j, new_line)
            break

    content = '\n'.join(lines)
    write_org_file(task.file_path, content)

    return True


def git_commit_push(data_dir: Path, message: str, files: Optional[list] = None) -> bool:
    """Stage files (or all), commit, and push."""
    if files:
        for f in files:
            git_add(data_dir, f)
    else:
        subprocess.run(['git', 'add', '-A'], cwd=data_dir, capture_output=True)

    git_commit(data_dir, message)
    return git_push(data_dir)


if __name__ == '__main__':
    import sys
    from org_parser import find_ai_tasks

    if len(sys.argv) < 2:
        print("Usage: python claim.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])

    # Find first claimable task
    tasks = find_ai_tasks(data_dir, states=['TODO', 'NEXT'])
    if not tasks:
        print("No tasks to claim")
        sys.exit(0)

    task = tasks[0]
    print(f"Attempting to claim: {task.title}")

    if claim_task(task, data_dir):
        print("Claim succeeded!")
    else:
        print("Claim failed (conflict or error)")
