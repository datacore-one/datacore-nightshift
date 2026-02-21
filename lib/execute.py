"""
Task execution via Claude CLI.
"""

import subprocess
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from org_parser import OrgTask


@dataclass
class ExecutionResult:
    """Result of executing a task."""
    success: bool
    output: str
    error: Optional[str] = None
    tokens_used: int = 0
    duration_seconds: float = 0


def determine_agent_type(task: OrgTask) -> str:
    """Map :AI:subtype: tag to agent name.

    Tags are parsed as split-by-colon list, so :AI:pm: becomes ['AI', 'pm'].
    We look for 'AI' in tags, then check the tag immediately following it
    for the subtype.
    """
    subtype_map = {
        'research': 'research-orchestrator',
        'content': 'gtd-content-writer',
        'pm': 'gtd-project-manager',
        'data': 'gtd-data-analyzer',
        'code': 'ai-task-executor',
    }
    tags = task.tags
    if 'AI' in tags:
        ai_idx = tags.index('AI')
        # Check if there's a subtype tag after AI
        if ai_idx + 1 < len(tags):
            subtype = tags[ai_idx + 1]
            return subtype_map.get(subtype, 'ai-task-executor')
    return 'ai-task-executor'


def build_task_prompt(task: OrgTask, data_dir: str = "", engram_text: str = "") -> str:
    """
    Build execution prompt from Rich Task Standard properties (DIP-0009 Part 3.5).

    Reads CONTEXT, KEY_FILES, CURRENT_STATUS, ACCEPTANCE_CRITERIA, TOOLS, ROLE
    from task properties. Sections with no content are omitted.
    """
    sections = []

    # 1. Agent routing preamble (always present)
    agent_type = determine_agent_type(task)
    sections.append(f"Execute this task using the Task tool with subagent_type='{agent_type}'.")
    if data_dir:
        sections.append(f"Working directory: {data_dir}")

    # 2. Role (optional)
    role = task.properties.get('ROLE', '').strip()
    if role:
        sections.append(f"# Role\n{role}")

    # 3. Task heading + metadata
    effort = task.properties.get('EFFORT', 'Unknown')
    tags_str = ', '.join(task.tags) if task.tags else 'none'
    meta = f"# Task: {task.title}\nTask ID: {task.id}  |  Effort: {effort}  |  Tags: {tags_str}"
    sections.append(meta)

    # 4-8. Rich context sections (omit if empty)
    for prop, heading in [
        ('CONTEXT', 'Context'),
        ('CURRENT_STATUS', 'Current Status'),
        ('KEY_FILES', 'Key Files to Read'),
        ('ACCEPTANCE_CRITERIA', 'Acceptance Criteria'),
        ('TOOLS', 'Approach'),
    ]:
        val = task.properties.get(prop, '').strip()
        if val:
            sections.append(f"## {heading}\n{val}")

    # 9. Engrams (runtime-resolved, passed in by execute_task)
    if engram_text:
        sections.append(f"## Applicable Engrams\n{engram_text}")

    # 10. Task body
    if task.body:
        sections.append(f"## Task Body\n{task.body}")

    return '\n\n'.join(sections)


def execute_task(task: OrgTask, data_dir: Path, context: str = "") -> ExecutionResult:
    """
    Execute a task using Claude CLI.

    Reads Rich Task Standard properties and injects runtime engrams.
    Returns ExecutionResult with output or error.
    """
    import time
    start_time = time.time()

    # Runtime engram injection (DIP-0019)
    engram_text = ''
    try:
        import sys
        lib_dir = str(Path(__file__).parent.parent.parent.parent / 'lib')
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from engram_selector import select_engrams, format_injection
        engrams = select_engrams(scope='global', task_desc=task.title, limit=5)
        engram_text = format_injection(engrams, limit=5)
    except (ImportError, Exception):
        pass  # Engram injection is optional; degrade gracefully

    # Build prompt with Rich Task Standard properties
    prompt = build_task_prompt(task, data_dir=str(data_dir), engram_text=engram_text)

    try:
        # Run Claude CLI with the prompt
        # Using -p for print mode (non-interactive)
        # 30 minute timeout for agent-based tasks (complex research can take time)
        result = subprocess.run(
            ['claude', '-p', '--dangerously-skip-permissions', prompt],
            cwd=data_dir,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )

        duration = time.time() - start_time

        if result.returncode == 0:
            return ExecutionResult(
                success=True,
                output=result.stdout,
                duration_seconds=duration,
                tokens_used=estimate_tokens(prompt + result.stdout)
            )
        else:
            return ExecutionResult(
                success=False,
                output=result.stdout,
                error=result.stderr,
                duration_seconds=duration
            )

    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            output="",
            error="Execution timed out after 30 minutes",
            duration_seconds=1800
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            output="",
            error=str(e),
            duration_seconds=time.time() - start_time
        )


def execute_command(command: str, data_dir: Path) -> ExecutionResult:
    """
    Execute a slash command (e.g., /today) using Claude CLI.
    """
    import time
    start_time = time.time()

    try:
        result = subprocess.run(
            ['claude', '-p', '--dangerously-skip-permissions', command],
            cwd=data_dir,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout for commands
        )

        duration = time.time() - start_time

        if result.returncode == 0:
            return ExecutionResult(
                success=True,
                output=result.stdout,
                duration_seconds=duration,
                tokens_used=estimate_tokens(result.stdout)
            )
        else:
            return ExecutionResult(
                success=False,
                output=result.stdout,
                error=result.stderr,
                duration_seconds=duration
            )

    except subprocess.TimeoutExpired:
        return ExecutionResult(
            success=False,
            output="",
            error="Command timed out",
            duration_seconds=300
        )
    except Exception as e:
        return ExecutionResult(
            success=False,
            output="",
            error=str(e),
            duration_seconds=time.time() - start_time
        )


def estimate_tokens(text: str) -> int:
    """Rough estimate of tokens (4 chars per token)."""
    return len(text) // 4


if __name__ == '__main__':
    import sys
    from org_parser import find_ai_tasks

    if len(sys.argv) < 2:
        print("Usage: python execute.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])

    # Test with first task
    tasks = find_ai_tasks(data_dir, states=['TODO', 'NEXT'])
    if not tasks:
        print("No tasks found")
        sys.exit(0)

    task = tasks[0]
    print(f"Executing: {task.title}")
    print("-" * 40)

    result = execute_task(task, data_dir)

    if result.success:
        print(f"SUCCESS ({result.duration_seconds:.1f}s, ~{result.tokens_used} tokens)")
        print(result.output[:500] + "..." if len(result.output) > 500 else result.output)
    else:
        print(f"FAILED: {result.error}")
