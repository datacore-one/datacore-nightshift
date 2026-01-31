---
name: nightshift-status
description: Check nightshift queue, recent executions, server status, and items needing review
user-invocable: true
---

# Nightshift Status

!`python3 -c "
import yaml, os
state_file = os.path.expanduser('~/Data/.datacore/state/nightshift/analytics.yaml')
if os.path.exists(state_file):
    with open(state_file) as f: data = yaml.safe_load(f) or {}
    print(f'Last run: {data.get(\"last_run\", \"never\")}')
    print(f'Total executions: {data.get(\"total_executions\", 0)}')
    print(f'Pending review: {data.get(\"pending_review\", 0)}')
else:
    print('No analytics file found')
" 2>/dev/null || echo "Analytics unavailable"`

## Instructions

Follow the full workflow in `~/Data/.datacore/modules/nightshift/commands/nightshift-status.md`.

Show:
1. **Queue** - Count :AI: tagged tasks across all `*/org/next_actions.org`
2. **Recent executions** - Last 5 nightshift runs with status
3. **Pending review** - Items with NIGHTSHIFT_STATUS: review
4. **Server status** - Whether nightshift server is configured/running

Display as formatted dashboard. Offer follow-up actions (process now, review items, clear queue).
