"""
Output writing for nightshift.
Writes results to 0-inbox/ and updates task state.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from org_parser import OrgTask
from evaluate import EvaluationResult


def generate_output_filename(task: OrgTask, exec_id: str) -> str:
    """Generate output filename for a task."""
    # Extract tag type (e.g., 'content' from ':AI:content:')
    tag = task.ai_tag or ':AI:'
    tag_type = tag.strip(':').replace('AI:', '').replace('AI', 'task')
    if not tag_type:
        tag_type = 'task'

    return f"nightshift-{exec_id}-{tag_type}.md"


def get_output_dir(task: OrgTask, data_dir: Path) -> Path:
    """Get the appropriate 0-inbox directory for this task."""
    space = task.space

    if space:
        # Check if space directory exists
        space_inbox = data_dir / space / '0-inbox'
        if space_inbox.parent.exists():
            space_inbox.mkdir(exist_ok=True)
            return space_inbox

    # Default to personal inbox
    personal_inbox = data_dir / '0-personal' / '0-inbox'
    personal_inbox.mkdir(exist_ok=True)
    return personal_inbox


def write_output(
    task: OrgTask,
    output: str,
    evaluation: EvaluationResult,
    exec_id: str,
    data_dir: Path,
    duration_seconds: float = 0,
    tokens_used: int = 0
) -> Path:
    """
    Write task output to 0-inbox/ with metadata.

    Returns the path to the created file.
    """
    output_dir = get_output_dir(task, data_dir)
    filename = generate_output_filename(task, exec_id)
    output_path = output_dir / filename

    # Build the output file content
    content_parts = []

    # Frontmatter
    content_parts.append('---')
    content_parts.append(f'nightshift_id: {exec_id}')
    content_parts.append(f'task: "{task.title}"')
    content_parts.append(f'task_type: "{task.ai_tag}"')
    content_parts.append(f'executed_at: {datetime.utcnow().isoformat()}Z')
    content_parts.append(f'score: {evaluation.consensus}')
    content_parts.append(f'status: {evaluation.decision}')

    # Evaluator scores
    content_parts.append('evaluators:')
    for evaluator, score in evaluation.scores.items():
        content_parts.append(f'  {evaluator}: {score}')

    # Requires action based on status
    if evaluation.decision == 'approved':
        content_parts.append('requires_action: none')
    elif evaluation.decision == 'approved_with_notes':
        content_parts.append('requires_action: acknowledge')
    else:
        content_parts.append('requires_action: review')

    content_parts.append('---')
    content_parts.append('')

    # Main content
    content_parts.append(f'# {task.title}')
    content_parts.append('')
    content_parts.append(output)
    content_parts.append('')

    # Nightshift metadata section
    content_parts.append('---')
    content_parts.append('')
    content_parts.append('## Nightshift Metadata')
    content_parts.append('')
    content_parts.append('### Execution')
    content_parts.append(f'- **Duration**: {duration_seconds:.1f}s')
    content_parts.append(f'- **Tokens**: ~{tokens_used}')
    content_parts.append(f'- **Task ID**: {task.id}')
    content_parts.append(f'- **Source**: `{task.file_path.name}:{task.line_number}`')
    content_parts.append('')

    # Evaluator feedback
    content_parts.append('### Evaluator Feedback')
    content_parts.append('')
    for evaluator, feedback in evaluation.feedback.items():
        score = evaluation.scores.get(evaluator, 0)
        content_parts.append(f'**{evaluator.title()}** ({score:.2f}):')
        content_parts.append(f'> {feedback}')
        content_parts.append('')

    # Consensus summary
    content_parts.append('### Consensus')
    content_parts.append(f'- **Score**: {evaluation.consensus:.2f}')
    content_parts.append(f'- **Variance**: {evaluation.variance:.4f}')
    content_parts.append(f'- **Decision**: {evaluation.decision}')
    content_parts.append('')

    # Write the file
    content = '\n'.join(content_parts)
    output_path.write_text(content, encoding='utf-8')

    print(f"Output written to: {output_path}")
    return output_path


def generate_exec_id() -> str:
    """Generate execution ID in format exec-YYYY-MM-DD-NNN."""
    today = datetime.utcnow().strftime('%Y-%m-%d')
    # For now, use timestamp for uniqueness
    timestamp = datetime.utcnow().strftime('%H%M%S')
    return f"exec-{today}-{timestamp}"


if __name__ == '__main__':
    import sys
    from evaluate import EvaluationResult, EvaluatorResult

    # Test output generation
    task = OrgTask(
        id="test-123",
        title="Test Task Output",
        state="WORKING",
        tags=["AI", "content"],
        properties={'SPACE': '0-personal'},
        file_path=Path("test.org"),
        line_number=1,
        heading_level=1,
        body="A test task"
    )

    evaluation = EvaluationResult(
        scores={'user': 0.85, 'critic': 0.70, 'ceo': 0.80},
        feedback={
            'user': 'Good practical output',
            'critic': 'Could be improved',
            'ceo': 'Strategic value present'
        },
        consensus=0.78,
        variance=0.005,
        decision='approved_with_notes',
        evaluator_results=[]
    )

    output = "This is the task output content.\n\nWith multiple paragraphs."

    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    else:
        data_dir = Path.home() / 'Data'

    exec_id = generate_exec_id()
    path = write_output(task, output, evaluation, exec_id, data_dir)
    print(f"Created: {path}")
