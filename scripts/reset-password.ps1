# Reset a forgotten Odoo user password (dev PC only).
# Usage (from project root):  .\scripts\reset-password.ps1 -Database odoo4u_dev [-Login someone@example.com]
# Without -Login it resets the main administrator (user id 2).
# You type the new password yourself: it is not shown, logged or saved anywhere.
param(
    [Parameter(Mandatory = $true)][string]$Database,
    [string]$Login
)
$ErrorActionPreference = 'Stop'

function Plain($secure) {
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
$password = Plain (Read-Host 'New password' -AsSecureString)
if ($password -ne (Plain (Read-Host 'Repeat it' -AsSecureString))) { throw 'The two passwords differ.' }
if ($password.Length -lt 8) { throw 'Use at least 8 characters.' }

# Runs inside "odoo shell"; the password reaches it as an environment variable.
$py = @'
import os
login = os.environ.get("X4U_LOGIN")
users = env["res.users"].with_context(active_test=False)
user = users.search([("login", "=", login)]) if login else users.browse(2)
if len(user) != 1:
    raise SystemExit("No user with login %r" % login)
user.password = os.environ["X4U_NEW_PASSWORD"]
env.cr.commit()
print("Password changed for", user.login)
'@

$env:X4U_NEW_PASSWORD = $password
$env:X4U_LOGIN = $Login
# Piped text must not start with a BOM, which Python rejects.
$noBom = New-Object System.Text.UTF8Encoding $false
$consoleIn = [Console]::InputEncoding
$OutputEncoding = $noBom
[Console]::InputEncoding = $noBom
try {
    $py | docker compose run --rm -T -e X4U_NEW_PASSWORD -e X4U_LOGIN web odoo shell -d $Database --log-level=warn
    if ($LASTEXITCODE -ne 0) { throw 'Password reset failed.' }
} finally {
    [Console]::InputEncoding = $consoleIn
    Remove-Item Env:X4U_NEW_PASSWORD, Env:X4U_LOGIN -ErrorAction SilentlyContinue
}
