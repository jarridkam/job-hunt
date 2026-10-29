#!/bin/bash
# One-time setup of a fresh Ubuntu 24.04 Hetzner server. Run as root:  bash server-setup.sh <site>
# <site> is the web address, e.g. 203-0-113-7.sslip.io (works with no domain) or jobs.example.com.
set -euo pipefail
SITE="${1:?usage: server-setup.sh <site>}"

# Updates, firewall, brute-force protection, automatic security updates
apt-get update && apt-get -y upgrade
apt-get install -y ufw fail2ban unattended-upgrades ca-certificates curl sqlite3
dpkg-reconfigure -f noninteractive unattended-upgrades
ufw default deny incoming && ufw default allow outgoing
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
systemctl enable --now fail2ban

# SSH: keys only (the key you added when creating the server)
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

# Docker
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi

# App folders. The encryption key lives in /etc/jobhunt, root-only, away from the data and its backups.
mkdir -p /opt/jobhunt/app /opt/jobhunt/data /opt/jobhunt/backups /etc/jobhunt
chown -R 1001:1001 /opt/jobhunt/data          # pwuser inside the container
if [ ! -f /etc/jobhunt/secret.env ]; then
  key=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
  printf 'JOBHUNT_SECRET_KEY=%s\n' "$key" > /etc/jobhunt/secret.env
fi
chmod 700 /etc/jobhunt && chmod 600 /etc/jobhunt/secret.env
printf 'SITE=%s\nTZ=America/Los_Angeles\n' "$SITE" > /opt/jobhunt/app/deploy/.env 2>/dev/null || {
  mkdir -p /opt/jobhunt/app/deploy && printf 'SITE=%s\nTZ=America/Los_Angeles\n' "$SITE" > /opt/jobhunt/app/deploy/.env; }

# Nightly database snapshot at 03:30, keep 14 days
cat > /etc/cron.d/jobhunt-backup <<'CRON'
30 3 * * * root sqlite3 /opt/jobhunt/data/jobhunt.db ".backup '/opt/jobhunt/backups/jobhunt-$(date +\%F).db'" && find /opt/jobhunt/backups -name 'jobhunt-*.db' -mtime +14 -delete
CRON

echo
echo "Server ready. Encryption key: /etc/jobhunt/secret.env  (copy it somewhere safe: without it, saved API keys can't be read)"
