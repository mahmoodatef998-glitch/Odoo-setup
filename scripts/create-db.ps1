# Create a NEW Odoo database the way production will be created:
# English as the base language, Arabic as a second language, the 4U company, then our modules.
# Usage (from project root):
#   .\scripts\create-db.ps1 -Database odoo4u_base [-CompanyName "..."] [-Email info@example.com] [-MailCatcher] [-TestUsers]
# -Email       company email; its domain becomes the "From" of outgoing emails (e.g. info@...).
# -MailCatcher dev only: every email goes to the local Mailpit inbox (http://127.0.0.1:8025), never to real people.
# -TestUsers   dev only: one test user per 4U role (scripts/dev_users.py), no password.
# Never loads demo data. Refuses to touch a database that already exists.
param(
    [Parameter(Mandatory = $true)][string]$Database,
    [string]$CompanyName = '4U Power Generation (DEV)',
    [string]$Email,
    [switch]$MailCatcher,
    [switch]$TestUsers,
    [string]$Modules = (@(
        # Odoo apps
        'sale_management', 'crm', 'purchase', 'stock', 'mrp',
        'hr', 'hr_holidays', 'hr_contract',
        # OCA: quality, full accounting (Community), payroll (blueprint §6)
        'quality_control_mrp_oca',
        'account_usability', 'account_financial_report', 'mis_builder', 'account_reconcile_oca',
        'account_asset_management', 'account_fiscal_year', 'account_check_deposit', 'account_due_list',
        'payroll', 'payroll_account', 'payroll_hr_public_holidays', 'hr_holidays_public',
        'hr_employee_service', 'hr_employee_document',
        # 4U
        'x4u_generator', 'x4u_setup_base', 'x4u_setup_4u', 'x4u_job_order', 'x4u_roles'
    ) -join ',')
)
$ErrorActionPreference = 'Stop'

function Run([string[]]$cmd) {
    # Docker and Odoo log to stderr. If this script's output is redirected, PowerShell 5.1 turns
    # those lines into errors, so only the exit code decides success here.
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $cmd[0] $cmd[1..($cmd.Length - 1)] } finally { $ErrorActionPreference = $eap }
    if ($LASTEXITCODE -ne 0) { throw "Failed: $($cmd -join ' ')" }
}

function Odoo([string[]]$odooArgs) {
    Run (@('docker', 'compose', 'run', '--rm', '-T', 'web', 'odoo', '-d', $Database) + $odooArgs + @('--stop-after-init'))
}

# Runs Python in "odoo shell"; parameters reach it as environment variables.
function Shell([string]$code) {
    $noBom = New-Object System.Text.UTF8Encoding $false
    $consoleIn = [Console]::InputEncoding
    $OutputEncoding = $noBom
    [Console]::InputEncoding = $noBom   # piped code must not start with a BOM
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # see Run
    try {
        $code | docker compose run --rm -T -e X4U_COMPANY -e X4U_EMAIL -e X4U_MAIL_CATCHER web odoo shell -d $Database --log-level=warn
    } finally {
        $ErrorActionPreference = $eap
        [Console]::InputEncoding = $consoleIn
    }
    if ($LASTEXITCODE -ne 0) { throw 'odoo shell step failed.' }
}

$ErrorActionPreference = 'Continue'   # see Run
$exists = docker compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$Database'"
$ErrorActionPreference = 'Stop'
if ($LASTEXITCODE -ne 0) { throw 'Could not reach PostgreSQL (is "docker compose up -d" running?).' }
if ($exists -match '1') { throw "Database '$Database' already exists. Back it up and drop it first (CLAUDE.md rule 6)." }

$env:X4U_COMPANY = $CompanyName
$env:X4U_EMAIL = $Email
$env:X4U_MAIL_CATCHER = $(if ($MailCatcher) { '1' } else { '0' })
try {
    # 1) English first. Loading Arabic together with base would make Arabic the database
    #    language: every name Odoo generates (journal codes, operation types...) would be Arabic.
    Write-Host '1/5 Base in English' -ForegroundColor Cyan
    Odoo @('-i', 'base', '--without-demo=all')
    Write-Host '2/5 Arabic as a second language' -ForegroundColor Cyan
    Odoo @('--load-language=ar_001')

    # 2) Company before the apps, so the UAE chart of accounts and taxes (l10n_ae) are used.
    Write-Host '3/5 Company' -ForegroundColor Cyan
    Shell @'
import os
company = env.ref("base.main_company")
aed = env.ref("base.AED")
aed.active = True
vals = {"name": os.environ["X4U_COMPANY"], "country_id": env.ref("base.ae").id, "currency_id": aed.id}
if os.environ.get("X4U_EMAIL"):
    vals["email"] = os.environ["X4U_EMAIL"]
company.write(vals)
env.ref("base.user_admin").tz = "Asia/Dubai"
env.cr.commit()
print("Company:", company.name, company.country_id.code, company.currency_id.name)
'@

    # The UAE chart (taxes, journals) is loaded after the other modules of the same install
    # step, so it gets its own step: our modules then find the taxes they set as defaults.
    Write-Host '4/5 Accounting: UAE chart of accounts and taxes' -ForegroundColor Cyan
    Odoo @('-i', 'account')
    Write-Host '4/5 Apps and 4U modules' -ForegroundColor Cyan
    Odoo @('-i', $Modules)

    Write-Host '5/5 Email and checks' -ForegroundColor Cyan
    Shell @'
import os
company = env.ref("base.main_company")
email = os.environ.get("X4U_EMAIL") or ""
if "@" in email:
    local, domain = email.split("@", 1)
    Domain = env["mail.alias.domain"]
    alias_domain = Domain.search([("name", "=", domain)], limit=1) or Domain.create({"name": domain})
    alias_domain.default_from = local
    company.alias_domain_id = alias_domain
if os.environ.get("X4U_MAIL_CATCHER") == "1":
    env["ir.mail_server"].create({
        "name": "Dev mail catcher (Mailpit)",
        "smtp_host": "mailpit", "smtp_port": 1025, "smtp_encryption": "none", "sequence": 1,
    })
env.cr.commit()
users = env["res.users"].with_context(active_test=False).search([])
print("Users language:", sorted(set(users.mapped("lang"))))
print("New contacts language:", env["ir.default"]._get("res.partner", "lang"))
print("Languages:", env["res.lang"].search([]).mapped("code"))
print("Journals:", env["account.journal"].search([]).mapped("code"))
print("Operation types:", env["stock.picking.type"].search([]).mapped("name"))
print("Emails from:", company.default_from_email or "-", "| mail servers:", env["ir.mail_server"].search([]).mapped("name"))
'@
    if ($TestUsers) {
        Write-Host 'Test users (dev only)' -ForegroundColor Cyan
        Shell (Get-Content -Raw (Join-Path $PSScriptRoot 'dev_users.py'))
    }
} finally {
    Remove-Item Env:X4U_COMPANY, Env:X4U_EMAIL, Env:X4U_MAIL_CATCHER -ErrorAction SilentlyContinue
}
Write-Host "Database '$Database' is ready: http://localhost:8069/web/login?db=$Database (admin / admin - change it)" -ForegroundColor Green
