#!/usr/bin/env bash
# Pilot server, every night from cron (docs/deploy/hetzner-pilot.md): the database dump and the
# filestore with scripts/backup.ps1, kept 14 days in /opt/odoo4u/backups. Hetzner's own server
# Backups (daily image, kept 7) hold a copy outside the server.
set -euo pipefail
cd /opt/odoo4u
pwsh -NoProfile -File scripts/backup.ps1 -Database "${1:-odoo4u}"
find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
