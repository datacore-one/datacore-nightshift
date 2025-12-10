# Nightshift Module

Autonomous AI task execution system with quality gates and continuous learning.

## Purpose

Nightshift processes `:AI:` tagged tasks autonomously, applying multi-perspective evaluation before delivering results. Works locally or on a server with identical user experience.

## Key Concepts

- **Queue Optimizer**: Prioritizes tasks by impact, effort, urgency
- **Context Enhancer**: Builds rich context from knowledge base before execution
- **Evaluation Panel**: 6 core evaluators + domain experts review every output
- **Learning Extractor**: Captures patterns and corrections for improvement

## Core Evaluators

| Persona | Focus |
|---------|-------|
| User | Does it solve my problem? |
| Critic | What's wrong/missing? |
| CEO | Strategic value |
| CTO | Technical quality |
| COO | Operational fit |
| Archivist | Was KB used well? |

## Task States

- `TODO` → `NEXT` → `WORKING` → `DONE`/`REVIEW`/`FAILED`

## Output Location

All outputs go to `[space]/0-inbox/nightshift-{id}-{type}.md`

## Commands

- `/tomorrow` - Queue tasks for overnight execution
- `/today` - Shows nightshift results
- `/nightshift-status` - Check queue and recent executions

## Settings

```yaml
nightshift:
  enabled: true
  quality_threshold: 0.80
  max_retries: 2
  evaluators_core: [user, critic, ceo, cto, coo, archivist]
```

## Git Sync Protocol

Server and local both work on `main` branch:
1. Pull before operations
2. Claim tasks via commit + push
3. Commit prefix: `nightshift:`

## Related

- DIP-0011: Full specification
- DIP-0009: GTD task states
- DIP-0004: Knowledge database (datacortex)
