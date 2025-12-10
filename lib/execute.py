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
    """Build the prompt for Claude to execute this task."""
    prompt_parts = []

    # Task header
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

    # Instructions based on task type
    task_type_instructions = {
        ':AI:research:': "Research this topic thoroughly. Provide sources and citations where possible.",
        ':AI:content:': "Generate high-quality content following best practices. Be clear, concise, and engaging.",
        ':AI:data:': "Analyze the data and provide insights. Include visualizations or structured output where helpful.",
        ':AI:pm:': "Provide project management analysis. Consider timelines, risks, and dependencies.",
        ':AI:code:': "Write clean, well-documented code. Include tests if appropriate.",
        ':AI:': "Complete this task to the best of your ability.",
    }

    tag = task.ai_tag or ':AI:'
    instructions = task_type_instructions.get(tag, task_type_instructions[':AI:'])

    prompt_parts.append("## Instructions")
    prompt_parts.append(instructions)
    prompt_parts.append("")

    prompt_parts.append("## Output")
    prompt_parts.append("Provide your complete response below:")

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
        result = subprocess.run(
            ['claude', '-p', prompt],
            cwd=data_dir,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
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
            error="Execution timed out after 10 minutes",
            duration_seconds=600
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
