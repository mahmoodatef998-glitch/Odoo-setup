# 4U Power Generation — Odoo 18 Community (project rules for Claude Code)

## Context
- Company: 4U Power Generation FZC (UAE) — generators, spare parts, warehouses, procurement, sales, assembly/manufacturing, quality inspection.
- Stack: Odoo 18.0 Community (`odoo:18.0-20261015` + `requirements.txt` → local image `odoo4u-web`), PostgreSQL 16.15, Docker Desktop on Windows 11 (WSL 2).
- Repo root on the PC: `A:\ODOO\odoo-4u\odoo-4u`.
- Working DB: `odoo4u_base` (4U company, English base + Arabic, no demo), built by `scripts/create-db.ps1`; all setup is decided and checked there, as code. `odoo4u_dev` = demo playground only. Tests: throwaway `odoo4u_test`, dropped after a green run.
- Dev email: Odoo sends everything to Mailpit (inbox http://127.0.0.1:8025); nothing reaches real people.
- Explain to the user in clear Egyptian Arabic; keep Odoo menu names and technical terms in English.

## Hard rules
1. Never edit Odoo core or OCA code. 4U code goes only in `custom-addons/` (one module per folder, technical prefix `x4u_`, e.g. `x4u_stock_generator`).
2. OCA repos are pinned git submodules in `oca-addons/` (see `scripts/add-oca.ps1`). Change a pin only with a reason in the commit message.
3. Secrets never go in Git, chat, or compose files: `.env`, `config/odoo.conf`, `backups/` are git-ignored. Ask the user to type secrets himself.
4. Dev only: no published ports beyond `127.0.0.1`, no deploy to a server without explicit approval. Company details (letterhead, TRN, contacts) may be used in the local dev DB for realistic documents (user, 2026-10-21) but never go in Git: real files live in git-ignored `private/`.
5. Never use `latest` tags; verify any new image tag / version on the official source first and cite it.
6. Before any destructive step (drop DB, `docker compose down -v`, module uninstall, migration): run `scripts/backup.ps1`, explain impact + rollback, get explicit approval.
7. Don't claim something works until verified (logs, `docker compose ps`, test run, UI check).

## Common commands (PowerShell, repo root)
```powershell
docker compose up -d ; docker compose ps ; docker compose logs -f web
docker compose build                       # after Dockerfile/requirements.txt change
docker compose restart web                 # after Python changes in custom-addons
docker compose run --rm web odoo -d odoo4u_base -u <module> --stop-after-init   # upgrade module (entrypoint adds DB credentials from .env)
.\scripts\backup.ps1 -Database odoo4u_base
.\scripts\restore-test.ps1 -BackupDir backups\<folder> -SourceDb odoo4u_base
.\scripts\create-db.ps1 -Database <new_db> -Email info@4upowers.com -MailCatcher   # new DB like production (refuses existing DBs)
.\scripts\reset-password.ps1 -Database odoo4u_base                                # forgotten Odoo password (user types it)
```

## Installed modules (odoo4u_dev, 2026-10-19)
Sales, CRM, Invoicing, Purchase, Inventory, Manufacturing, Employees, Time Off, Contracts,
OCA: account_usability, account_financial_report (+date_range, report_xlsx), mis_builder, quality_control_oca, quality_control_stock_oca, quality_control_mrp_oca,
account_reconcile_oca, account_asset_management, account_fiscal_year, account_check_deposit, account_due_list,
payroll (Beta), payroll_account, payroll_hr_public_holidays, hr_holidays_public, hr_employee_service, hr_employee_document.
4U: x4u_generator. Gap analysis and decisions: `docs/phase1/business-blueprint.md`.
`odoo4u_base` (rebuilt 2026-10-21): Sales, CRM, Purchase, Inventory, Manufacturing, Invoicing (`l10n_ae`), quality_control_mrp_oca, purchase_request, base_user_role, x4u_generator, x4u_setup_base, x4u_setup_4u, x4u_job_order, x4u_roles. Module-by-module work: `docs/modules/`.
Users get exactly one 4U role (`x4u_roles`); dev test users per role: `.\scripts\dev-users.ps1 -Database odoo4u_base` (no passwords, the user sets them).
Never click "Upgrade" (Enterprise) apps: Accounting (accountant), MRP II, Quality, Knowledge.

## Module conventions
- Odoo 18 manifest `version` = `18.0.x.y.z`, license `LGPL-3` (`AGPL-3` if it depends on an AGPL module, e.g. OCA `quality_control_*`), depends only on what is used.
- Security: every new model gets `ir.model.access.csv` rows + record rules where multi-company applies.
- Views: Odoo 18 uses `<list>` (not `<tree>`), `invisible="..."` expressions (no `attrs`).
- Add tests under `tests/` for business logic; run with `--test-enable -i <module>` on a throwaway DB.
