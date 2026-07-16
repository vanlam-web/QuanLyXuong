param(
    [string]$Machine = "",
    [string]$NasDistPath = "\\192.168.1.188\AI\Tools\dist-auto-update",
    [string]$LocalDir = "C:\QuanLyXuong\Client",
    [string]$DashboardUrl = "http://192.168.1.104:5000",
    [string]$StatusJsonPath = "",
    [int]$IdleSeconds = 300,
    [string]$StatePath = "",
    [switch]$AllowWhileActive,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

function Write-UpdateLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    if ($script:LogPath) {
        Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8
    }
}

function Resolve-MachineName([string]$Value) {
    if ($Value) { return $Value }
    $hostName = ""
    if ($env:COMPUTERNAME) { $hostName = $env:COMPUTERNAME.Trim().ToLowerInvariant() }
    if ($hostName -eq "inbat") { return "InBat" }
    if ($hostName -eq "indecal") { return "InDecal" }
    if ($hostName -eq "cnc") { return "CNC" }
    throw "Cannot resolve machine name from COMPUTERNAME=$env:COMPUTERNAME. Pass -Machine."
}

function Read-StatusData([string]$Path, [string]$Url, [string]$MachineName) {
    if ($Path) {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    $today = Get-Date -Format "yyyy-MM-dd"
    $encodedMachine = [uri]::EscapeDataString($MachineName)
    $endpoint = "$Url/api/data?start=$today&end=$today&machine=$encodedMachine&limit=80"
    return Invoke-RestMethod -Uri $endpoint -TimeoutSec 8
}

function Get-BlockingQueue($StatusData, [string]$MachineName) {
    $sections = @()
    if ($MachineName -eq "CNC") {
        $sections = @("RUNNING", "EXPORTED")
    } else {
        $sections = @("RUNNING", "RIP")
    }
    foreach ($section in $sections) {
        $items = $StatusData.$section
        if (-not $items) { continue }
        foreach ($item in $items) {
            $itemMachine = ""
            if ($item.machine) { $itemMachine = $item.machine }
            if ($itemMachine -eq $MachineName) {
                if ($section -eq "RUNNING" -and (Test-PausedItem $item)) { continue }
                return $section
            }
        }
    }
    return ""
}

function Test-PausedItem($Item) {
    if (-not $Item) { return $false }
    $status = ""
    $stage = ""
    $isPaused = ""
    if ($Item.status) { $status = [string]$Item.status }
    if ($Item.stage_key) { $stage = [string]$Item.stage_key }
    if ($Item.is_paused -ne $null) { $isPaused = [string]$Item.is_paused }
    $status = $status.Trim().ToUpperInvariant()
    $stage = $stage.Trim().ToUpperInvariant()
    $isPaused = $isPaused.Trim().ToLowerInvariant()
    return $status -in @("PAUSE", "PAUSED") -or $stage -eq "PAUSED" -or $isPaused -in @("true", "1")
}

function Get-PausedLogKey($StatusData, [string]$MachineName) {
    $items = $StatusData.RUNNING
    if (-not $items) { return "" }
    foreach ($item in $items) {
        $itemMachine = ""
        if ($item.machine) { $itemMachine = $item.machine }
        if ($itemMachine -ne $MachineName) { continue }
        if (-not (Test-PausedItem $item)) { continue }
        $name = ""
        $updated = ""
        $status = ""
        $progress = ""
        if ($item.name) { $name = [string]$item.name }
        if ($item.updated) { $updated = [string]$item.updated }
        if ($item.status) { $status = [string]$item.status }
        elseif ($item.stage_key) { $status = [string]$item.stage_key }
        if ($item.progress_label) { $progress = [string]$item.progress_label }
        return "$name|$updated|$status|$progress"
    }
    return ""
}

function Read-IdleState([string]$Path) {
    if ($Path -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
        try {
            $loaded = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
            foreach ($prop in @("idleSince", "lastBusyAt", "pausedQuietSince", "lastPausedLogKey", "lastOutcome", "lastOutcomeAt", "lastMessage", "sourcePath", "sourceExpected", "sourceActual", "localActual", "legacyActual")) {
                if (-not ($loaded.PSObject.Properties.Name -contains $prop)) {
                    $loaded | Add-Member -NotePropertyName $prop -NotePropertyValue ""
                }
            }
            return $loaded
        } catch { }
    }
    return [pscustomobject]@{
        idleSince = ""
        lastBusyAt = ""
        pausedQuietSince = ""
        lastPausedLogKey = ""
        lastOutcome = ""
        lastOutcomeAt = ""
        lastMessage = ""
        sourcePath = ""
        sourceExpected = ""
        sourceActual = ""
        localActual = ""
        legacyActual = ""
    }
}

function Save-IdleState([string]$Path, $State) {
    if (-not $Path) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $State | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Set-IdleStateField($State, [string]$Name, $Value) {
    if (-not $State) { return }
    if ($State.PSObject.Properties.Name -contains $Name) {
        $State.$Name = $Value
    } else {
        $State | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Write-IdleStateOutcome([string]$Path, $State, [string]$Outcome, [string]$Message, [string]$MachineName, [string]$SourcePath = "", [string]$ExpectedHash = "", [string]$ActualSourceHash = "", [string]$LocalHash = "", [string]$LegacyHash = "") {
    if (-not $State) { return }
    Set-IdleStateField $State "lastOutcome" $Outcome
    Set-IdleStateField $State "lastOutcomeAt" (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Set-IdleStateField $State "lastMessage" $Message
    Set-IdleStateField $State "machine" $MachineName
    Set-IdleStateField $State "sourcePath" $SourcePath
    Set-IdleStateField $State "sourceExpected" $ExpectedHash
    Set-IdleStateField $State "sourceActual" $ActualSourceHash
    Set-IdleStateField $State "localActual" $LocalHash
    Set-IdleStateField $State "legacyActual" $LegacyHash
    Save-IdleState $Path $State
}

function Get-ManifestHash($Manifest, [string]$FileName) {
    $entry = $Manifest.files | Where-Object { $_.name -eq $FileName } | Select-Object -First 1
    if (-not $entry) { return "" }
    if (-not $entry.sha256) { return "" }
    return $entry.sha256.ToUpperInvariant()
}

function Read-UpdateSource([string]$Path) {
    $exe = Join-Path $Path "QuanLyXuong.exe"
    $manifestPath = Join-Path $Path "BUILD_MANIFEST.json"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "NAS client exe not found: $exe" }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "NAS manifest not found: $manifestPath" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $expected = Get-ManifestHash $manifest "QuanLyXuong.exe"
    if (-not $expected) { throw "QuanLyXuong.exe hash missing in BUILD_MANIFEST.json" }
    $actual = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToUpperInvariant()
    return [pscustomobject]@{
        Path = $Path
        Exe = $exe
        ManifestPath = $manifestPath
        Manifest = $manifest
        Expected = $expected
        Actual = $actual
        IsMatch = ($actual -eq $expected)
    }
}

function Resolve-UpdateSource([string]$PreferredPath) {
    $source = Read-UpdateSource $PreferredPath
    if ($source.IsMatch) { return $source }

    $parent = Split-Path -Parent $PreferredPath
    $leaf = Split-Path -Leaf $PreferredPath
    if ($leaf -ne "dist") { return $source }

    $fallbackPath = Join-Path $parent "dist-auto-update"
    if (-not (Test-Path -LiteralPath $fallbackPath -PathType Container)) { return $source }
    $fallback = Read-UpdateSource $fallbackPath
    if ($fallback.IsMatch -and $fallback.Expected -eq $source.Expected) {
        Write-UpdateLog "SOURCE_SWITCH dist -> dist-auto-update $($fallback.Actual.Substring(0, 12))"
        return $fallback
    }
    return $source
}

function Stop-LocalClient {
    Get-Process QuanLyXuong,QuanLyXuong_Local -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

$Machine = Resolve-MachineName $Machine
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
if (-not $StatePath) { $StatePath = Join-Path $LocalDir "auto_update_state.json" }
$script:LogPath = Join-Path $LocalDir "auto_update.log"

$localExe = Join-Path $LocalDir "QuanLyXuong.exe"
$localManifest = Join-Path $LocalDir "BUILD_MANIFEST.json"
$legacyExe = Join-Path (Split-Path -Parent $LocalDir) "QuanLyXuong_Local.exe"

$state = Read-IdleState $StatePath
try {
    $statusData = Read-StatusData $StatusJsonPath $DashboardUrl $Machine
} catch {
    Write-IdleStateOutcome $StatePath $state "FAILED" ("status read failed: {0}" -f $_.Exception.Message) $Machine
    throw
}
$now = Get-Date

$blockingQueue = ""
if (-not $AllowWhileActive) {
    $blockingQueue = Get-BlockingQueue $statusData $Machine
}
if ($blockingQueue) {
    $state.idleSince = ""
    $state.lastBusyAt = $now.ToString("s")
    $state.pausedQuietSince = ""
    $state.lastPausedLogKey = ""
    Write-IdleStateOutcome $StatePath $state "BUSY" "blocked by $blockingQueue" $Machine
    Save-IdleState $StatePath $state
    Write-UpdateLog "BUSY $Machine $blockingQueue - skip update"
    exit 0
}

if ($IdleSeconds -gt 0) {
    if (-not $state.idleSince) {
        $state.idleSince = $now.ToString("s")
        Write-IdleStateOutcome $StatePath $state "WAIT_IDLE" "idle timer started" $Machine
        Save-IdleState $StatePath $state
        Write-UpdateLog "WAIT_IDLE $Machine - idle timer started"
        exit 0
    }
    $idleSince = [datetime]::Parse($state.idleSince)
    $idleAge = ($now - $idleSince).TotalSeconds
    if ($idleAge -lt $IdleSeconds) {
        Write-IdleStateOutcome $StatePath $state "WAIT_IDLE" ("{0:n0}/{1}s" -f $idleAge, $IdleSeconds) $Machine
        Write-UpdateLog ("WAIT_IDLE {0} - {1:n0}/{2}s" -f $Machine, $idleAge, $IdleSeconds)
        exit 0
    }

    $pausedLogKey = Get-PausedLogKey $statusData $Machine
    if ($pausedLogKey) {
        if (-not $state.pausedQuietSince) {
            $state.pausedQuietSince = $now.ToString("s")
            $state.lastPausedLogKey = $pausedLogKey
            Write-IdleStateOutcome $StatePath $state "WAIT_PAUSE_QUIET" "pause quiet timer started" $Machine
            Save-IdleState $StatePath $state
            Write-UpdateLog "WAIT_PAUSE_QUIET $Machine - pause quiet timer started"
            exit 0
        }
        if ($state.lastPausedLogKey -ne $pausedLogKey) {
            $state.pausedQuietSince = $now.ToString("s")
            $state.lastPausedLogKey = $pausedLogKey
            Write-IdleStateOutcome $StatePath $state "WAIT_PAUSE_QUIET" "pause log changed" $Machine
            Save-IdleState $StatePath $state
            Write-UpdateLog "WAIT_PAUSE_QUIET $Machine - pause log changed"
            exit 0
        }
        $pausedQuietSince = [datetime]::Parse($state.pausedQuietSince)
        $pausedQuietAge = ($now - $pausedQuietSince).TotalSeconds
        if ($pausedQuietAge -lt $IdleSeconds) {
            Write-IdleStateOutcome $StatePath $state "WAIT_PAUSE_QUIET" ("{0:n0}/{1}s" -f $pausedQuietAge, $IdleSeconds) $Machine
            Write-UpdateLog ("WAIT_PAUSE_QUIET {0} - {1:n0}/{2}s" -f $Machine, $pausedQuietAge, $IdleSeconds)
            exit 0
        }
    } else {
        $state.pausedQuietSince = ""
        $state.lastPausedLogKey = ""
        Write-IdleStateOutcome $StatePath $state "WAIT_IDLE" "pause cleared" $Machine
        Save-IdleState $StatePath $state
    }
}

try {
    $source = Resolve-UpdateSource $NasDistPath
} catch {
    Write-IdleStateOutcome $StatePath $state "FAILED" ("source read failed: {0}" -f $_.Exception.Message) $Machine
    throw
}
$sourceExe = $source.Exe
$sourceManifest = $source.ManifestPath
$expected = $source.Expected

if (Test-Path -LiteralPath $localExe -PathType Leaf) {
    $current = (Get-FileHash -LiteralPath $localExe -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($current -eq $expected) {
        $legacyActual = ""
        if (Test-Path -LiteralPath $legacyExe -PathType Leaf) {
            $legacyActual = (Get-FileHash -LiteralPath $legacyExe -Algorithm SHA256).Hash.ToUpperInvariant()
        }
        Write-IdleStateOutcome $StatePath $state "UP_TO_DATE" "local hash already matches manifest" $Machine $sourceExe $expected $source.Actual $current $legacyActual
        Write-UpdateLog "UP_TO_DATE $Machine $($current.Substring(0, 12))"
        exit 0
    }
}

try {
    Stop-LocalClient
    Copy-Item -LiteralPath $sourceExe -Destination $localExe -Force
    Copy-Item -LiteralPath $sourceManifest -Destination $localManifest -Force
    if ([System.IO.Path]::GetFullPath($legacyExe) -ne [System.IO.Path]::GetFullPath($localExe)) {
        Copy-Item -LiteralPath $sourceExe -Destination $legacyExe -Force
    }

    $actual = (Get-FileHash -LiteralPath $localExe -Algorithm SHA256).Hash.ToUpperInvariant()
    $legacyActual = ""
    if (Test-Path -LiteralPath $legacyExe -PathType Leaf) {
        $legacyActual = (Get-FileHash -LiteralPath $legacyExe -Algorithm SHA256).Hash.ToUpperInvariant()
    }
    if ($actual -ne $expected) {
        Write-IdleStateOutcome $StatePath $state "FAILED" "local client hash mismatch" $Machine $sourceExe $expected $source.Actual $actual $legacyActual
        Write-UpdateLog "FAILED $Machine hash mismatch"
        throw "Local client hash mismatch. expected=$expected actual=$actual"
    }

    if ($NoStart) {
        Write-IdleStateOutcome $StatePath $state "UPDATED" "copied only" $Machine $sourceExe $expected $source.Actual $actual $legacyActual
        Write-UpdateLog "UPDATED $Machine copied only $($actual.Substring(0, 12))"
        exit 0
    }

    Start-Process -FilePath $localExe -WorkingDirectory $LocalDir -WindowStyle Hidden
    Write-IdleStateOutcome $StatePath $state "UPDATED" "copied and started" $Machine $sourceExe $expected $source.Actual $actual $legacyActual
    Write-UpdateLog "UPDATED $Machine started $($actual.Substring(0, 12))"
} catch {
    Write-IdleStateOutcome $StatePath $state "FAILED" $_.Exception.Message $Machine $sourceExe $expected $source.Actual
    throw
}
