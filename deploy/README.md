# Running jobhunt on a server

jobhunt runs in Docker behind Caddy (automatic HTTPS). The same files work on two kinds of server:

| | Oracle Cloud "Always Free" | Hetzner |
|---|---|---|
| Cost | $0 (inside the free limits) | about $12-14 a month with backups |
| Chip | ARM (Ampere A1) | x86 |
| Log in as | `ubuntu` (scripts use `sudo`) | `root` |
| Firewall | Oracle's iptables + the VCN security list | ufw |

Your data, resumes and settings stay in `/opt/jobhunt/data` on the server. The key that encrypts saved
passwords and API keys lives in `/etc/jobhunt/secret.env`, apart from the data and its backups.

## Oracle Cloud (free)

### 1. Account
Sign up at **cloud.oracle.com** (Free Tier). Oracle checks a card but doesn't charge for Always Free resources.
Pick a **home region** near you (for example US West, Phoenix or San Jose). It can't be changed later, and free
servers can only be made in it.

### 2. The server
Menu → **Compute → Instances → Create instance**.

- **Name:** `jobhunt`
- **Image:** Change image → **Canonical Ubuntu 24.04** (not "Minimal").
- **Shape:** Change shape → **Ampere** → `VM.Standard.A1.Flex`, **2 OCPUs, 12 GB memory**.
  (Up to 4 OCPUs / 24 GB is free in total; 2/12 is plenty and leaves room.)
- **Networking:** keep "Create new virtual cloud network" and **Assign a public IPv4 address**.
- **SSH keys:** **Paste public keys** and paste the `jobhunt-deploy` key (the contents of `~/.ssh/jobhunt_hetzner.pub`).
- **Boot volume:** default 50 GB is fine (up to 200 GB is free).

Click **Create**. If it says *Out of capacity*, try another availability domain in the same screen, or try
again later: free ARM servers run out at busy times.

### 3. Open ports 80 and 443
Instance page → **Primary VNIC → Subnet** → **Security Lists** → the default list → **Add Ingress Rules**:

- Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port **80**
- Source CIDR `0.0.0.0/0`, IP protocol TCP, destination port **443**

(`server-setup.sh` opens the same ports in the server's own firewall.)

### 4. Keep it from being reclaimed
Oracle may stop Always Free servers that look idle for a week. jobhunt is light most of the time, so the safest
fix is to **upgrade the account to Pay As You Go** (Billing → Upgrade). Always Free servers stay free and are
no longer reclaimed. Add a **budget alert of $1** (Billing → Budgets) so you hear about any charge at all.

### 5. Set it up (from this PC, in Git Bash)
Replace `IP` with the server's public IP, and `IP-WITH-DASHES` with the same address using dashes (`1-2-3-4`):

```bash
scp -i ~/.ssh/jobhunt_hetzner deploy/server-setup.sh ubuntu@IP:
ssh -i ~/.ssh/jobhunt_hetzner ubuntu@IP sudo bash server-setup.sh IP-WITH-DASHES.sslip.io
deploy/deploy.sh ubuntu@IP --data
```

The first deploy builds the image on the server (a few minutes). Then open `https://IP-WITH-DASHES.sslip.io`.
Save the encryption key somewhere safe: `ssh -i ~/.ssh/jobhunt_hetzner ubuntu@IP sudo cat /etc/jobhunt/secret.env`.

Later updates: `deploy/deploy.sh ubuntu@IP` (code only; your data on the server is kept).

## Hetzner

Create an Ubuntu 24.04 server with the `jobhunt-deploy` SSH key and backups on, then:

```bash
scp -i ~/.ssh/jobhunt_hetzner deploy/server-setup.sh root@IP:
ssh -i ~/.ssh/jobhunt_hetzner root@IP bash server-setup.sh IP-WITH-DASHES.sslip.io
deploy/deploy.sh root@IP --data
```

## After moving

- Log in, check your data, and try **Take over** on an application so the browser view works from your phone.
- On your phone, open the site and choose **Add to Home Screen**.
- Turn off the old link to the PC (Tailscale Funnel), and stop running jobhunt on the PC so two copies don't
  both check your inbox and apply.
