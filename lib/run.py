#!/usr/bin/env python3
"""
Main nightshift execution loop.
Orchestrates the full pipeline: queue -> claim -> execute -> evaluate -> output.
"""

import sys
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from org_parser import OrgTask, find_ai_tasks
from queue import build_queue, QueuedTask
from claim import claim_task, complete_task, git_pull, git_commit_push
from execute import execute_task, execute_command, ExecutionResult
from evaluate import evaluate_output, EvaluationResult
from output import write_output, generate_exec_id
from journal import write_nightshift_summary


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

    # Process tasks
    completed = []
    failed = []
    review = []
    total_tokens = 0

    for i, queued_task in enumerate(queue):
        task = queued_task.task
        print(f"\n[3/7] Processing task {i+1}/{len(queue)}: {task.title}")

        # Claim task
        print("  - Claiming task...")
        if not claim_task(task, data_dir):
            print("  - SKIP: Could not claim (conflict or error)")
            continue

        # Generate execution ID
        exec_id = generate_exec_id()
        print(f"  - Execution ID: {exec_id}")

        # Execute task
        print("  - Executing task...")
        exec_result = execute_task(task, data_dir)

        if not exec_result.success:
            print(f"  - FAILED: {exec_result.error}")
            complete_task(task, data_dir, 'failed', 0.0, '')
            failed.append({
                'title': task.title,
                'space': task.space,
                'error': exec_result.error
            })
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
        output_path = write_output(
            task=task,
            output=exec_result.output,
            evaluation=eval_result,
            exec_id=exec_id,
            data_dir=data_dir,
            duration_seconds=exec_result.duration_seconds,
            tokens_used=exec_result.tokens_used
        )

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

        print(f"  - Done!")

    # Write journal summary
    total_duration = time.time() - start_time
    print(f"\n[6/7] Writing journal entries...")
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
    print(f"Duration: {total_duration:.1f}s")
    print(f"Tokens: ~{total_tokens}")

    return {
        'completed': completed,
        'failed': failed,
        'review': review,
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
