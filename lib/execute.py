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


def build_task_prompt(task: OrgTask, context: str = "") -> str:
    """
    Build the prompt for Claude to execute this task.

    Uses specialized agents based on task type:
    - :AI:research: → gtd-research-processor agent
    - :AI:content: → gtd-content-writer agent
    - :AI:pm: → gtd-project-manager agent
    - :AI:data: → gtd-data-analyzer agent
    - :AI: (general) → ai-task-executor agent
    """
    prompt_parts = []

    # Agent mapping
    agent_map = {
        ':AI:research:': 'gtd-research-processor',
        ':AI:content:': 'gtd-content-writer',
        ':AI:pm:': 'gtd-project-manager',
        ':AI:data:': 'gtd-data-analyzer',
        ':AI:code:': None,  # No specialized code agent yet
        ':AI:': 'ai-task-executor',
    }

    tag = task.ai_tag or ':AI:'
    agent = agent_map.get(tag, 'ai-task-executor')

    # Instruction to use the specialized agent
    prompt_parts.append(f"Execute this task using the Task tool with subagent_type='{agent}':")
    prompt_parts.append("")

    # Task details
    prompt_parts.append(f"# Task: {task.title}")
    prompt_parts.append(f"Task ID: {task.id}")
    prompt_parts.append(f"Type: {task.ai_tag}")
    prompt_parts.append("")

    # Task body if present
    if task.body:
        prompt_parts.append("## Task Description")
        prompt_parts.append(task.body)
        prompt_parts.append("")

    # Context if provided
    if context:
        prompt_parts.append("## Context")
        prompt_parts.append(context)
        prompt_parts.append("")

    # Output requirements
    prompt_parts.append("## Requirements")
    prompt_parts.append("- Use the specialized agent to complete this task")
    prompt_parts.append("- Write the output to a markdown file in the appropriate 0-inbox/ directory")
    prompt_parts.append("- Return the path to the output file when done")

    return '\n'.join(prompt_parts)


def execute_task(task: OrgTask, data_dir: Path, context: str = "") -> ExecutionResult:
    """
    Execute a task using Claude CLI.

    Returns ExecutionResult with output or error.
    """
    import time
    start_time = time.time()

    # Build prompt
    prompt = build_task_prompt(task, context)

    try:
        # Run Claude CLI with the prompt
        # Using -p for print mode (non-interactive)
        # 30 minute timeout for agent-based tasks (complex research can take time)
        result = subprocess.run(
            ['claude', '-p', prompt],
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
            ['claude', '-p', command],
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
