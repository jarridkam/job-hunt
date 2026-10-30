#!/bin/bash
# Ship code from this PC to the server and (re)start it. Run from the project folder in Git Bash:
#   deploy/deploy.sh root@<server-ip>            code only (Hetzner)
#   deploy/deploy.sh ubuntu@<server-ip>          code only (Oracle Cloud: logs in as ubuntu, uses sudo)
#   add --data to also copy data/ (first move; overwrites the server's data!)
set -euo pipefail
HOST="${1:?usage: deploy/deploy.sh root@<server-ip>|ubuntu@<server-ip> [--data]}"
KEY="${JOBHUNT_SSH_KEY:-$HOME/.ssh/jobhunt_hetzner}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new"
case "$HOST" in root@*) S="" ;; *) S="sudo" ;; esac   # S runs server commands as root when logged in as ubuntu
cd "$(dirname "$0")/.."

tar czf - --exclude=.venv --exclude=data --exclude='__pycache__' --exclude=deploy/.env --exclude=.git --exclude=.claude \
  --exclude=reports --exclude=research_notes --exclude='*.log' --exclude='.env*' --exclude='*.pem' --exclude='*.key' . \
  | $SSH "$HOST" "$S mkdir -p /opt/jobhunt/app && $S tar xzf - --no-same-owner -C /opt/jobhunt/app"

if [ "${2:-}" = "--data" ]; then
  echo "Copying data (database, uploads, screenshots; not the PC browser profile)..."
  $SSH "$HOST" "cd /opt/jobhunt/app/deploy && ($S docker compose stop app 2>/dev/null || true)"
  # Consistent snapshot of the live database (safe even while jobhunt runs here), plus uploads/screenshots.
  SNAP=$(mktemp -d)
  .venv/Scripts/python.exe -c "import sqlite3,sys; s=sqlite3.connect('data/jobhunt.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" "$SNAP/jobhunt.db"
  cp -r data/uploads data/screenshots "$SNAP/"
  tar czf - -C "$SNAP" . | $SSH "$HOST" \
    "$S rm -rf /opt/jobhunt/data.new && $S mkdir /opt/jobhunt/data.new && $S tar xzf - --no-same-owner -C /opt/jobhunt/data.new \
     && $S rm -rf /opt/jobhunt/data && $S mv /opt/jobhunt/data.new /opt/jobhunt/data && $S mkdir -p /opt/jobhunt/data/browser \
     && $S chown -R 1001:1001 /opt/jobhunt/data"
  rm -rf "$SNAP"
fi

$SSH "$HOST" "cd /opt/jobhunt/app/deploy && $S docker compose up -d --build && $S docker image prune -f >/dev/null && $S docker compose ps"
