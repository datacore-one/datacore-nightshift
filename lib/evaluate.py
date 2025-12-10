"""
Evaluator orchestration for nightshift.
Runs persona evaluators and computes consensus.
"""

import subprocess
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from org_parser import OrgTask


# Evaluator selection matrix - which evaluators to run for each task type
EVALUATOR_MATRIX = {
    ':AI:content:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['twain', 'hemingway', 'orwell']
    },
    ':AI:research:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['popper', 'kahneman', 'data']
    },
    ':AI:data:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['tufte', 'feynman', 'data']
    },
    ':AI:pm:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['bezos', 'picard']
    },
    ':AI:strategy:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['buffett', 'musk', 'socrates', 'taleb']
    },
    ':AI:code:': {
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': ['dijkstra', 'data']
    },
    ':AI:': {  # Default
        'core': ['user', 'critic', 'ceo', 'cto', 'coo', 'archivist'],
        'domain': []
    }
}


@dataclass
class EvaluatorResult:
    """Result from a single evaluator."""
    evaluator: str
    score: float
    feedback: str
    raw_output: str


@dataclass
class EvaluationResult:
    """Combined result from all evaluators."""
    scores: Dict[str, float]
    feedback: Dict[str, str]
    consensus: float
    variance: float
    decision: str  # approved, approved_with_notes, needs_review
    evaluator_results: List[EvaluatorResult]


def get_evaluators_for_task(task: OrgTask) -> List[str]:
    """Get list of evaluator names to run for this task type."""
    tag = task.ai_tag or ':AI:'

    # Get from matrix, fallback to default
    config = EVALUATOR_MATRIX.get(tag, EVALUATOR_MATRIX[':AI:'])

    return config['core'] + config['domain']


def build_evaluation_prompt(evaluator: str, task: OrgTask, output: str) -> str:
    """Build prompt for an evaluator agent."""
    prompt = f"""# Evaluation Request

## Evaluator
You are the {evaluator} evaluator. Apply your persona's evaluation criteria.

## Task Being Evaluated
Title: {task.title}
Type: {task.ai_tag}
Description: {task.body or 'N/A'}

## Output to Evaluate
{output}

## Instructions
Evaluate this output according to your persona's criteria and scoring rubric.

You MUST respond with a YAML block containing:
- evaluator: "{evaluator}"
- score: <number between 0.0 and 1.0>
- feedback: "<your feedback>"

Example:
```yaml
evaluator: {evaluator}
score: 0.75
feedback: "The output is good but could be improved by..."
```

Provide your evaluation:
"""
    return prompt


def run_evaluator(
    evaluator: str,
    task: OrgTask,
    output: str,
    data_dir: Path
) -> EvaluatorResult:
    """
    Run a single evaluator agent on the output.

    Returns EvaluatorResult with score and feedback.
    """
    prompt = build_evaluation_prompt(evaluator, task, output)

    try:
        # Run Claude CLI with the evaluator prompt
        result = subprocess.run(
            ['claude', '-p', prompt],
            cwd=data_dir,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout per evaluator
        )

        if result.returncode != 0:
            return EvaluatorResult(
                evaluator=evaluator,
                score=0.5,  # Default to neutral on error
                feedback=f"Evaluator error: {result.stderr}",
                raw_output=result.stdout
            )

        # Parse the YAML output
        raw_output = result.stdout
        score, feedback = parse_evaluator_output(raw_output, evaluator)

        return EvaluatorResult(
            evaluator=evaluator,
            score=score,
            feedback=feedback,
            raw_output=raw_output
        )

    except subprocess.TimeoutExpired:
        return EvaluatorResult(
            evaluator=evaluator,
            score=0.5,
            feedback="Evaluator timed out",
            raw_output=""
        )
    except Exception as e:
        return EvaluatorResult(
            evaluator=evaluator,
            score=0.5,
            feedback=f"Error: {str(e)}",
            raw_output=""
        )


def parse_evaluator_output(output: str, evaluator: str) -> tuple:
    """Parse score and feedback from evaluator output."""
    # Try to find YAML block
    yaml_match = re.search(r'```yaml\s*(.*?)\s*```', output, re.DOTALL)
    if yaml_match:
        yaml_content = yaml_match.group(1)
    else:
        yaml_content = output

    # Extract score
    score_match = re.search(r'score:\s*([\d.]+)', yaml_content)
    score = float(score_match.group(1)) if score_match else 0.5

    # Clamp score to valid range
    score = max(0.0, min(1.0, score))

    # Extract feedback
    feedback_match = re.search(r'feedback:\s*["\']?(.+?)["\']?\s*(?:\n|$)', yaml_content, re.DOTALL)
    feedback = feedback_match.group(1).strip() if feedback_match else "No feedback provided"

    return score, feedback


def compute_consensus(scores: Dict[str, float]) -> tuple:
    """Compute consensus score and variance from individual scores."""
    if not scores:
        return 0.5, 0.0

    values = list(scores.values())
    n = len(values)

    # Mean
    mean = sum(values) / n

    # Variance
    variance = sum((x - mean) ** 2 for x in values) / n

    return round(mean, 3), round(variance, 4)


def make_decision(consensus: float, variance: float) -> str:
    """Make approval decision based on consensus and variance."""
    # High variance indicates disagreement - be more cautious
    if variance > 0.1:
        # Evaluators disagree significantly
        if consensus >= 0.85:
            return 'approved_with_notes'
        else:
            return 'needs_review'

    # Low variance - evaluators agree
    if consensus >= 0.80:
        return 'approved'
    elif consensus >= 0.70:
        return 'approved_with_notes'
    else:
        return 'needs_review'


def evaluate_output(task: OrgTask, output: str, data_dir: Path) -> EvaluationResult:
    """
    Run all relevant evaluators on the output.

    Returns EvaluationResult with consensus and decision.
    """
    evaluators = get_evaluators_for_task(task)

    scores = {}
    feedback = {}
    results = []

    print(f"Running {len(evaluators)} evaluators...")

    for evaluator in evaluators:
        print(f"  - {evaluator}...", end=" ", flush=True)
        result = run_evaluator(evaluator, task, output, data_dir)
        scores[evaluator] = result.score
        feedback[evaluator] = result.feedback
        results.append(result)
        print(f"{result.score:.2f}")

    consensus, variance = compute_consensus(scores)
    decision = make_decision(consensus, variance)

    print(f"\nConsensus: {consensus:.2f} (variance: {variance:.4f})")
    print(f"Decision: {decision}")

    return EvaluationResult(
        scores=scores,
        feedback=feedback,
        consensus=consensus,
        variance=variance,
        decision=decision,
        evaluator_results=results
    )


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python evaluate.py <data_dir> <output_file>")
        print("       Evaluates the content of output_file")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    # Create a mock task for testing
    task = OrgTask(
        id="test-task",
        title="Test Evaluation",
        state="WORKING",
        tags=["AI", "content"],
        properties={},
        file_path=Path("test.org"),
        line_number=1,
        heading_level=1,
        body="Test task for evaluation"
    )

    output = output_file.read_text()

    result = evaluate_output(task, output, data_dir)

    print("\n" + "=" * 40)
    print("Evaluation Complete")
    print("=" * 40)
    print(f"Consensus Score: {result.consensus}")
    print(f"Decision: {result.decision}")
    print("\nIndividual Scores:")
    for evaluator, score in result.scores.items():
        print(f"  {evaluator}: {score:.2f}")
