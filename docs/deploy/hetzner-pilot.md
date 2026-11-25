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

## Training database (2026-11-23)
- `odoo4u_training`: a copy of `odoo4u` (same users, passwords, look) + `scripts/training_data.py`
  (3 generators 100/250/500 kVA with Open/Canopy and AQT/Leroy-Somer variants, their parts,
  3 vendors, 3 customers, starting stock with serials, all "(Training)" / `TR-`). The navbar and
  the Home page say "Training" (`x4u_theme.environment_label`). The script refuses any database
  whose name does not end in `_training`.
- The login page lists both (`list_db = True`, `dbfilter = ^odoo4u(_training)?$`); Caddy blocks
  the Database Manager pages and `/xmlrpc`, `/jsonrpc` (deploy/Caddyfile).
- Not in the nightly backup. Start again from the pilot (on the server, `cd /opt/odoo4u`):
```bash
deploy/backup-daily.sh </dev/null                      # odoo4u
docker compose stop web                                # a template needs no open connection
docker compose exec -T db dropdb -U odoo --if-exists odoo4u_training
docker compose exec -T db createdb -U odoo -T odoo4u odoo4u_training
docker compose start web
docker compose exec -T web rm -rf /var/lib/odoo/filestore/odoo4u_training
docker compose exec -T web cp -a /var/lib/odoo/filestore/odoo4u /var/lib/odoo/filestore/odoo4u_training
docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_data.py
docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_scenarios.py
docker compose stop web
docker compose run --rm -T web odoo -d odoo4u_training -u x4u_account --stop-after-init   # the Focus tree (until the pilot has it)
./private/ata/run_ata_load.sh odoo4u_training        # ATA's Focus books Jan-Sep 2026 (private files, not in Git)
docker compose run --rm -T web odoo shell -d odoo4u_training --no-http < scripts/training_accounting.py
docker compose up -d
```
- Accounting in training (2026-11-24): 4U on the Focus account tree (x4u_account 18.0.1.10.0) with
  20 customers in every situation (`scripts/training_accounting.py`), and a second company
  **ATA SAIF ZONE** with its Focus books (admin and the Accountant only; files in
  `/opt/odoo4u/private/ata`, chmod 600). The pilot `odoo4u` has the tree since 18.0.1.11.0
  (2026-11-24, Phase 1 after the UAT: average cost, cost of sales at the delivery, serials; the
  owner's OK "Yes, deploy"). Check every report:
  `docker compose run --rm -T -e X4U_COMPANY="ATA SAIF ZONE" -e X4U_DATE_TO=2026-09-30 web odoo shell -d odoo4u_training --no-http < scripts/accounting_reports_check.py`
- After the pilot starts: drop it and put `dbfilter = ^odoo4u$`, `list_db = False` back.

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
# The generator catalog (spec x4u_generator_datasheet v0.3), again whenever a price list or the
# website changes. On the PC: python scripts/fetch_datasheets.py && python scripts/generator_catalog.py,
# then copy private/datasheets/catalog.json to /opt/odoo4u/private/datasheets/ (owner uid 100 = the
# container's odoo user, chmod 600), and here:
docker compose run --rm -T -v /opt/odoo4u/private/datasheets:/tmp/x4u_catalog:ro web \
  odoo shell -d odoo4u --no-http < scripts/import_generators.py
# The letterhead of the 4U quotation: copy private/branding/letterhead-*.png to
# /opt/odoo4u/private/branding/ (owner uid 100, chmod 600), then
docker compose run --rm -T -v /opt/odoo4u/private/branding:/tmp/x4u_branding:ro web \
  odoo shell -d odoo4u --no-http < scripts/set_letterhead.py
# A user's forgotten password (the owner types the new one):
pwsh scripts/reset-password.ps1 -Database odoo4u -Login <login>
# Change the domain: edit ODOO_DOMAIN in .env, then
docker compose up -d caddy
```

## Still to do
- The real outgoing email (SMTP of the company mailbox): until then Odoo sends nothing.
- The company subdomain instead of the temporary address (an A record to the server's IPv4).
- A copy of the nightly backup outside Hetzner (e.g. a Hetzner Storage Box or the owner's PC).
