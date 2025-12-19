# Nightshift Module

Autonomous AI task execution system with quality gates and continuous learning.

## Purpose

Nightshift processes `:AI:` tagged tasks autonomously, applying multi-perspective evaluation before delivering results. Works locally or on a server with identical user experience.

## Server Operations

### Connection

| Property | Value |
|----------|-------|
| IP | `209.38.195.208` |
| User | `gregor` |
| SSH | `ssh gregor@209.38.195.208` |
| Data path | `/home/gregor/Data` |
| Config | `/home/gregor/config/nightshift.env` |

### Systemd Timers

| Timer | Schedule (UTC) | Purpose |
|-------|----------------|---------|
| `nightshift-overnight.timer` | 00:00, 06:00 | Execute :AI: tasks |
| `nightshift-today.timer` | 07:00 | Generate /today briefing |

### Common Operations

```bash
# Check timer status
ssh gregor@209.38.195.208 'systemctl list-timers | grep nightshift'

# View recent logs
ssh gregor@209.38.195.208 'journalctl -u nightshift-overnight.service --since today'

# Manual trigger
ssh gregor@209.38.195.208 'sudo systemctl start nightshift-overnight.service'

# Check nightshift status
ssh gregor@209.38.195.208 'cd ~/Data && ./.datacore/modules/nightshift/nightshift status'
```

### Repo Architecture (Critical)

Server has SEPARATE repos (not nested):
- `/home/gregor/Data` - Main datacore repo
- `/home/gregor/Data/1-datafund` - Separate datafund-space repo (cloned independently)

This matches local architecture. If 1-datafund is part of main repo (gitignored), outputs won't sync.

```bash
# Verify repos are separate
ssh gregor@209.38.195.208 'cd ~/Data/1-datafund && git remote -v'
# Should show: github.com:datacore-one/datafund-space.git
```

## CLI Commands

```bash
# Check queue and status
nightshift status

# Run tasks now (local)
nightshift run

# Run specific command
nightshift run --command=/today

# Scheduler management
nightshift scheduler status
nightshift scheduler install --backend=systemd
nightshift scheduler uninstall --backend=systemd
```

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

## Troubleshooting

### Tasks Not Executing

1. Check timers: `ssh gregor@209.38.195.208 'systemctl list-timers | grep nightshift'`
2. Check logs: `ssh gregor@209.38.195.208 'journalctl -u nightshift-overnight.service -n 50'`
3. Check API key: `ssh gregor@209.38.195.208 'grep ANTHROPIC ~/config/nightshift.env'`

### Outputs Not Syncing

1. Verify server pushed: `ssh gregor@209.38.195.208 'cd ~/Data/1-datafund && git log --oneline -3'`
2. Pull locally: `cd ~/Data/1-datafund && git pull`
3. Verify 1-datafund is separate repo on server (not part of main repo)

### Rate Limits

Tasks fail with rate limit errors will retry on next cycle. Check logs for details.

## File Locations

| What | Path |
|------|------|
| CLI script | `.datacore/modules/nightshift/nightshift` |
| Agents | `.datacore/modules/nightshift/agents/` |
| Lib | `.datacore/modules/nightshift/lib/` |
| Server files | `.datacore/modules/nightshift/server/` |
| Systemd services | `/etc/systemd/system/nightshift-*.service` (on server) |

## Settings

In `.datacore/settings.yaml`:

```yaml
nightshift:
  enabled: true
  quality_threshold: 0.80
  max_retries: 2
  budget_daily_usd: 0
```

## Git Sync Protocol

Server and local both work on `main` branch:
1. Pull before operations
2. Claim tasks via commit + push (git-based locking)
3. Commit prefix: `nightshift:`

## Related

- [SERVER.md](SERVER.md) - Full server operations guide
- DIP-0011: Full specification
- DIP-0009: GTD task states
