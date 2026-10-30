#!/bin/bash
# Ship code from this PC to the server and (re)start it. Run from the project folder in Git Bash:
#   deploy/deploy.sh root@<server-ip>            code only
#   deploy/deploy.sh root@<server-ip> --data     also copy data/ (first move; overwrites the server's data!)
set -euo pipefail
HOST="${1:?usage: deploy/deploy.sh root@<server-ip> [--data]}"
KEY="${JOBHUNT_SSH_KEY:-$HOME/.ssh/jobhunt_hetzner}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new"
cd "$(dirname "$0")/.."

tar czf - --exclude=.venv --exclude=data --exclude='__pycache__' --exclude=deploy/.env --exclude=.git --exclude=.claude \
  --exclude=reports --exclude=research_notes --exclude='*.log' --exclude='.env*' --exclude='*.pem' --exclude='*.key' . \
  | $SSH "$HOST" 'mkdir -p /opt/jobhunt/app && tar xzf - -C /opt/jobhunt/app'

if [ "${2:-}" = "--data" ]; then
  echo "Copying data (database, uploads, screenshots; not the PC browser profile)..."
  $SSH "$HOST" 'cd /opt/jobhunt/app/deploy && docker compose stop app 2>/dev/null || true'
  # Consistent snapshot of the live database (safe even while jobhunt runs here), plus uploads/screenshots.
  SNAP=$(mktemp -d)
  .venv/Scripts/python.exe -c "import sqlite3,sys; s=sqlite3.connect('data/jobhunt.db'); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" "$SNAP/jobhunt.db"
  cp -r data/uploads data/screenshots "$SNAP/"
  tar czf - -C "$SNAP" . | $SSH "$HOST" \
    'rm -rf /opt/jobhunt/data.new && mkdir /opt/jobhunt/data.new && tar xzf - -C /opt/jobhunt/data.new \
     && rm -rf /opt/jobhunt/data && mv /opt/jobhunt/data.new /opt/jobhunt/data && mkdir -p /opt/jobhunt/data/browser \
     && chown -R 1001:1001 /opt/jobhunt/data'
  rm -rf "$SNAP"
fi

$SSH "$HOST" 'cd /opt/jobhunt/app/deploy && docker compose up -d --build && docker image prune -f >/dev/null && docker compose ps'
