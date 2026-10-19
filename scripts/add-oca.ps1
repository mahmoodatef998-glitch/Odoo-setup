# Adds the OCA 18.0 repositories as git submodules, pinned to reviewed commits.
# Run once from the project root:  .\scripts\add-oca.ps1  (existing ones are kept)
$ErrorActionPreference = 'Stop'
$repos = [ordered]@{
    # reviewed 2026-10-17
    'account-financial-tools'     = '7b7c0d6'
    'account-financial-reporting' = '512c06f'
    'mis-builder'                 = '4f9eef0'
    'reporting-engine'            = 'e35a0fe'
    'server-ux'                   = '8ae4369'
    'manufacture'                 = '635df4c'
    # reviewed 2026-10-19: accounting + payroll (docs/phase1/business-blueprint.md §6)
    'account-reconcile'           = '00b5908'
    'account-payment'             = '2d68222'
    'payroll'                     = '4c71cd4'
    'hr-holidays'                 = '893e3e3'
    'hr'                          = '96c6ad7'
    'calendar'                    = 'ebd2e06'
}
foreach ($r in $repos.Keys) {
    $path = "oca-addons/$r"
    if (-not (Test-Path $path)) {
        git submodule add -b 18.0 "https://github.com/OCA/$r.git" $path
        if ($LASTEXITCODE -ne 0) { throw "submodule add failed: $r" }
    }
    git -C $path checkout $repos[$r]
    if ($LASTEXITCODE -ne 0) { throw "checkout failed: $r" }
}
git add .gitmodules oca-addons
Write-Host 'OCA submodules ready. Next: docker compose build; docker compose up -d' -ForegroundColor Green
