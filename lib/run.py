#!/usr/bin/env python3
"""
Main nightshift execution loop.
Orchestrates the full pipeline: queue -> claim -> execute -> evaluate -> output.
"""

import sys
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from nightshift_parser import OrgTask, find_ai_tasks
from queue import build_queue, QueuedTask, load_config
from claim import claim_task, complete_task, git_pull, git_commit_push
from execute import execute_task, execute_command, ExecutionResult
from evaluate import evaluate_output, EvaluationResult
from output import write_output, generate_exec_id
from journal import write_nightshift_summary
from summary import write_summary_file, generate_journal_summary
from execution_recorder import record_execution

# Add .datacore/lib to path for hooks
_lib_path = str(Path(__file__).resolve().parent.parent.parent.parent / ".datacore" / "lib")
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)

try:
    from hooks import HookExecutor
    _HOOKS_AVAILABLE = True
except ImportError:
    _HOOKS_AVAILABLE = False


# Failure analysis patterns for categorizing execution errors
_TRANSIENT_PATTERNS = [
    'timeout', 'timed out', 'rate limit', 'rate_limit', 'connection reset',
    'connection refused', 'temporary', 'retry', '529', '503', '429',
    'overloaded', 'capacity',
]

_CONTEXT_PATTERNS = [
    'file not found', 'no such file', 'missing', 'not found',
    'broken link', 'stale', 'does not exist',
]

_CAPABILITY_PATTERNS = [
    'permission denied', 'access denied', 'unauthorized', 'forbidden',
    'not supported', 'not implemented', 'requires',
]


def analyze_failure(task: OrgTask, error: str) -> dict:
    """Classify a task execution failure and determine retry eligibility.

    Returns dict with: category, root_cause, retryable, recommendation.
    """
    error_lower = error.lower() if error else ''

    # Check patterns in priority order
    for pattern in _TRANSIENT_PATTERNS:
        if pattern in error_lower:
            return {
                'category': 'transient',
                'root_cause': f'Transient error: {pattern}',
                'retryable': True,
                'recommendation': 'Retry with backoff',
            }

    for pattern in _CONTEXT_PATTERNS:
        if pattern in error_lower:
            return {
                'category': 'context',
                'root_cause': f'Context issue: {pattern}',
                'retryable': False,
                'recommendation': 'Review task context and referenced files',
            }

    for pattern in _CAPABILITY_PATTERNS:
        if pattern in error_lower:
            return {
                'category': 'capability',
                'root_cause': f'Capability gap: {pattern}',
                'retryable': False,
                'recommendation': 'Task requires access or tools not available',
            }

    # Check if task has sufficient specification
    if not task.properties.get('CONTEXT') and not task.properties.get('ACCEPTANCE_CRITERIA'):
        return {
            'category': 'specification',
            'root_cause': 'Task lacks CONTEXT and ACCEPTANCE_CRITERIA properties',
            'retryable': False,
            'recommendation': 'Add Rich Task Standard properties before retry',
        }

    return {
        'category': 'unknown',
        'root_cause': error[:200] if error else 'No error message',
        'retryable': True,
        'recommendation': 'Retry once; if still failing, escalate to human review',
    }


# ---- Budget enforcement (DIP-0011 5.2) ----

# Cost estimate: tokens / 1000 * price per 1k tokens (same as metrics.py)
_COST_PER_1K_TOKENS = 0.015


def _get_budget_limit(data_dir: Path) -> float:
    """Read budget_daily_usd from settings. Returns 0 for unlimited."""
    config = load_config(data_dir)
    return float(config.get('nightshift', {}).get('budget_daily_usd', 0))


def _get_today_spend(data_dir: Path) -> float:
    """Sum estimated cost from today's execution records in state/nightshift/."""
    state_dir = data_dir / '.datacore' / 'state' / 'nightshift'
    if not state_dir.exists():
        return 0.0

    today_prefix = datetime.now(timezone.utc).strftime('%Y%m%d')
    total = 0.0

    for f in state_dir.glob(f'{today_prefix}-*.json'):
        try:
            data = json.loads(f.read_text())
            tokens = data.get('tokens_used', 0)
            total += (tokens / 1000) * _COST_PER_1K_TOKENS
        except (json.JSONDecodeError, OSError):
            continue

    return total


