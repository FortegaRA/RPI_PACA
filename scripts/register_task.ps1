# Register the RPI Tier-A run as a Windows Scheduled Task.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_task.ps1
#
# Edit the three settings below first if you want a different cadence/time.
# Re-running with the same TaskName updates it (/F overwrites).

$TaskName = 'RPI_TierA'
$Time     = '07:00'      # HH:mm (24h), local time
$Schedule = 'DAILY'      # DAILY  or  WEEKLY (weekly also runs on $Days)
$Days     = 'MON,TUE,WED,THU,FRI'   # only used when $Schedule = 'WEEKLY'

$proj    = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $proj 'scripts\run_tier_a.ps1'
if (-not (Test-Path $wrapper)) { Write-Host "Wrapper not found: $wrapper"; exit 1 }

$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$wrapper`""

if ($Schedule -eq 'WEEKLY') {
    schtasks /Create /TN $TaskName /TR $tr /SC WEEKLY /D $Days /ST $Time /RL LIMITED /F
} else {
    schtasks /Create /TN $TaskName /TR $tr /SC DAILY /ST $Time /RL LIMITED /F
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Registered scheduled task '$TaskName' ($Schedule at $Time)."
    Write-Host "  Run now to test : schtasks /Run /TN $TaskName"
    Write-Host "  Inspect         : schtasks /Query /TN $TaskName /V /FO LIST"
    Write-Host "  Remove          : schtasks /Delete /TN $TaskName /F"
    Write-Host "  Log             : output\scheduled_run.log"
} else {
    Write-Host "Failed to register task (exit $LASTEXITCODE)."
}
