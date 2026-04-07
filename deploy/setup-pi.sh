#!/usr/bin/env bash
# TraderBot - Raspberry Pi setup script
# Run as your normal user (not root), it will use sudo where needed.
#
# Usage:
#   1. Copy the TraderBot folder to your Pi (scp, git clone, USB stick)
#   2. cd TraderBot/deploy
#   3. chmod +x setup-pi.sh
#   4. ./setup-pi.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="$(whoami)"

echo "=== TraderBot Raspberry Pi Setup ==="
echo "Project dir : $PROJECT_DIR"
echo "User        : $SERVICE_USER"
echo ""

# --- 1. System packages ---
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git

# --- 2. Python venv ---
echo "[2/5] Creating Python virtual environment..."
cd "$PROJECT_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
pip install python-dotenv -q
echo "       Python $(python3 --version)"

# --- 3. .env file ---
echo "[3/5] Checking .env..."
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "       No .env found — creating from template."
    echo "       EDIT THIS FILE with your Alpaca keys!"
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "  >>> nano $PROJECT_DIR/.env <<<"
    echo ""
else
    echo "       .env exists, skipping."
fi

# --- 4. Systemd service for dashboard ---
echo "[4/5] Installing systemd services..."

sudo tee /etc/systemd/system/traderbot-dashboard.service > /dev/null <<EOF
[Unit]
Description=TraderBot Web Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python main.py serve --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10
EnvironmentFile=$PROJECT_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable traderbot-dashboard.service
echo "       Dashboard service installed (port 8000)"

# --- 5. Cron jobs ---
echo "[5/5] Installing cron schedule..."

# Remove old traderbot cron entries if any
crontab -l 2>/dev/null | grep -v 'traderbot' | crontab - 2>/dev/null || true

# US market opens 15:30 CET, closes 22:00 CET
# run      = daily rebalance at 16:00 CET (30 min after open)
# snapshot = daily portfolio log at 22:30 CET (after close)
# guard    = circuit breaker every 30 min during market hours
CRON_LINES=$(cat <<'CRON'
# --- TraderBot scheduled jobs ---
0 16 * * 1-5   cd PROJECT_DIR && .venv/bin/python main.py run      >> logs/cron.log 2>&1
30 22 * * 1-5   cd PROJECT_DIR && .venv/bin/python main.py snapshot >> logs/cron.log 2>&1
*/30 15-22 * * 1-5 cd PROJECT_DIR && .venv/bin/python main.py guard >> logs/cron.log 2>&1
CRON
)

# Replace placeholder with actual path
CRON_LINES="${CRON_LINES//PROJECT_DIR/$PROJECT_DIR}"

(crontab -l 2>/dev/null; echo "$CRON_LINES") | crontab -
echo "       Cron jobs installed:"
echo "         - run      : Mon-Fri 16:00 CET"
echo "         - snapshot : Mon-Fri 22:30 CET"
echo "         - guard    : Mon-Fri every 30 min (15:00-22:00 CET)"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit your API keys:  nano $PROJECT_DIR/.env"
echo "  2. Start dashboard:     sudo systemctl start traderbot-dashboard"
echo "  3. Open in browser:     http://<pi-ip>:8000"
echo "  4. Test a run:          cd $PROJECT_DIR && .venv/bin/python main.py status"
echo ""
