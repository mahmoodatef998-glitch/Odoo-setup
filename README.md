# 4U Power Generation — Odoo 18 Community (DEV)

Development environment only — test and training data, not exposed to the network. Company files (letterhead, datasheets, imports) stay in git-ignored `private/`, never in Git.

| Component | Version (verified 2026-10-17) |
|---|---|
| Odoo | `odoo:18.0-20261015` (Docker Hub official image) |
| PostgreSQL | `postgres:16.15` |
| Docker Desktop | 4.95.0 (WSL 2 backend) |

## Layout
```
compose.yaml            containers (db + web + mailpit)
.env.example            copy to .env  (git-ignored, holds DB_PASSWORD)
config/odoo.conf.example copy to config/odoo.conf (git-ignored)
custom-addons/          4U modules — never edit Odoo core
scripts/backup.ps1      DB dump + filestore
scripts/restore-test.ps1 restore into a NEW DB and verify
scripts/create-db.ps1   new DB like production (English base + Arabic, 4U modules)
scripts/reset-password.ps1 reset a forgotten Odoo password
backups/, private/      git-ignored
```

## First run (PowerShell, in this folder)
```powershell
Copy-Item .env.example .env
notepad .env                       # set your own DB_PASSWORD
Copy-Item config\odoo.conf.example config\odoo.conf
docker compose pull
docker compose up -d
docker compose ps                  # db = healthy, web = running
```
Then create the working database (English base + Arabic, no demo data, 4U modules):
```powershell
.\scripts\create-db.ps1 -Database odoo4u_base -Email info@4upowers.com -MailCatcher
```
Open http://127.0.0.1:8069/web/login?db=odoo4u_base (port can be changed with ODOO_PORT in .env), log in as admin / admin and change the password.
Emails go to the local Mailpit inbox, http://127.0.0.1:8025 , never to real people.
`odoo4u_dev` (Odoo demo data) is only a playground.

## Daily
```powershell
docker compose up -d      # start
docker compose stop       # stop (data kept)
docker compose logs -f web
```

## Backup & restore test
```powershell
.\scripts\backup.ps1 -Database odoo4u_base
.\scripts\restore-test.ps1 -BackupDir backups\<folder> -SourceDb odoo4u_base
```
A backup counts only after the restore test passes and the restored DB opens with attachments.

## CI (GitHub Actions)
`.github/workflows/odoo-tests.yml` installs every module in `custom-addons/` on a fresh
database and runs its tests on each push and pull request, with the same `Dockerfile` and
`compose.yaml`. A red run means a failed test or an ERROR in the Odoo log; the full log is
attached to the run as `odoo-test-log`. Make the "Odoo tests" check required on `main`
(Settings → Branches) so nothing is merged red.

## Danger zone
`docker compose down -v` **deletes all data volumes**. Never run it without a tested backup.

## OCA modules (Odoo 18.0)
Repos are git submodules under `oca-addons/`, pinned by commit (see `scripts/add-oca.ps1`).
Extra Python deps live in `requirements.txt` and are baked into the local image via `Dockerfile`.
```powershell
.\scripts\add-oca.ps1                 # first time only
git submodule update --init           # after cloning the repo elsewhere
docker compose build
docker compose up -d
```
Then in Odoo: Apps → Update Apps List → install the modules you need.
