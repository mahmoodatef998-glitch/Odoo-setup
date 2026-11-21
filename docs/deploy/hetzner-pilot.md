# Pilot server on Hetzner — how it is built and run

Approved by the user on 2026-11-21 ("يلا عاوز ابدا اشتغل علي سيرفر وارفع الموقع علي سيرفر").
The server address, passwords and the domain live only on the server (`/opt/odoo4u/.env`,
`/opt/odoo4u/config/odoo.conf`, both `chmod 600`) and in the owner's Hetzner account, never here
(this repository is public).

## Server
- Hetzner Cloud, project "4U Odoo", server `4u-odoo-pilot`: x86, 4 vCPU, 8 GB RAM, Ubuntu 24.04,
  Falkenstein. Hetzner **Backups on** (a daily image of the whole server, kept 7).
- Hetzner Firewall `4u-odoo-fw`: inbound TCP 22, 80, 443 and ICMP only.
- SSH: key only (`/etc/ssh/sshd_config.d/10-4u-hardening.conf`), the key is on the owner's PC
  (`~/.ssh/id_ed25519_4u_hetzner`). fail2ban on sshd. Daily security updates (unattended-upgrades,
  no automatic reboot). 4 GB swap. Time zone Asia/Dubai.
- Docker Engine + Compose plugin from Docker's apt repo; PowerShell 7 from Microsoft's repo, so
  `scripts/*.ps1` run unchanged. Docker logs rotate (20 MB x 5).

## The application (`/opt/odoo4u`, a clone of this repository with its OCA submodules)
- `.env`: `DB_PASSWORD` (random), `COMPOSE_FILE=compose.yaml:compose.prod.yaml`, `ODOO_DOMAIN`.
- `config/odoo.conf` from `config/odoo.prod.conf.example` with a random `admin_passwd`; owned by
  the container's odoo user (uid 100), `chmod 600`.
- `compose.prod.yaml` on top of `compose.yaml`: restart always, no Mailpit, Caddy in front with
  HTTPS (Let's Encrypt, renewed by itself). Odoo itself listens on 127.0.0.1 only.
- One database, `odoo4u`, built with `scripts/create-db.ps1` (no demo data, no test users), no
  Database Manager on the internet (`list_db = False`, `dbfilter = ^odoo4u$`).

- Settings in the database (not in Git, set once on the server):
  - `report.url = http://localhost:8069`, so wkhtmltopdf fetches the report CSS and logo from
    Odoo inside the container, not through the internet.
  - Company logo and report colors (primary #1A1A1A, secondary #8C7000, a readable dark gold of
    the logo's #FFDE59); the logo file is kept in `private/branding/` (git-ignored).
  - No free sign-up from the login page: `x4u_roles` 18.0.1.0.9 sets
    `auth_signup.invitation_scope = b2b` (Odoo's `auth_signup` opens b2c when it installs).

## Every day
- 02:30 `deploy/backup-daily.sh` (root crontab): `scripts/backup.ps1` → `/opt/odoo4u/backups`,
  kept 14 days. Plus Hetzner's daily server image.

## Common jobs (on the server, `cd /opt/odoo4u`)
```bash
docker compose ps
docker compose logs -f --tail 100 web
# Update to the latest main (after a backup):
deploy/backup-daily.sh && git pull --recurse-submodules && docker compose build web \
  && docker compose stop web && docker compose run --rm -T web odoo -d odoo4u -u <modules> --stop-after-init \
  && docker compose up -d
# A user's forgotten password (the owner types the new one):
pwsh scripts/reset-password.ps1 -Database odoo4u -Login <login>
# Change the domain: edit ODOO_DOMAIN in .env, then
docker compose up -d caddy
```

## Still to do
- The real outgoing email (SMTP of the company mailbox): until then Odoo sends nothing.
- The company subdomain instead of the temporary address (an A record to the server's IPv4).
- A copy of the nightly backup outside Hetzner (e.g. a Hetzner Storage Box or the owner's PC).
