# Restore a backup into a NEW database (never overwrites the source DB).
# Usage: .\scripts\restore-test.ps1 -BackupDir backups\odoo4u_dev-20261017-120000 -SourceDb odoo4u_dev
param(
    [Parameter(Mandatory = $true)][string]$BackupDir,
    [Parameter(Mandatory = $true)][string]$SourceDb,
    [string]$TargetDb = "$SourceDb`_restoretest"
)
$ErrorActionPreference = 'Stop'

function Run([string[]]$cmd) {
    & $cmd[0] $cmd[1..($cmd.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "Failed: $($cmd -join ' ')" }
}

if ($TargetDb -eq $SourceDb) { throw 'TargetDb must differ from SourceDb.' }

$exists = docker compose exec -T db psql -U odoo -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$TargetDb'"
if ($exists -match '1') { throw "Database '$TargetDb' already exists - drop it manually or choose another -TargetDb." }

$dump = Join-Path $BackupDir "$SourceDb.dump"
$fs   = Join-Path $BackupDir "$SourceDb-filestore.tgz"
if (-not (Test-Path $dump) -or -not (Test-Path $fs)) { throw "Missing $dump or $fs" }

# 1) Database
Run @('docker','compose','cp',$dump,'db:/tmp/restore.dump')
Run @('docker','compose','exec','-T','db','createdb','-U','odoo',$TargetDb)
Run @('docker','compose','exec','-T','db','pg_restore','-U','odoo','--no-owner','-d',$TargetDb,'/tmp/restore.dump')
Run @('docker','compose','exec','-T','db','rm','-f','/tmp/restore.dump')

# 2) Filestore: extract to a temp dir, then move under the TARGET name
Run @('docker','compose','cp',$fs,'web:/tmp/restore-fs.tgz')
Run @('docker','compose','exec','-T','web','sh','-c',
  "set -e; rm -rf /tmp/restore-fs; mkdir -p /tmp/restore-fs; tar -xzf /tmp/restore-fs.tgz -C /tmp/restore-fs; test ! -e /var/lib/odoo/filestore/$TargetDb; mv /tmp/restore-fs/$SourceDb /var/lib/odoo/filestore/$TargetDb; rm -rf /tmp/restore-fs")
# docker cp leaves the archive owned by root, so remove it as root
Run @('docker','compose','exec','-T','-u','root','web','rm','-f','/tmp/restore-fs.tgz')

# 3) Basic verification
Write-Host 'Row counts (source vs restored):'
foreach ($d in @($SourceDb, $TargetDb)) {
    $n = docker compose exec -T db psql -U odoo -d $d -tAc "SELECT (SELECT count(*) FROM res_partner)||' partners, '||(SELECT count(*) FROM ir_attachment)||' attachments'"
    Write-Host "  $d : $n"
}
Write-Host "Now open http://127.0.0.1:8069/web/database/selector , log in to '$TargetDb' and open a record with an attachment." -ForegroundColor Green
