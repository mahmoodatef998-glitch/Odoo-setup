# Backup one Odoo database: PostgreSQL dump + filestore.
# Usage (from project root):  .\scripts\backup.ps1 -Db odoo4u_dev
param([Parameter(Mandatory = $true)][string]$Db)
$ErrorActionPreference = 'Stop'

function Run([string[]]$cmd) {
    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Failed: $($cmd -join ' ')" }
}

$ts   = Get-Date -Format 'yyyyMMdd-HHmmss'
$dir  = Join-Path 'backups' "$Db-$ts"
New-Item -ItemType Directory -Force $dir | Out-Null

# 1) Database dump (custom format), written inside the container then copied out
#    (avoids PowerShell corrupting binary output on redirect).
Run @('docker','compose','exec','-T','db','pg_dump','-U','odoo','-Fc','-f',"/tmp/$Db.dump",$Db)
Run @('docker','compose','cp',"db:/tmp/$Db.dump",(Join-Path $dir "$Db.dump"))
Run @('docker','compose','exec','-T','db','rm','-f',"/tmp/$Db.dump")

# 2) Filestore (attachments)
Run @('docker','compose','exec','-T','web','tar','-czf',"/tmp/$Db-filestore.tgz",'-C','/var/lib/odoo/filestore',$Db)
Run @('docker','compose','cp',"web:/tmp/$Db-filestore.tgz",(Join-Path $dir "$Db-filestore.tgz"))
Run @('docker','compose','exec','-T','web','rm','-f',"/tmp/$Db-filestore.tgz")

Get-ChildItem $dir | Format-Table Name, Length
Write-Host "Backup written to $dir  - NOT trusted until restore-test.ps1 passes." -ForegroundColor Yellow
