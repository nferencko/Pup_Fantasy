# Creates (or replaces) a Windows scheduled task that refreshes the rankings every day at 9:00 AM.
# Run once:   powershell -ExecutionPolicy Bypass -File schedule_update.ps1
# Remove:     Unregister-ScheduledTask -TaskName FantasyRankingsDailyUpdate -Confirm:$false
#
# The task uses this PC's clock, so 9:00 AM is Pacific time as long as Windows is set to Pacific
# (it follows daylight saving automatically). If the PC is off or asleep at 9 AM, the update runs
# as soon as the PC is back on and online.
$ErrorActionPreference = "Stop"
$taskName = "FantasyRankingsDailyUpdate"
$bat = Join-Path $PSScriptRoot "update_scheduled.bat"

$action   = New-ScheduledTaskAction -Execute "powershell.exe" `
              -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$bat'`"" -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At "9:00AM"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
              -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Principal $principal -Description "Refreshes fantasy football rankings (update_data.py) daily at 9 AM Pacific." -Force | Out-Null
$t = Get-ScheduledTask -TaskName $taskName
"Task '$taskName' is set. Next run: " + (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime
