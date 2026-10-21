# Dev only: one test user per 4U role (fake names on example.com, no password).
# Usage (from project root):  .\scripts\dev-users.ps1 -Database odoo4u_base
# Set a password yourself (Settings > Users > Action > Change Password) to log in as one of them.
param([Parameter(Mandatory = $true)][string]$Database)
$ErrorActionPreference = 'Stop'

$code = Get-Content -Raw (Join-Path $PSScriptRoot 'dev_users.py')
$noBom = New-Object System.Text.UTF8Encoding $false
$consoleIn = [Console]::InputEncoding
$OutputEncoding = $noBom
[Console]::InputEncoding = $noBom   # piped code must not start with a BOM
$ErrorActionPreference = 'Continue'   # Docker logs to stderr; the exit code decides
try {
    $code | docker compose run --rm -T web odoo shell -d $Database --log-level=warn
} finally {
    $ErrorActionPreference = 'Stop'
    [Console]::InputEncoding = $consoleIn
}
if ($LASTEXITCODE -ne 0) { throw 'Creating the test users failed.' }
