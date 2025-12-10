# Nightshift Module

> *"Tag tasks before bed. Wake up to completed work."*

Autonomous AI task execution system with quality gates, multi-persona evaluation, and continuous learning.

## Overview

Nightshift processes `:AI:` tagged tasks autonomously, applying a rigorous evaluation pipeline before delivering results. Works locally or on a server with identical user experience.

## Features

- **Queue Optimization** - Prioritizes tasks by impact, effort, urgency
- **Context Enhancement** - Builds rich context from knowledge base (datacortex RAG, wiki-links, patterns)
- **Multi-Persona Evaluation** - 6 core evaluators + domain experts review every output
- **Quality Gates** - Only delivers work meeting quality threshold (default 0.80)
- **Continuous Learning** - Extracts patterns from success, logs corrections from failures
- **Platform-Agnostic Scheduling** - Cron, launchd, systemd, or in-process daemon

## Quick Start

### 1. Tag Tasks for AI

In your `org/next_actions.org`:

```org
* TODO Research competitor pricing :AI:research:
* TODO Draft blog post about data sovereignty :AI:content:
* TODO Generate Q4 metrics report :AI:data:
```

### 2. Queue for Overnight

Run `/tomorrow` to:
- See queue optimization preview
- Confirm tasks for execution
- Push to server (if configured)

### 3. Get Results

Run `/today` in the morning to see:
- Completed work with quality scores
- Items needing review
- Evaluator feedback

## Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  1. QUEUE OPTIMIZER                                             │
│     Analyze :AI: tasks, prioritize by impact/effort/urgency     │
├─────────────────────────────────────────────────────────────────┤
│  2. CONTEXT ENHANCER                                            │
│     RAG search, wiki-links, patterns, corrections, journals     │
├─────────────────────────────────────────────────────────────────┤
│  3. EXECUTION ENGINE                                            │
│     Specialized agents + self-reflection loop                   │
├─────────────────────────────────────────────────────────────────┤
│  4. EVALUATION PANEL                                            │
│     Core: User, Critic, CEO, CTO, COO, Archivist                │
│     Domain: Twain, Bezos, Popper, etc. (by task type)           │
├─────────────────────────────────────────────────────────────────┤
│  5. LEARNING EXTRACTOR                                          │
│     Patterns from success, corrections from failures            │
└─────────────────────────────────────────────────────────────────┘
```

## Evaluators

### Core (Always Run)

| Persona | Focus |
|---------|-------|
| **User** | Does it solve my problem? |
| **Critic** | What's wrong? What's missing? |
| **CEO** | Strategic value, ROI |
| **CTO** | Technical quality, best practices |
| **COO** | Operational feasibility |
| **Archivist** | Was knowledge base used well? |

### Domain (By Task Type)

| Persona | Focus | Invoked For |
|---------|-------|-------------|
| Mark Twain | Clarity, brevity | `:AI:content:` |
| Bezos | Customer obsession | Strategy tasks |
| Popper | Falsifiability | `:AI:research:` |
| Tufte | Data clarity | `:AI:data:` |

## Configuration

### Settings

In `.datacore/settings.local.yaml`:

```yaml
nightshift:
  enabled: true
  quality_threshold: 0.80
  max_retries: 2

  servers:
    personal:
      url: "nightshift.example.com"
      ssh_key: "~/.ssh/nightshift"
      spaces: ["*"]  # Can run all spaces
```

### Schedules

In `.datacore/modules/nightshift/schedules.yaml`:

```yaml
schedules:
  - id: nightly-execution
    schedule: "0 0 * * *"  # Midnight
    command: "nightshift run"
    enabled: true
```

## Output

Results go to `[space]/0-inbox/nightshift-{id}-{type}.md`:

```markdown
---
nightshift_id: exec-2025-12-10-001
task: "Research competitor X"
score: 0.85
status: approved
---

# Research: Competitor X Analysis

[Output content]

---

## Evaluator Feedback

> **CEO**: Good strategic relevance.
> **Critic**: Could use more recent data.
```

## Task States

| State | Meaning |
|-------|---------|
| `TODO` | Not queued |
| `NEXT` | Queued for nightshift |
| `WORKING` | Currently executing |
| `DONE` | Completed and approved |
| `REVIEW` | Needs human review |
| `FAILED` | Execution failed |

## Commands

- `/tomorrow` - Queue tasks, preview execution, trigger server
- `/today` - Show nightshift results
- `/nightshift-status` - Check queue and server status

## Server Setup

Nightshift can run:
- **Locally** - When laptop is awake
- **On Server** - 24/7 execution on DigitalOcean/etc.

### Server Requirements

- Git access to Data repo (deploy key)
- Claude CLI or API access
- Cron or systemd for scheduling

### Space Isolation

- Personal server: Can run all spaces
- Team server: Only runs its space (e.g., datafund server only runs 1-datafund)

## Git Protocol

Single branch (main), atomic operations:

1. Pull before any operation
2. Claim tasks via commit + push
3. Commit messages: `nightshift: claim/complete/fail {task_id}`

## Related

- [DIP-0011](../../dips/DIP-0011-nightshift-module.md) - Full specification
- [DIP-0009](../../dips/DIP-0009-gtd-specification.md) - GTD task states
- [DIP-0004](../../dips/DIP-0004-knowledge-database.md) - Knowledge database

## License

Part of Datacore. See root LICENSE.
