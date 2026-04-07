# TraderBot - Raspberry Pi Deployment

## Requirements

- Raspberry Pi 5 (4GB) with Raspberry Pi OS Bookworm
- Python 3.11+ (included by default on Bookworm)
- Internet connection (for market data and Alpaca API)

## Quick install

```bash
# 1. Copy the project to your Pi
scp -r TraderBot/ pi@<pi-ip>:~/TraderBot
# Or clone via git:
# git clone <repo-url> ~/TraderBot

# 2. Run the setup script
cd ~/TraderBot/deploy
chmod +x setup-pi.sh
./setup-pi.sh

# 3. Fill in your Alpaca API keys
nano ~/TraderBot/.env
```

## What the setup script does

1. Installs Python and required system packages
2. Creates a virtual environment with all dependencies
3. Copies `.env.example` to `.env` (if it doesn't exist yet)
4. Installs a **systemd service** for the dashboard (auto-start on boot)
5. Configures **cron jobs** for automated trading

## Schedule (CET)

| Time          | Days     | Command    | Description                            |
|---------------|----------|------------|----------------------------------------|
| 16:00         | Mon-Fri  | `run`      | Daily rebalance (30 min after open)    |
| every 30 min  | Mon-Fri  | `guard`    | Circuit breaker check (15:00-22:00)    |
| 22:30         | Mon-Fri  | `snapshot` | Log portfolio value (after close)      |

## Useful commands

```bash
# Start/stop dashboard
sudo systemctl start traderbot-dashboard
sudo systemctl stop traderbot-dashboard
sudo systemctl status traderbot-dashboard

# View logs
tail -f ~/TraderBot/logs/traderbot.log    # bot log
tail -f ~/TraderBot/logs/cron.log         # cron log
journalctl -u traderbot-dashboard -f      # dashboard log

# Manual run
cd ~/TraderBot && .venv/bin/python main.py run

# Portfolio status
cd ~/TraderBot && .venv/bin/python main.py status

# View cron jobs
crontab -l
```

## Accessing the dashboard

After installation the dashboard is available at:

```
http://<pi-ip>:8000
```

Tip: assign a static IP to your Pi in your router so the address doesn't change.

## Set timezone

Make sure the Pi is set to CET/CEST so cron times are correct:

```bash
sudo timedatectl set-timezone Europe/Amsterdam
```
