# Nightshift Server Operations

Quick reference for server administration.

## Server Details

| Property | Value |
|----------|-------|
| IP | `your-server-ip` |
| User | `deploy` |
| Data path | `/home/deploy/Data` |
| Config | `/home/deploy/config/nightshift.env` |

## SSH Access

```bash
# Interactive session
ssh user@your-server-ip

# Quick command
ssh user@your-server-ip 'command here'
```

## Systemd Timers (Schedules)

| Timer | Schedule | Purpose |
|-------|----------|---------|
| `nightshift-overnight.timer` | 00:00, 06:00 UTC | Execute :AI: tasks |
| `nightshift-today.timer` | 07:00 UTC | Generate /today briefing |

### Check Timer Status

```bash
# SSH to server and check
ssh user@your-server-ip 'systemctl list-timers | grep nightshift'

# Or use the CLI
nightshift scheduler status
```

### View Recent Logs

```bash
# Overnight execution logs
ssh user@your-server-ip 'journalctl -u nightshift-overnight.service --since today'

# Today briefing logs
ssh user@your-server-ip 'journalctl -u nightshift-today.service --since today'

# Follow logs in real-time
ssh user@your-server-ip 'journalctl -u nightshift-overnight.service -f'
```

### Manual Trigger

```bash
# Run overnight tasks now
ssh user@your-server-ip 'sudo systemctl start nightshift-overnight.service'

# Run /today briefing now
ssh user@your-server-ip 'sudo systemctl start nightshift-today.service'
```

## Scheduler CLI

```bash
# Check installed schedules
nightshift scheduler status

# Install systemd timers (run on server)
nightshift scheduler install --backend=systemd

# Uninstall timers
nightshift scheduler uninstall --backend=systemd
```

## Git Sync

Server uses separate repos with different origins:

| Space | Origin | Notes |
|-------|--------|-------|
| Root (`.datacore/`) | GitHub (datacore-one/datacore) | System only |
| `0-personal/` | **This server** (self-hosted) | Private, no GitHub |
| `1-teamspace/` | GitHub (team-space) | Team collaboration |
| `2-projectspace/` | GitHub (project-space) | Team collaboration |

```bash
# Check sync status on server
ssh user@your-server-ip 'cd ~/Data && git status'
ssh user@your-server-ip 'cd ~/Data/0-personal && git status'  # Self-hosted origin
ssh user@your-server-ip 'cd ~/Data/1-teamspace && git status'

# Manual pull (0-personal pulls from local pushes, not GitHub)
ssh user@your-server-ip 'cd ~/Data && git pull'
ssh user@your-server-ip 'cd ~/Data/1-teamspace && git pull'

# 0-personal is origin ON this server - local machine pushes here
```

## GitHub CLI

`gh` is installed for creating issues, PRs, and GitHub API operations:

```bash
# Check auth status
ssh user@your-server-ip 'gh auth status'

# Example: Create issue from nightshift
ssh user@your-server-ip 'cd ~/Data/1-teamspace && gh issue create --title "..." --body "..."'
```

**Authenticated as:** `username` (SSH protocol)

## Troubleshooting

### Tasks Not Executing

1. Check timers are active:
   ```bash
   ssh user@your-server-ip 'systemctl list-timers | grep nightshift'
   ```

2. Check for errors in logs:
   ```bash
   ssh user@your-server-ip 'journalctl -u nightshift-overnight.service -n 50'
   ```

3. Check API key is set:
   ```bash
   ssh user@your-server-ip 'grep ANTHROPIC ~/config/nightshift.env'
   ```

4. Test manual run:
   ```bash
   ssh user@your-server-ip 'cd ~/Data && ./.datacore/modules/nightshift/nightshift status'
   ```

### Outputs Not Syncing to Local

1. Verify server committed and pushed:
   ```bash
   ssh user@your-server-ip 'cd ~/Data/1-teamspace && git log --oneline -5'
   ```

2. Pull locally:
   ```bash
   cd ~/Data/1-teamspace && git pull
   ```

3. Check repo architecture matches (local and server should both have 1-teamspace as separate repo)

### Rate Limits

If tasks fail due to rate limits:
- Check `journalctl` for "rate limit" errors
- Tasks will be retried on next cycle
- Consider reducing concurrent tasks in queue

## File Locations

| What | Server Path |
|------|-------------|
| Nightshift script | `/home/deploy/Data/.datacore/modules/nightshift/nightshift` |
| Service files | `/etc/systemd/system/nightshift-*.service` |
| Timer files | `/etc/systemd/system/nightshift-*.timer` |
| Environment | `/home/deploy/config/nightshift.env` |
| Personal outputs | `/home/deploy/Data/0-personal/0-inbox/` |
| Team outputs | `/home/deploy/Data/1-teamspace/0-inbox/` |
| Logs | `journalctl -u nightshift-*` |

## Current Status

**Deployed (2025-12-20):**
- [x] Systemd timers installed and running
- [x] Scheduler CLI functional
- [x] Git access to private repos (team-space)
- [x] Environment configured (API key)
- [x] GitHub CLI (`gh`) installed and authenticated
- [x] Personal space (0-personal) as self-hosted repo

**Timers Active:**
- `nightshift-overnight.timer` - midnight + 6am UTC
- `nightshift-today.timer` - 7am UTC

**Repository Architecture:**
- 0-personal: Server is origin (self-hosted, no GitHub)
- Team spaces: GitHub origins (1-teamspace, 2-projectspace)

## See Also

- [README.md](README.md) - Module overview
- [DIP-0011](../../dips/DIP-0011-nightshift-module.md) - Full specification
- [server/01-droplet-setup.sh](server/01-droplet-setup.sh) - Initial server setup