def check_budget(data_dir: Path) -> tuple:
    """Check if daily budget allows another task.

    Returns:
        (allowed: bool, spent: float, limit: float)
        If limit is 0, budget is unlimited and allowed is always True.
    """
    limit = _get_budget_limit(data_dir)
    if limit <= 0:
        return (True, 0.0, 0.0)

    spent = _get_today_spend(data_dir)
    return (spent < limit, spent, limit)


def run_command_mode(data_dir: Path, command: str) -> bool:
    """
    Execute a slash command (e.g., /today).
    Used for scheduled command execution.
    """
    print(f"=" * 50)
    print(f"Nightshift: Executing command {command}")
    print(f"=" * 50)

    # Pull latest
    print("\nPulling latest changes...")
    git_pull(data_dir)

    # Execute the command
    print(f"\nRunning: {command}")
    result = execute_command(command, data_dir)

    if result.success:
        print(f"\nCommand completed successfully ({result.duration_seconds:.1f}s)")
        # Commit and push any changes
        git_commit_push(data_dir, f"nightshift: {command} {time.strftime('%Y-%m-%d')}")
        return True
    else:
        print(f"\nCommand failed: {result.error}")
        return False


def run_task_mode(
    data_dir: Path,
    test_mode: bool = False,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute :AI: tasks from the queue.

    Args:
        data_dir: Path to Data directory
        test_mode: If True, only process one task
        limit: Maximum number of tasks to process

    Returns:
        Summary dict with completed, failed, review tasks
    """
    print(f"=" * 50)
    print("Nightshift: AI Task Execution")
    print(f"=" * 50)
    print(f"Data directory: {data_dir}")
    print(f"Mode: {'TEST (single task)' if test_mode else 'FULL'}")

    start_time = time.time()

    # Load config
    config = load_config(data_dir)
    max_retries = config.get('nightshift', {}).get('max_retries', 2)

    # Initialize hook executor
    hook_executor = None
    if _HOOKS_AVAILABLE:
        try:
            hook_executor = HookExecutor()
        except Exception as e:
            print(f"WARNING: Could not initialize hooks: {e}")

    # Pull latest
    print("\n[1/7] Pulling latest changes...")
    if not git_pull(data_dir):
        print("WARNING: Git pull had issues, continuing anyway...")

    # Build queue
    print("\n[2/7] Building task queue...")
    if test_mode:
        limit = 1
    queue = build_queue(data_dir, limit=limit)

    if not queue:
        print("No :AI: tasks in queue. Nothing to do.")
        return {'completed': [], 'failed': [], 'review': [], 'duration': 0, 'tokens': 0}

    print(f"Found {len(queue)} tasks to process")
    for i, item in enumerate(queue[:5], 1):  # Show first 5
        print(f"  {i}. [{item.task.state}] {item.task.title} (priority: {item.priority_score})")
    if len(queue) > 5:
        print(f"  ... and {len(queue) - 5} more")

    # Budget status
    budget_allowed, budget_spent, budget_limit = check_budget(data_dir)
    if budget_limit > 0:
        print(f"\n  Budget: ${budget_spent:.2f} / ${budget_limit:.2f} USD today")
        if not budget_allowed:
            print("  Budget exhausted -- skipping all tasks")

    # Process tasks
    completed = []
    failed = []
    review = []
    skipped = []
    total_tokens = 0

    for i, queued_task in enumerate(queue):
        task = queued_task.task
        print(f"\n[3/7] Processing task {i+1}/{len(queue)}: {task.title}")

        # Budget gate
        budget_allowed, budget_spent, budget_limit = check_budget(data_dir)
        if not budget_allowed:
            reason = f"Daily budget exhausted (${budget_spent:.2f} / ${budget_limit:.2f})"
            print(f"  - SKIP: {reason}")
            skipped.append({'title': task.title, 'space': task.space, 'reason': reason})
            record_execution(data_dir=data_dir, task_title=task.title, space=task.space or '0-personal', ai_tag=task.ai_tag or ':AI:', status='skipped', score=0.0, duration_seconds=0, tokens_used=0, exec_id=generate_exec_id(), error=reason)
            continue

        # Claim task
        print("  - Claiming task...")
        if not claim_task(task, data_dir):
            print("  - SKIP: Could not claim (conflict or error)")
            continue

        # Generate execution ID
        exec_id = generate_exec_id()
        print(f"  - Execution ID: {exec_id}")

        # Pre-execution hooks
        hook_context = ""
        if hook_executor:
            try:
                agent_id = task.ai_tag.strip(':').replace('AI:', '') if task.ai_tag else 'ai-task-executor'
                should_continue, hook_context = hook_executor.execute_pre_hooks(agent_id, task.title)
                if not should_continue:
                    print(f"  - SKIP: Pre-hook aborted execution")
                    record_execution(data_dir=data_dir, task_title=task.title, space=task.space or '0-personal', ai_tag=task.ai_tag or ':AI:', status='skipped', score=0.0, duration_seconds=0, tokens_used=0, exec_id=exec_id, error=f"Pre-hook abort: {hook_context}")
                    continue
            except Exception as e:
                print(f"  - WARNING: Pre-hook error (continuing): {e}")

        # Execute task
        print("  - Executing task...")
        exec_result = execute_task(task, data_dir)

        if not exec_result.success:
            print(f"  - FAILED: {exec_result.error}")

            # Failure analysis hook — classify and determine retry eligibility
            failure_info = analyze_failure(task, exec_result.error)
            print(f"  - Failure analysis: {failure_info['category']} — {failure_info['root_cause']}")

            # Error hooks
            if hook_executor:
                try:
                    agent_id = task.ai_tag.strip(':').replace('AI:', '') if task.ai_tag else 'ai-task-executor'
                    hook_executor.execute_error_hooks(agent_id, Exception(exec_result.error))
                except Exception as e:
                    print(f"  - WARNING: Error hook failed: {e}")

            if failure_info['retryable'] and int(task.properties.get('NIGHTSHIFT_RETRIES', '0')) < max_retries:
                print(f"  - Retrying (transient failure)...")
                retry_count = int(task.properties.get('NIGHTSHIFT_RETRIES', '0')) + 1
                task.properties['NIGHTSHIFT_RETRIES'] = str(retry_count)
                exec_result = execute_task(task, data_dir)
                if exec_result.success:
                    print(f"  - Retry succeeded!")
                    # Fall through to evaluation below
                else:
                    print(f"  - Retry also failed: {exec_result.error}")
                    complete_task(task, data_dir, 'failed', 0.0, '')
                    failed.append({
                        'title': task.title,
                        'space': task.space,
                        'error': exec_result.error,
                        'failure_analysis': failure_info,
                    })
                    record_execution(data_dir=data_dir, task_title=task.title, space=task.space or '0-personal', ai_tag=task.ai_tag or ':AI:', status='failed', score=0.0, duration_seconds=exec_result.duration_seconds, tokens_used=exec_result.tokens_used, exec_id=exec_id, error=exec_result.error, failure_analysis=failure_info)
                    git_commit_push(data_dir, f"nightshift: fail {task.id}")
                    continue
            else:
                complete_task(task, data_dir, 'failed', 0.0, '')
                failed.append({
                    'title': task.title,
                    'space': task.space,
                    'error': exec_result.error,
                    'failure_analysis': failure_info,
                })
                record_execution(data_dir=data_dir, task_title=task.title, space=task.space or '0-personal', ai_tag=task.ai_tag or ':AI:', status='failed', score=0.0, duration_seconds=exec_result.duration_seconds, tokens_used=exec_result.tokens_used, exec_id=exec_id, error=exec_result.error, failure_analysis=failure_info)
                git_commit_push(data_dir, f"nightshift: fail {task.id}")
                continue

        print(f"  - Execution complete ({exec_result.duration_seconds:.1f}s, ~{exec_result.tokens_used} tokens)")
        total_tokens += exec_result.tokens_used

        # Evaluate output
        print("  - Evaluating output...")
        eval_result = evaluate_output(task, exec_result.output, data_dir)
        print(f"  - Consensus: {eval_result.consensus:.2f} -> {eval_result.decision}")

        # Write output to 0-inbox
        print("  - Writing output...")
        output_path, write_success = write_output(
            task=task,
            output=exec_result.output,
            evaluation=eval_result,
            exec_id=exec_id,
            data_dir=data_dir,
            duration_seconds=exec_result.duration_seconds,
            tokens_used=exec_result.tokens_used
        )

        if not write_success:
            print(f"  - FAILED: Could not write output to {output_path}")
            complete_task(task, data_dir, 'failed', 0.0, '')
            failed.append({
                'title': task.title,
                'space': task.space,
                'error': f'Output write failed: {output_path}'
            })
            git_commit_push(data_dir, f"nightshift: write-fail {task.id}")
            continue

        # Update task state
        print("  - Completing task...")
        complete_task(
            task=task,
            data_dir=data_dir,
            status=eval_result.decision,
            score=eval_result.consensus,
            output_path=str(output_path)
        )

        # Commit and push
        git_commit_push(data_dir, f"nightshift: complete {task.id}")

        # Categorize result
        task_result = {
            'title': task.title,
            'space': task.space,
            'score': eval_result.consensus,
            'status': eval_result.decision,
            'output_path': str(output_path)
        }

        if eval_result.decision in ['approved', 'approved_with_notes']:
            completed.append(task_result)
        else:
            review.append(task_result)

        # Post-execution hooks
        if hook_executor:
            try:
                agent_id = task.ai_tag.strip(':').replace('AI:', '') if task.ai_tag else 'ai-task-executor'
                hook_executor.execute_post_hooks(agent_id, {'output': exec_result.output, 'score': eval_result.consensus, 'decision': eval_result.decision, 'duration': exec_result.duration_seconds, 'tokens': exec_result.tokens_used, 'task_title': task.title, 'space': task.space or '0-personal'})
            except Exception as e:
                print(f"  - WARNING: Post-hook error: {e}")

        # Record execution for analytics
        record_execution(data_dir=data_dir, task_title=task.title, space=task.space or '0-personal', ai_tag=task.ai_tag or ':AI:', status=eval_result.decision, score=eval_result.consensus, duration_seconds=exec_result.duration_seconds, tokens_used=exec_result.tokens_used, exec_id=exec_id)

        print(f"  - Done!")

    # Write summary report and journal entries
    total_duration = time.time() - start_time
    print(f"\n[6/7] Writing summary report and journal entries...")

    # Write consolidated summary file to each space's 0-inbox
    spaces_with_tasks = set()
    for task in completed + review + failed:
        space = task.get('space') or '0-personal'
        spaces_with_tasks.add(space)

    for space in spaces_with_tasks:
        space_completed = [t for t in completed if (t.get('space') or '0-personal') == space]
        space_review = [t for t in review if (t.get('space') or '0-personal') == space]
        space_failed = [t for t in failed if (t.get('space') or '0-personal') == space]

        if space_completed or space_review or space_failed:
            write_summary_file(
                data_dir=data_dir,
                space=space,
                completed_tasks=space_completed,
                failed_tasks=space_failed,
                review_tasks=space_review,
                total_duration=total_duration,
                total_tokens=total_tokens
            )

    # Write journal entries (existing behavior)
    write_nightshift_summary(
        data_dir=data_dir,
        completed_tasks=completed,
        failed_tasks=failed,
        review_tasks=review,
        total_duration=total_duration,
        total_tokens=total_tokens
    )

    # Final push
    print("\n[7/7] Final commit and push...")
    git_commit_push(data_dir, "nightshift: batch-end")

    # Summary
    print(f"\n{'=' * 50}")
    print("Nightshift Complete!")
    print(f"{'=' * 50}")
    print(f"Completed: {len(completed)}")
    print(f"For Review: {len(review)}")
    print(f"Failed: {len(failed)}")
    if skipped:
        print(f"Skipped (budget): {len(skipped)}")
    print(f"Duration: {total_duration:.1f}s")
    print(f"Tokens: ~{total_tokens}")

    return {
        'completed': completed,
        'failed': failed,
        'review': review,
        'skipped': skipped,
        'duration': total_duration,
        'tokens': total_tokens
    }


def main():
    parser = argparse.ArgumentParser(description='Nightshift - Autonomous AI Task Execution')
    parser.add_argument('data_dir', type=Path, help='Path to Data directory')
    parser.add_argument('--command', '-c', type=str, help='Execute a slash command (e.g., /today)')
    parser.add_argument('--test', action='store_true', help='Test mode: process only one task')
    parser.add_argument('--limit', '-l', type=int, help='Maximum tasks to process')
    parser.add_argument('--final', action='store_true', help='Final batch mode (same as regular)')

    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"ERROR: Data directory does not exist: {args.data_dir}")
        sys.exit(1)

    if args.command:
        # Command mode (e.g., /today)
        success = run_command_mode(args.data_dir, args.command)
        sys.exit(0 if success else 1)
    else:
        # Task execution mode
        result = run_task_mode(
            args.data_dir,
            test_mode=args.test,
            limit=args.limit
        )
        # Exit with error if any failures
        sys.exit(1 if result['failed'] else 0)


if __name__ == '__main__':
    main()
