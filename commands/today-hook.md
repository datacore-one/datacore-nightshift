# Nightshift Hook: /today Integration

## Command Context

### When to Reference Nightshift Module

**Always reference when:**
- Generating daily briefing section
- Parsing nightshift summary files
- Displaying review items

**Key decisions the module informs:**
- Summary file location pattern
- Frontmatter fields to extract
- Display thresholds

### Quick Reference

| Question | Answer |
|----------|--------|
| Summary location? | `[space]/0-inbox/nightshift-summary-*.md` |
| Key metrics? | total, approved, review, failed |
| Skip threshold? | No runs in 24h |
| Hook trigger? | Called by /today |

### Integration Points

- **/today** - Triggers this hook
- **0-inbox/** - Summary file location
- **nightshift-orchestrator** - Creates summaries

---

This hook adds nightshift results to the daily briefing.

## Trigger

Called by `/today` command when nightshift module is installed.

## Behavior

1. Find the most recent `nightshift-summary-*.md` file in each space's `0-inbox/`
2. Parse the summary for key metrics
3. Generate a condensed section for the daily briefing

## Section to Generate

```markdown
### Nightshift Results

**Last run**: [timestamp from summary] | **Duration**: [X]h [Y]m
**Tasks**: [total] ([approved] approved, [review] review, [failed] failed)

**Needs Review:**
- [ ] [Task title] (0.55) → [[nightshift-exec-...]]
- [ ] [Task title] (0.62) → [[nightshift-exec-...]]

**Ready to Process:**
- [Task title] (0.93) - high value
- [Task title] (0.91) - high value
- ... and N more

Full report: [[nightshift-summary-YYYY-MM-DD.md]]
```

## Implementation

To find and parse the latest summary:

```python
from pathlib import Path
from datetime import datetime
import yaml

def get_nightshift_summary(data_dir: Path, space: str) -> dict:
    """Get latest nightshift summary for a space."""
    inbox = data_dir / space / '0-inbox'
    if not inbox.exists():
        return None

    # Find most recent summary file
    summaries = sorted(inbox.glob('nightshift-summary-*.md'), reverse=True)
    if not summaries:
        return None

    summary_path = summaries[0]

    # Parse frontmatter
    content = summary_path.read_text()
    if content.startswith('---'):
        _, frontmatter, body = content.split('---', 2)
        meta = yaml.safe_load(frontmatter)
        return {
            'path': summary_path,
            'date': meta.get('date'),
            'total': meta.get('total_tasks', 0),
            'approved': meta.get('approved', 0),
            'review': meta.get('review', 0),
            'failed': meta.get('failed', 0),
        }

    return None
```

## Data Sources

- `[space]/0-inbox/nightshift-summary-*.md` - Summary reports
- Frontmatter contains: date, total_tasks, approved, review, failed

## Conditions

| Condition | Behavior |
|-----------|----------|
| No nightshift runs | Skip section entirely |
| Summary older than 24h | Show with "Last run: X days ago" warning |
| No review items | Skip "Needs Review" subsection |
| No approved items | Skip "Ready to Process" subsection |

## Example Output

```markdown
### Nightshift Results

**Last run**: 2025-12-12 03:00 UTC | **Duration**: 2h 15m
**Tasks**: 12 (8 approved, 3 review, 1 failed)

**Needs Review:**
- [ ] 6-month Verity roadmap (0.55) → [[nightshift-exec-2025-12-12-003245-task.md]]
- [ ] Data standardization research (0.62) → [[nightshift-exec-2025-12-12-004521-task.md]]

**Ready to Process:**
- Competitive landscape analysis (0.93) - high value
- Product roadmap draft (0.94) - high value
- ZK framework research (0.93)
- ... and 5 more

Full report: [[nightshift-summary-2025-12-12.md]]
```

## No Nightshift Output

If no nightshift has run recently:

```markdown
### Nightshift Results

No nightshift execution in past 24 hours.

Queue status: [X] tasks pending
Next scheduled: [time] UTC
```
