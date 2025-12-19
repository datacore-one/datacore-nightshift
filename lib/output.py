"""
Output writing for nightshift.
Writes results to 0-inbox/ and updates task state.
"""

import subprocess
import logging
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from org_parser import OrgTask
from evaluate import EvaluationResult

logger = logging.getLogger(__name__)


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


def get_team_members(task: OrgTask, data_dir: Path) -> List[str]:
    """Get team members from space config for review checkboxes."""
    space = task.space or '0-personal'
    config_path = data_dir / space / '.datacore' / 'config.yaml'

    if not config_path.exists():
        # Fallback to root config
        config_path = data_dir / '.datacore' / 'settings.yaml'

    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            team = config.get('team', {})
            members = team.get('members', [])
            return [m.get('id', m.get('name', 'unknown')) for m in members]
    except Exception as e:
        logger.warning(f"Could not read team config: {e}")

    return ['reviewer']  # Fallback


def write_output(
    task: OrgTask,
    output: str,
    evaluation: EvaluationResult,
    exec_id: str,
    data_dir: Path,
    duration_seconds: float = 0,
    tokens_used: int = 0
) -> Tuple[Path, bool]:
    """
    Write task output to 0-inbox/ with metadata and review section.

    Returns tuple of (path, success).
    """
    output_dir = get_output_dir(task, data_dir)
    filename = generate_output_filename(task, exec_id)
    output_path = output_dir / filename

    # Get team members for review section
    team_members = get_team_members(task, data_dir)

    # Build the output file content
    content_parts = []

    # Frontmatter
    content_parts.append('---')
    content_parts.append(f'title: "{task.title}"')
    content_parts.append('type: nightshift-output')
    content_parts.append(f'task_type: "{task.ai_tag}"')
    content_parts.append(f'created: {datetime.utcnow().strftime("%Y-%m-%d")}')
    content_parts.append(f'nightshift_id: {exec_id}')
    content_parts.append(f'score: {evaluation.consensus}')
    content_parts.append(f'status: {evaluation.decision}')
    content_parts.append('---')
    content_parts.append('')

    # Main content - the actual deliverable
    content_parts.append(f'# {task.title}')
    content_parts.append('')
    content_parts.append(output)
    content_parts.append('')

    # Review section
    content_parts.append('---')
    content_parts.append('')
    content_parts.append('## Review')
    content_parts.append('')
    content_parts.append('### Reviewed By')
    for member in team_members:
        content_parts.append(f'- [ ] @{member}')
    content_parts.append('')

    content_parts.append('### Quality Assessment')
    content_parts.append('- [ ] Content is accurate')
    content_parts.append('- [ ] Meets task requirements')
    content_parts.append('- [ ] Ready for integration')
    content_parts.append('')

    content_parts.append('### Next Steps (check all that apply)')
    content_parts.append('- [ ] Move to knowledge base: `3-knowledge/pages/`')
    content_parts.append('- [ ] Move to research: `1-tracks/research/`')
    content_parts.append('- [ ] Create follow-up tasks')
    content_parts.append('- [ ] Share with team (Slack/email)')
    content_parts.append('- [ ] Needs revision')
    content_parts.append('- [ ] Archive (low value)')
    content_parts.append('')

    content_parts.append('### Processing Instructions')
    content_parts.append('')
    content_parts.append('<!-- Reviewer: Add notes for processing this output -->')
    content_parts.append('<!-- Examples: -->')
    content_parts.append('<!-- - Target filename: Competitive-Analysis-Data-RWA.md -->')
    content_parts.append('<!-- - Follow-up tasks: Research Ocean Protocol deeper -->')
    content_parts.append('<!-- - Revision notes: Add market sizing data -->')
    content_parts.append('')
    content_parts.append('')
    content_parts.append('')

    # Nightshift metadata section (collapsible)
    content_parts.append('---')
    content_parts.append('')
    content_parts.append('## Nightshift Metadata')
    content_parts.append('')
    content_parts.append('| Field | Value |')
    content_parts.append('|-------|-------|')
    content_parts.append(f'| Task | {task.title} |')
    content_parts.append(f'| Executed | {datetime.utcnow().isoformat()}Z |')
    content_parts.append(f'| Duration | {duration_seconds:.1f}s |')
    content_parts.append(f'| Score | {evaluation.consensus:.2f} |')
    content_parts.append(f'| Status | {evaluation.decision} |')
    content_parts.append(f'| Source | {task.file_path.name}:{task.line_number} |')
    content_parts.append('')

    # Evaluator feedback in collapsible section
    content_parts.append('<details>')
    content_parts.append('<summary>Evaluator Feedback</summary>')
    content_parts.append('')
    for evaluator, feedback in evaluation.feedback.items():
        score = evaluation.scores.get(evaluator, 0)
        content_parts.append(f'**{evaluator.title()}** ({score:.2f}):')
        content_parts.append(f'> {feedback}')
        content_parts.append('')
    content_parts.append('</details>')
    content_parts.append('')

    # Write the file with error handling
    content = '\n'.join(content_parts)

    try:
        output_path.write_text(content, encoding='utf-8')

        # Verify file was written
        if not output_path.exists():
            logger.error(f"File not found after write: {output_path}")
            return (output_path, False)

        # Verify content was written correctly
        if output_path.stat().st_size < len(content) * 0.9:
            logger.error(f"File size mismatch, possible incomplete write: {output_path}")
            return (output_path, False)

        # Stage file for git
        try:
            subprocess.run(
                ['git', 'add', str(output_path)],
                cwd=str(output_path.parent),
                capture_output=True,
                timeout=10
            )
        except Exception as git_err:
            logger.warning(f"Could not stage file for git: {git_err}")
            # Continue anyway - file is written locally

        print(f"Output written to: {output_path}")
        return (output_path, True)

    except PermissionError as e:
        logger.error(f"Permission denied writing to {output_path}: {e}")
        return (output_path, False)
    except OSError as e:
        logger.error(f"OS error writing to {output_path}: {e}")
        return (output_path, False)
    except Exception as e:
        logger.error(f"Unexpected error writing output: {e}")
        return (output_path, False)


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
