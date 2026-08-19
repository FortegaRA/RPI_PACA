# RPI Tier-A scheduled run — the unattended slice of the pipeline.
#
# Runs ONLY the reliable HTTP sources (EMA, FDA, Colombia approvals, El Salvador,
# Honduras) -> normalize / post-filter / consolidate -> xlsx report.
# No browser, no CAPTCHA, no human: safe to run on a schedule.
#
# The run writes files and stops there. There is NO automated delivery (Notion /
# Airtable / email were removed 16/08/2026 — company compliance does not permit
# automated connectors). Someone opens output\RPI_REPORT_*.xlsx afterwards and
# copies the rows into the team's consolidated workbook.
#
# Called by the Windows Scheduled Task created with scripts\register_task.ps1.

$ErrorActionPreference = 'Continue'
$proj   = Split-Path -Parent $PSScriptRoot
# Prefer the project's virtual environment; fall back to a system Python.
$python = Join-Path $proj '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'C:\Python311\python.exe' }
Set-Location $proj

$log = Join-Path $proj 'output\scheduled_run.log'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
"=== RPI Tier-A run $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -Append -Encoding utf8 $log

& $python rpi_cluster.py --tier-a *>> $log

"=== finished (exit $LASTEXITCODE) ===" | Out-File -Append -Encoding utf8 $log
