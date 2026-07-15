param(
    [string]$Machine = "",
    [string]$ScriptPath = "\\192.168.1.188\AI\Tools\scripts\Update-WorkstationClientIfIdle.ps1",
    [string]$NasDistPath = "\\192.168.1.188\AI\Tools\dist-auto-update",
    [int]$EveryMinutes = 5,
    [switch]$AllowWhileActive,
    [switch]$PrintCommandOnly
)

$ErrorActionPreference = "Stop"

function Resolve-MachineName([string]$Value) {
    if ($Value) { return $Value }
    $hostName = ""
    if ($env:COMPUTERNAME) { $hostName = $env:COMPUTERNAME.Trim().ToLowerInvariant() }
    if ($hostName -eq "inbat") { return "InBat" }
    if ($hostName -eq "indecal") { return "InDecal" }
    if ($hostName -eq "cnc") { return "CNC" }
    throw "Cannot resolve machine name from COMPUTERNAME=$env:COMPUTERNAME. Pass -Machine."
}

$Machine = Resolve-MachineName $Machine
$taskName = "QLX Auto Update $Machine"
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -Machine $Machine -NasDistPath `"$NasDistPath`""
if ($AllowWhileActive) { $argument += " -AllowWhileActive" }

if ($PrintCommandOnly) {
    Write-Host $taskName
    Write-Host "powershell.exe $argument"
    exit 0
}

if ($EveryMinutes -lt 1) { throw "EveryMinutes must be >= 1" }
if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
    throw "Auto update script not found: $ScriptPath"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settingsArgs = @{
    MultipleInstances = "IgnoreNew"
    StartWhenAvailable = $true
}
$settingsParams = (Get-Command New-ScheduledTaskSettingsSet).Parameters
if ($settingsParams.ContainsKey("AllowStartIfOnBatteries")) {
    $settingsArgs.AllowStartIfOnBatteries = $true
}
if ($settingsParams.ContainsKey("DisallowStartIfOnBatteries")) {
    $settingsArgs.DisallowStartIfOnBatteries = $false
}
$settings = New-ScheduledTaskSettingsSet @settingsArgs

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "QuanLyXuong client auto-update only when production machine is idle" -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"
