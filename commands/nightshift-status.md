# Nightshift Status Command

## Command Context

### When to Reference Nightshift Module

**Always reference when:**
- Checking queue state
- Displaying execution history
- Showing server status
- Identifying items needing review

**Key decisions the module informs:**
- Where to find :AI: tagged tasks
- Analytics file location
- Server configuration
- Quality thresholds for display

### Quick Reference

| Question | Answer |
|----------|--------|
| Queue source? | `*/org/next_actions.org` |
| Analytics file? | `.datacore/state/nightshift/analytics.yaml` |
| Review state? | Tasks with NIGHTSHIFT_STATUS: review |
| Server config? | `.datacore/settings.local.yaml` |

### Agents This Command Invokes

| Agent | Purpose |
|-------|---------|
| (none) | Status display only, no agents |

### Integration Points

- **org files** - Task queue source
- **state/nightshift/** - Analytics data
- **settings.local.yaml** - Server configuration
- **/today** - Nightshift hook integration

---

Check the current state of nightshift: queue, recent executions, and server status.

## What to Show

### 1. Current Queue

Check `org/next_actions.org` across all spaces for `:AI:` tagged tasks:

```
NIGHTSHIFT QUEUE
────────────────
Tasks pending: 3

| # | Space | Task | Type | Priority |
|---|-------|------|------|----------|
| 1 | teamspace | Research competitor X | :AI:research: | A |
| 2 | teamspace | Draft blog post | :AI:content: | B |
| 3 | personal | Organize reading list | :AI: | C |

Estimated: ~45 min, $0.35
```

### 2. Recent Executions

Check `.datacore/state/nightshift/analytics.yaml` for recent runs:

```
RECENT EXECUTIONS (last 7 days)
───────────────────────────────
| Date | Tasks | Completed | Review | Avg Score | Cost |
|------|-------|-----------|--------|-----------|------|
| 12-10 | 5 | 4 | 1 | 0.84 | $0.48 |
| 12-09 | 3 | 3 | 0 | 0.88 | $0.32 |
| 12-08 | 4 | 3 | 1 | 0.79 | $0.41 |

Total: 12 tasks, 10 completed, 2 review, $1.21
```

### 3. Server Status

If server is configured, check status:

```
SERVER STATUS
─────────────
Personal server: nightshift.example.com
  Status: ONLINE
  Last run: 2025-12-10 02:15
  Next scheduled: 2025-12-11 00:00

Team server: nightshift.team.example.com
  Status: ONLINE
  Last run: 2025-12-10 02:30
  Spaces: 1-teamspace only
```

If no server configured:
```
SERVER STATUS
─────────────
No server configured. Running locally only.
Configure in .datacore/settings.local.yaml
```

### 4. Active Execution

If nightshift is currently running:

```
ACTIVE EXECUTION
────────────────
Started: 2025-12-10 02:15
Executor: server:personal
Current task: Research competitor X (3/5)
Duration: 12 min
```

### 5. Items Needing Review

Check for tasks in REVIEW state:

```
NEEDS REVIEW
────────────
1. Blog post draft (score: 0.68)
   Reason: Evaluator disagreement on tone
   Output: 1-teamspace/0-inbox/nightshift-003-content.md
```

## Conversational Flow

If user just runs `/nightshift-status`:
1. Show queue summary
2. Show recent executions summary
3. Show server status
4. Flag anything needing attention

Ask if they want:
1. Detailed queue analysis
2. Execution history
3. Server logs
4. Analytics deep dive

## Data Sources

- Queue: `*/org/next_actions.org` (grep for :AI:)
- Analytics: `.datacore/state/nightshift/analytics.yaml`
- Server config: `.datacore/settings.local.yaml`
- Pending review: Tasks with state REVIEW

## Error Handling

**No :AI: tasks found:**
```
NIGHTSHIFT QUEUE
----------------
No tasks in queue.

To add tasks:
  1. Add :AI: tag to any TODO in org/next_actions.org
  2. Specialized: :AI:research:, :AI:content:, :AI:data:
```

**Analytics file missing:**
```
No execution history found.

This is normal for new installations.
History will appear after first nightshift run.
```

**Server unreachable:**
```
SERVER STATUS
-------------
Cannot reach nightshift.example.com

Check:
  - Server is running: ssh user@server "systemctl status nightshift"
  - Network connectivity
  - Server config in .datacore/settings.local.yaml
```

## Settings Reference

User can configure in `~/.datacore/settings.local.yaml`:

```yaml
nightshift:
  enabled: true                    # Enable/disable nightshift
  quality_threshold: 0.80          # Minimum score for auto-approval
  max_retries: 2                   # Revision attempts before human review
  context_quality_threshold: 0.60  # Minimum context quality to proceed
  budget_daily_usd: 0              # Daily cost limit (0 = unlimited)
  evaluators_core:                 # Core evaluators that always run
    - user
    - critic
    - ceo
    - cto
    - coo
    - archivist
```

## Your Boundaries

**YOU CAN:**
- Read org files to find :AI: tagged tasks
- Read analytics and state files
- Check server status if configured
- Display formatted status information
- Offer to show detailed views

**YOU CANNOT:**
- Modify any org files
- Execute tasks (that's the orchestrator's job)
- Change nightshift settings
- Delete analytics or state files

**YOU MUST:**
- Show helpful messages when data is missing
- Offer follow-up options after displaying status
- Respect user's configured preferences
