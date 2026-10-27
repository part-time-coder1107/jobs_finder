# ============================================================================
# Register 10:00 AM & 10:00 PM Daily Job-Search Agent in Windows Task Scheduler
# Run in PowerShell: .\scripts\register_task_scheduler.ps1
# ============================================================================

$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonExe = (Get-Command python).Source
$TaskName = "PersonalAIJobSearchAgent_10AM_10PM"

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m src.main --run-once" `
    -WorkingDirectory $ProjectDir

$Trigger10AM = New-ScheduledTaskTrigger -Daily -At 10:00AM
$Trigger10PM = New-ScheduledTaskTrigger -Daily -At 10:00PM

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($Trigger10AM, $Trigger10PM) `
    -Settings $Settings `
    -Description "Runs the Personal AI Job-Search Engine at 10:00 AM and 10:00 PM daily and sends the Gmail digest." `
    -Force

Write-Host "✅ Registered Windows Scheduled Task '$TaskName' for 10:00 AM and 10:00 PM daily!" -ForegroundColor Green
