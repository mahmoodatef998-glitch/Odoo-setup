# 4U Power Generation — Odoo 18 Community (DEV)

Development environment only. Demo/test data only — no real company data, not exposed to the network.

| Component | Version (verified 2026-10-17) |
|---|---|
| Odoo | `odoo:18.0-20261015` (Docker Hub official image) |
| PostgreSQL | `postgres:16.15` |
| Docker Desktop | 4.95.0 (WSL 2 backend) |

## Layout
```
compose.yaml            containers (db + web)
.env.example            copy to .env  (git-ignored, holds DB_PASSWORD)
config/odoo.conf.example copy to config/odoo.conf (git-ignored)
custom-addons/          4U modules — never edit Odoo core
scripts/backup.ps1      DB dump + filestore
scripts/restore-test.ps1 restore into a NEW DB and verify
backups/                git-ignored
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
Open http://127.0.0.1:8069 (port can be changed with ODOO_PORT in .env) → create database `odoo4u_dev` with **demo data**, and set a **Master Password** (store it in your password manager).

## Daily
```powershell
docker compose up -d      # start
docker compose stop       # stop (data kept)
docker compose logs -f web
```

## Backup & restore test
```powershell
.\scripts\backup.ps1 -Db odoo4u_dev
.\scripts\restore-test.ps1 -BackupDir backups\<folder> -SourceDb odoo4u_dev
```
A backup counts only after the restore test passes and the restored DB opens with attachments.

## Danger zone
`docker compose down -v` **deletes all data volumes**. Never run it without a tested backup.
