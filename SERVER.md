# Nightshift Server Operations

Quick reference for server administration.

## Server Details

| Property | Value |
|----------|-------|
| IP | `YOUR_SERVER_IP` |
| User | `deploy` |
| Data path | `/home/deploy/Data` |
| Config | `/home/deploy/config/nightshift.env` |

## SSH Access

```bash
# Interactive session
ssh deploy@YOUR_SERVER_IP

# Quick command
ssh deploy@YOUR_SERVER_IP 'command here'
```

## Systemd Timers (Schedules)

| Timer | Schedule | Purpose |
|-------|----------|---------|
| `nightshift-overnight.timer` | 00:00, 06:00 UTC | Execute :AI: tasks |
| `nightshift-today.timer` | 07:00 UTC | Generate /today briefing |

### Check Timer Status

```bash
# SSH to server and check
ssh deploy@YOUR_SERVER_IP 'systemctl list-timers | grep nightshift'

# Or use the CLI
nightshift scheduler status
```

### View Recent Logs

```bash
# Overnight execution logs
ssh deploy@YOUR_SERVER_IP 'journalctl -u nightshift-overnight.service --since today'

# Today briefing logs
ssh deploy@YOUR_SERVER_IP 'journalctl -u nightshift-today.service --since today'

# Follow logs in real-time
ssh deploy@YOUR_SERVER_IP 'journalctl -u nightshift-overnight.service -f'
```

### Manual Trigger

```bash
# Run overnight tasks now
ssh deploy@YOUR_SERVER_IP 'sudo systemctl start nightshift-overnight.service'

# Run /today briefing now
ssh deploy@YOUR_SERVER_IP 'sudo systemctl start nightshift-today.service'
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

Server uses separate repos:
- Main datacore repo: `/home/deploy/Data`
- Datafund space: `/home/deploy/Data/1-datafund` (separate repo)

```bash
# Check sync status on server
ssh deploy@YOUR_SERVER_IP 'cd ~/Data && git status'
ssh deploy@YOUR_SERVER_IP 'cd ~/Data/1-datafund && git status'

# Manual pull
ssh deploy@YOUR_SERVER_IP 'cd ~/Data && git pull'
ssh deploy@YOUR_SERVER_IP 'cd ~/Data/1-datafund && git pull'
```

## Troubleshooting

### Tasks Not Executing

1. Check timers are active:
   ```bash
   ssh deploy@YOUR_SERVER_IP 'systemctl list-timers | grep nightshift'
   ```

2. Check for errors in logs:
   ```bash
   ssh deploy@YOUR_SERVER_IP 'journalctl -u nightshift-overnight.service -n 50'
   ```

3. Check API key is set:
   ```bash
   ssh deploy@YOUR_SERVER_IP 'grep ANTHROPIC ~/config/nightshift.env'
   ```

4. Test manual run:
   ```bash
   ssh deploy@YOUR_SERVER_IP 'cd ~/Data && ./.datacore/modules/nightshift/nightshift status'
   ```

### Outputs Not Syncing to Local

1. Verify server committed and pushed:
   ```bash
   ssh deploy@YOUR_SERVER_IP 'cd ~/Data/1-datafund && git log --oneline -5'
   ```

2. Pull locally:
   ```bash
   cd ~/Data/1-datafund && git pull
   ```

3. Check repo architecture matches (local and server should both have 1-datafund as separate repo)

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
| Task outputs | `/home/deploy/Data/1-datafund/0-inbox/` |
| Logs | `journalctl -u nightshift-*` |

## Current Status

**Deployed (2025-12-13):**
- [x] Systemd timers installed and running
- [x] Scheduler CLI functional
- [x] Git access to private repos (datafund-space)
- [x] Environment configured (API key)

**Timers Active:**
- `nightshift-overnight.timer` - midnight + 6am UTC
- `nightshift-today.timer` - 7am UTC

## See Also

- [README.md](README.md) - Module overview
- [DIP-0011](../../dips/DIP-0011-nightshift-module.md) - Full specification
- [server/01-droplet-setup.sh](server/01-droplet-setup.sh) - Initial server setup
