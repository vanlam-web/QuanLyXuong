# Operational Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lam he thong V2 on dinh truoc khi sua tiep UI/%/ETA: khong process trung, test khong cham log/live data, health/status bao dung, version may san xuat dong bo ro.

**Architecture:** Giu kien truc hien tai `server_Local.exe`, `Dashboard_Local.exe`, `cnc_legacy_bridge.exe`, agent may san xuat va SQLite. Them lop guard/diagnostic nho quanh runtime va test, khong viet lai core san xuat. Moi thay doi co test truoc, deploy tung phan co rollback.

**Tech Stack:** Python 3.10, unittest, Flask Dashboard, FastAPI server, SQLite, PowerShell runtime scripts, PyInstaller, NSSM.

---

## Context da doc qua 3 vong

### Vong 1 - Tong hop van de tu docs/live

- `docs/MASTER_PLAN.md`: uu tien on dinh hon tinh nang, moi deploy phai co rollback, loi phai co log de doc.
- `docs/V2_RUNBOOK.md`: V2 chay `server_Local.exe`, `Dashboard_Local.exe`, `cnc_legacy_bridge.exe`; dashboard `:5000` la man hinh van hanh.
- `docs/V2_DIRECTION_DECISIONS.md`: V2 khong tu tao bill, khong gui Zalo auto, event phai co outbox/idempotency, QCVL chua dieu khien nguoc may.
- Live ngay 2026-07-15 da thay trung process: 2 `server_Local.exe`, 2 `Dashboard_Local.exe`, 2 `cnc_legacy_bridge.exe`.
- Full test pass nhung `tests/test_server_reprint_noise.py` ghi log mau vao `C:\QuanLyXuong\Server_Log.txt` qua `server.log_sys()`.
- Version live lech: InBat `V2.0.9_AUTO_UPDATE_IDLE`, InDecal `V2.1.0_TEST`, CNC `V2.1.0_TEST_CNC_BRIDGE`.

### Vong 2 - Soi script/code

- `scripts/Start-V2RuntimeNssm.ps1` da co mutex `Global\QuanLyXuongV2Runtime`, nhung `scripts/Start-V2Runtime.ps1` va `scripts/Restart-DashboardV2.ps1` chua co guard/verify du manh.
- `scripts/Test-QuanLyXuongHealth.ps1` chi check "co process", chua fail khi process count > 1.
- `app/Dashboard.py:get_v2_status_snapshot()` doc version/log/machine status, nhung chua co diagnosis duplicate process tu may server.
- `app/server.py:LOG_FILE` hardcode `C:\QuanLyXuong\Server_Log.txt`; tests patch `DB_DIR` nhung chua patch `LOG_FILE`.
- `Dashboard.py` qua lon, nhung tach file lon khong nen lam trong cung chang nay neu muc tieu la on dinh van hanh nhanh.

### Vong 3 - Dieu chinh muc tieu

Khong sua truc tiep %/ETA hay preview trong plan nay. Truoc het phai lam 4 nen:

1. Test khong ghi log/live data.
2. Runtime khong duoc co 2 process cung vai tro.
3. Healthcheck/Dashboard phai bao do neu co duplicate hoac version lech.
4. Docs/runbook phai co lenh kiem tra va cach restart sach.

---

## File Structure

- Modify: `tests/test_server_reprint_noise.py`
  - Patch `server.LOG_FILE` vao temp dir trong `setUp()`.
  - Them test rang buoc `post_event()` khong ghi `C:\QuanLyXuong\Server_Log.txt`.

- Modify: `tests/test_dashboard_v2_status.py`
  - Them test cho runtime process summary trong `/api/v2_status`.
  - Them test version health: online machine khac expected client version se tao warning.

- Modify: `tests/test_workstation_auto_update.py`
  - Them test source version/hash doc tu manifest va auto-update status.

- Modify: `scripts/Test-QuanLyXuongHealth.ps1`
  - Them helper dem process.
  - Fail khi `server_Local`, `Dashboard_Local`, `cnc_legacy_bridge` count > 1.
  - In PID/path khi duplicate.

- Modify: `scripts/Start-V2Runtime.ps1`
  - Them mutex/script lock cho runtime tay.
  - Sau stop/start, verify moi role chi co 1 process.
  - Neu stop fail do access denied, fail ro, khong start them process moi.

- Modify: `scripts/Restart-DashboardV2.ps1`
  - Stop dashboard cu, wait, verify con 0 process truoc copy/start.
  - Sau start, verify chi co 1 `Dashboard_Local.exe`.
  - Fail ro neu co duplicate.

- Modify: `app/Dashboard.py`
  - Them helper `inspect_runtime_processes()` doc process count cua server/dashboard/cnc bridge.
  - Them `runtime_processes` va warning duplicate vao `/api/v2_status`.
  - Them expected version source trong status de man hinh `Phien ban` noi ro may nao lech.

- Modify: `app/server.py`
  - Cho `LOG_FILE` doc env `QLX_SERVER_LOG_FILE`, default giu `C:\QuanLyXuong\Server_Log.txt`.
  - Khong doi endpoint `/api/log_event`.

- Modify: `app/qlx_config.py`
  - Them config `SERVER_LOG_FILE`, `DASHBOARD_LOG_FILE` neu can dung chung sau nay.
  - Giu default cu de production khong doi hanh vi.

- Modify: `docs/V2_RUNBOOK.md`
  - Them muc "Restart sach / duplicate process".
  - Them muc "Doc version dung".

- Modify: `docs/HEALTHCHECK_RUNBOOK.md`
  - Them cach doc duplicate process va cach xu ly.

- Modify: `CHANGELOG.md`
  - Ghi muc on dinh van hanh.

---

### Task 1: Co lap log trong unit test server

**Files:**
- Modify: `tests/test_server_reprint_noise.py`
- Modify: `app/server.py`
- Test: `tests/test_server_reprint_noise.py`

- [ ] **Step 1: Write failing test**

Add this test to `ServerReprintNoiseTests`:

```python
    def test_post_event_writes_log_to_test_temp_file_only(self):
        live_log = r"C:\QuanLyXuong\Server_Log.txt"
        before_size = os.path.getsize(live_log) if os.path.exists(live_log) else 0

        self.post_event(
            "DONE",
            "2026-07-10 15:27:57",
            "test-log-isolation-done",
            path=r"D:\2026-07-10\New Folder\log_isolation.prt",
        )

        after_size = os.path.getsize(live_log) if os.path.exists(live_log) else 0
        self.assertEqual(after_size, before_size)
        with open(self.test_log_file, "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("[INBAT] DONE: log_isolation.prt", content)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_server_reprint_noise.ServerReprintNoiseTests.test_post_event_writes_log_to_test_temp_file_only
```

Expected before fix:

```text
FAIL
```

because `server.LOG_FILE` still points at `C:\QuanLyXuong\Server_Log.txt`.

- [ ] **Step 3: Patch `setUp()` to isolate server log**

In `tests/test_server_reprint_noise.py`, update `setUp()` and `restore_globals()`:

```python
        self.old_log_file = server.LOG_FILE
        self.test_log_file = os.path.join(self.temp_dir.name, "Server_Log.txt")
        server.LOG_FILE = self.test_log_file
```

```python
        server.LOG_FILE = self.old_log_file
```

- [ ] **Step 4: Allow env override in app code**

In `app/server.py`, replace:

```python
LOG_FILE = r"C:\QuanLyXuong\Server_Log.txt"
```

with:

```python
LOG_FILE = os.getenv("QLX_SERVER_LOG_FILE", r"C:\QuanLyXuong\Server_Log.txt")
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_server_reprint_noise
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit**

```powershell
git add app/server.py tests/test_server_reprint_noise.py
git commit -m "test: isolate server logs from production"
```

---

### Task 2: Fail healthcheck khi runtime co duplicate process

**Files:**
- Modify: `scripts/Test-QuanLyXuongHealth.ps1`
- Test: `tests/test_runtime_health_scripts.py`

- [ ] **Step 1: Create failing test file**

Create `tests/test_runtime_health_scripts.py`:

```python
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HEALTH_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "Test-QuanLyXuongHealth.ps1")


class RuntimeHealthScriptTests(unittest.TestCase):
    def test_healthcheck_contains_duplicate_process_gate(self):
        with open(HEALTH_SCRIPT, "r", encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("Test-ProcessCountAtMostOne", script)
        self.assertIn("Duplicate process server_Local", script)
        self.assertIn("Duplicate process Dashboard_Local", script)
        self.assertIn("Duplicate process cnc_legacy_bridge", script)
        self.assertIn("Process server duplicate guard", script)
        self.assertIn("Process Dashboard duplicate guard", script)
        self.assertIn("Process CNC bridge duplicate guard", script)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Add process-count helper**

In `scripts/Test-QuanLyXuongHealth.ps1`, after `Test-AnyProcess`, add:

```powershell
function Get-ProcessDetails([string]$Name) {
    @(Get-Process -Name $Name -ErrorAction SilentlyContinue | ForEach-Object {
        $path = ""
        try { $path = $_.Path } catch { $path = "" }
        "pid=$($_.Id) path=$path"
    })
}

function Test-ProcessCountAtMostOne([string]$Name, [ref]$Detail) {
    $items = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if ($items.Count -le 1) {
        $Detail.Value = "$Name count=$($items.Count)"
        return $true
    }
    $Detail.Value = "Duplicate process $Name count=$($items.Count): $((Get-ProcessDetails $Name) -join '; ')"
    return $false
}
```

- [ ] **Step 4: Add duplicate checks**

Inside the existing `if ($Role -in @("All", "Server"))` block, after process existence checks, add:

```powershell
    $serverDupDetail = ""
    Add-Check $checks "Process server duplicate guard" (Test-ProcessCountAtMostOne "server_Local" ([ref]$serverDupDetail)) $serverDupDetail

    $dashboardDupDetail = ""
    Add-Check $checks "Process Dashboard duplicate guard" (Test-ProcessCountAtMostOne "Dashboard_Local" ([ref]$dashboardDupDetail)) $dashboardDupDetail

    $cncDupDetail = ""
    Add-Check $checks "Process CNC bridge duplicate guard" (Test-ProcessCountAtMostOne "cnc_legacy_bridge" ([ref]$cncDupDetail)) $cncDupDetail
```

- [ ] **Step 5: Run focused test**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts
```

Expected:

```text
OK
```

- [ ] **Step 6: Run real healthcheck**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Test-QuanLyXuongHealth.ps1 -Role Server
```

Expected in current dirty live state:

```text
[WARN] Process server duplicate guard - Duplicate process server_Local count=2
[WARN] Process Dashboard duplicate guard - Duplicate process Dashboard_Local count=2
[WARN] Process CNC bridge duplicate guard - Duplicate process cnc_legacy_bridge count=2
SUMMARY ok=
warn=3
```

- [ ] **Step 7: Commit**

```powershell
git add scripts/Test-QuanLyXuongHealth.ps1 tests/test_runtime_health_scripts.py
git commit -m "health: detect duplicate runtime processes"
```

---

### Task 3: Lam `Start-V2Runtime.ps1` khong start them khi stop fail

**Files:**
- Modify: `scripts/Start-V2Runtime.ps1`
- Test: `tests/test_runtime_health_scripts.py`

- [ ] **Step 1: Add failing test**

Add to `RuntimeHealthScriptTests`:

```python
    def test_start_runtime_uses_strict_stop_and_verify_single_instance(self):
        path = os.path.join(PROJECT_ROOT, "scripts", "Start-V2Runtime.ps1")
        with open(path, "r", encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("Stop-Process -Id $process.Id -Force -ErrorAction Stop", script)
        self.assertIn("Wait-Process -Id $process.Id -Timeout 10 -ErrorAction Stop", script)
        self.assertIn("Assert-SingleProcess \"server_Local\"", script)
        self.assertIn("Assert-SingleProcess \"Dashboard_Local\"", script)
        self.assertIn("Assert-SingleProcess \"cnc_legacy_bridge\"", script)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts.RuntimeHealthScriptTests.test_start_runtime_uses_strict_stop_and_verify_single_instance
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Make stop strict**

In `scripts/Start-V2Runtime.ps1`, replace `Stop-IfRunning` with:

```powershell
function Stop-IfRunning([string]$ProcessName) {
    $processes = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
    if ($processes.Count -eq 0) { return }
    foreach ($process in $processes) {
        Write-Host "Stopping $ProcessName pid=$($process.Id)"
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
    }
    foreach ($process in $processes) {
        try {
            Wait-Process -Id $process.Id -Timeout 10 -ErrorAction Stop
        } catch {
            $stillRunning = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
            if ($stillRunning) {
                throw "Cannot stop $ProcessName pid=$($process.Id). Run PowerShell as Administrator or stop NSSM service first."
            }
        }
    }
}
```

- [ ] **Step 4: Add single-process assertion**

Add this helper near `Stop-BridgePython`:

```powershell
function Assert-SingleProcess([string]$ProcessName) {
    $items = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
    if ($items.Count -gt 1) {
        $detail = ($items | ForEach-Object {
            $path = ""
            try { $path = $_.Path } catch { $path = "" }
            "pid=$($_.Id) path=$path"
        }) -join "; "
        throw "Duplicate $ProcessName count=$($items.Count): $detail"
    }
    Write-Host "$ProcessName count=$($items.Count)"
}
```

After current final loop that prints process counts, add:

```powershell
Assert-SingleProcess "server_Local"
Assert-SingleProcess "Dashboard_Local"
Assert-SingleProcess "cnc_legacy_bridge"
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/Start-V2Runtime.ps1 tests/test_runtime_health_scripts.py
git commit -m "runtime: prevent duplicate V2 process starts"
```

---

### Task 4: Lam `Restart-DashboardV2.ps1` verify sach

**Files:**
- Modify: `scripts/Restart-DashboardV2.ps1`
- Test: `tests/test_runtime_health_scripts.py`

- [ ] **Step 1: Add failing test**

Add:

```python
    def test_restart_dashboard_verifies_zero_before_start_and_one_after_start(self):
        path = os.path.join(PROJECT_ROOT, "scripts", "Restart-DashboardV2.ps1")
        with open(path, "r", encoding="utf-8") as handle:
            script = handle.read()

        self.assertIn("Assert-ProcessCount \"Dashboard_Local\" 0", script)
        self.assertIn("Assert-ProcessCount \"Dashboard_Local\" 1", script)
        self.assertIn("Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop", script)
        self.assertIn("throw \"Dashboard process count mismatch", script)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts.RuntimeHealthScriptTests.test_restart_dashboard_verifies_zero_before_start_and_one_after_start
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Add assert helper and strict stop**

In `scripts/Restart-DashboardV2.ps1`, set:

```powershell
$ErrorActionPreference = "Stop"
```

Add:

```powershell
function Assert-ProcessCount([string]$Name, [int]$Expected) {
    $items = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if ($items.Count -ne $Expected) {
        $detail = ($items | ForEach-Object {
            $path = ""
            try { $path = $_.Path } catch { $path = "" }
            "pid=$($_.Id) path=$path"
        }) -join "; "
        throw "Dashboard process count mismatch for $Name. expected=$Expected actual=$($items.Count) $detail"
    }
}
```

Change stop loop to:

```powershell
$runningDashboards | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
}
foreach ($dashboard in $runningDashboards) {
    try { Wait-Process -Id $dashboard.ProcessId -Timeout 8 -ErrorAction Stop } catch {}
}
Assert-ProcessCount "Dashboard_Local" 0
```

After `Start-Process`, add:

```powershell
Start-Sleep -Seconds 2
Assert-ProcessCount "Dashboard_Local" 1
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_runtime_health_scripts
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/Restart-DashboardV2.ps1 tests/test_runtime_health_scripts.py
git commit -m "runtime: verify clean dashboard restart"
```

---

### Task 5: Dua duplicate process vao `/api/v2_status`

**Files:**
- Modify: `app/Dashboard.py`
- Modify: `tests/test_dashboard_v2_status.py`
- Test: `tests/test_dashboard_v2_status.py`

- [ ] **Step 1: Add failing test**

Add to `DashboardV2StatusTests`:

```python
    def test_v2_status_reports_duplicate_runtime_processes(self):
        fake_processes = [
            {"name": "server_Local", "pid": 11, "path": r"C:\QuanLyXuong\server_Local.exe"},
            {"name": "server_Local", "pid": 12, "path": r"C:\QuanLyXuong\server_Local.exe"},
            {"name": "Dashboard_Local", "pid": 21, "path": r"C:\QuanLyXuong\Dashboard_Local.exe"},
        ]

        with mock.patch.object(Dashboard, "list_runtime_processes", return_value=fake_processes):
            status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        self.assertEqual(status["runtime_processes"]["server_Local"]["count"], 2)
        self.assertEqual(status["runtime_processes"]["Dashboard_Local"]["count"], 1)
        self.assertTrue(any("Duplicate process server_Local count=2" in item for item in status["warnings"]))
        self.assertEqual(status["overall"], "WARN")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status.DashboardV2StatusTests.test_v2_status_reports_duplicate_runtime_processes
```

Expected:

```text
ERROR: AttributeError
```

because `list_runtime_processes` does not exist.

- [ ] **Step 3: Add process helpers**

In `app/Dashboard.py`, near V2 status helpers, add:

```python
def list_runtime_processes():
    names = {"server_Local.exe", "Dashboard_Local.exe", "cnc_legacy_bridge.exe"}
    if os.name != "nt":
        return []
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('server_Local.exe','Dashboard_Local.exe','cnc_legacy_bridge.exe') } | Select-Object Name,ProcessId,ExecutablePath | ConvertTo-Json -Depth 3"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        rows = []
        for row in data:
            rows.append({
                "name": str(row.get("Name", "")).replace(".exe", ""),
                "pid": row.get("ProcessId"),
                "path": row.get("ExecutablePath") or "",
            })
        return rows
    except Exception:
        return []


def summarize_runtime_processes(processes):
    summary = {}
    for name in ("server_Local", "Dashboard_Local", "cnc_legacy_bridge"):
        items = [p for p in processes if p.get("name") == name]
        summary[name] = {"count": len(items), "items": items}
    return summary
```

- [ ] **Step 4: Wire into `get_v2_status_snapshot()`**

Before building final result, add:

```python
    runtime_processes = summarize_runtime_processes(list_runtime_processes())
    for proc_name, proc_info in runtime_processes.items():
        if proc_info["count"] > 1:
            warnings.append(f"Duplicate process {proc_name} count={proc_info['count']}")
```

Add to returned dict:

```python
        "runtime_processes": runtime_processes,
```

- [ ] **Step 5: Run focused test**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status.DashboardV2StatusTests.test_v2_status_reports_duplicate_runtime_processes
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit**

```powershell
git add app/Dashboard.py tests/test_dashboard_v2_status.py
git commit -m "dashboard: report duplicate runtime processes"
```

---

### Task 6: Version target va lech version hien ro tren Dashboard

**Files:**
- Modify: `app/Dashboard.py`
- Modify: `tests/test_dashboard_v2_status.py`
- Test: `tests/test_dashboard_v2_status.py`

- [ ] **Step 1: Add failing test**

Add:

```python
    def test_v2_status_warns_when_online_machine_version_is_not_expected(self):
        self.make_machine_db("InBat")
        old_versions = getattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", None)
        Dashboard.EXPECTED_MACHINE_VERSIONS = {
            "InBat": "V2.1.0_TEST",
            "InDecal": "V2.1.0_TEST",
            "CNC": "V2.1.0_TEST_CNC_BRIDGE",
        }
        self.addCleanup(lambda: setattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", old_versions))

        status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        self.assertTrue(any("InBat version V2.0.0_OUTBOX_READY != expected V2.1.0_TEST" in warning for warning in status["warnings"]))
        machine = next(item for item in status["machines"] if item["machine"] == "InBat")
        self.assertEqual(machine["expected_version"], "V2.1.0_TEST")
        self.assertFalse(machine["version_ok"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status.DashboardV2StatusTests.test_v2_status_warns_when_online_machine_version_is_not_expected
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Add expected version map**

In `app/Dashboard.py`, near constants:

```python
EXPECTED_MACHINE_VERSIONS = {
    "InBat": os.getenv("QLX_EXPECTED_INBAT_VERSION", "V2.1.0_TEST"),
    "InDecal": os.getenv("QLX_EXPECTED_INDECAL_VERSION", "V2.1.0_TEST"),
    "CNC": os.getenv("QLX_EXPECTED_CNC_VERSION", "V2.1.0_TEST_CNC_BRIDGE"),
}
```

- [ ] **Step 4: Add version comparison in status snapshot**

Inside loop over machines in `get_v2_status_snapshot()`:

```python
        expected_version = EXPECTED_MACHINE_VERSIONS.get(machine["machine"], "")
        machine["expected_version"] = expected_version
        machine["version_ok"] = (not expected_version) or machine.get("version") == expected_version
        if machine.get("online") and expected_version and machine.get("version") != expected_version:
            warnings.append(f"{machine['machine']} version {machine.get('version') or 'missing'} != expected {expected_version}")
```

- [ ] **Step 5: Update frontend version table**

In `renderV2Status(data)`, update row render:

```javascript
const versionOk = m.version_ok !== false;
const versionCellClass = versionOk ? 'version-ok' : 'version-old';
const expected = m.expected_version ? ` / cáº§n ${escapeHtml(m.expected_version)}` : '';
```

Use:

```javascript
<td class="${versionCellClass}">${escapeHtml(version)}${expected}</td>
```

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status
```

Expected:

```text
OK
```

- [ ] **Step 7: Commit**

```powershell
git add app/Dashboard.py tests/test_dashboard_v2_status.py
git commit -m "dashboard: warn on mismatched machine versions"
```

---

### Task 7: Fix auto-update observability cho 3 may

**Files:**
- Modify: `scripts/Update-WorkstationClientIfIdle.ps1`
- Modify: `tests/test_workstation_auto_update.py`
- Modify: `docs/V2_RUNBOOK.md`

- [ ] **Step 1: Add failing test**

Add to `WorkstationAutoUpdateScriptTests`:

```python
    def test_update_script_writes_version_state_after_up_to_date(self):
        result = self.run_script({"RUNNING": []})
        self.assertEqual(result.returncode, 0, result.stderr)

        result2 = self.run_script({"RUNNING": []})
        self.assertEqual(result2.returncode, 0, result2.stderr)

        state_path = os.path.join(self.local_dir, "auto_update_state.json")
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertEqual(state["lastResult"], "UP_TO_DATE")
        self.assertEqual(state["machine"], "InBat")
        self.assertIn("sourceSha256", state)
        self.assertIn("localSha256", state)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_workstation_auto_update.WorkstationAutoUpdateScriptTests.test_update_script_writes_version_state_after_up_to_date
```

Expected:

```text
FAIL
```

- [ ] **Step 3: Add update status writer**

In `scripts/Update-WorkstationClientIfIdle.ps1`, add:

```powershell
function Save-UpdateResult([string]$Path, [string]$MachineName, [string]$Result, [string]$SourceHash, [string]$LocalHash, [string]$Message) {
    if (-not $Path) { return }
    $state = Read-IdleState $Path
    $state | Add-Member -NotePropertyName "machine" -NotePropertyValue $MachineName -Force
    $state | Add-Member -NotePropertyName "lastResult" -NotePropertyValue $Result -Force
    $state | Add-Member -NotePropertyName "sourceSha256" -NotePropertyValue $SourceHash -Force
    $state | Add-Member -NotePropertyName "localSha256" -NotePropertyValue $LocalHash -Force
    $state | Add-Member -NotePropertyName "lastMessage" -NotePropertyValue $Message -Force
    $state | Add-Member -NotePropertyName "lastCheckedAt" -NotePropertyValue (Get-Date).ToString("s") -Force
    Save-IdleState $Path $state
}
```

Before each `exit 0` state (`BUSY`, `WAIT_IDLE`, `WAIT_PAUSE_QUIET`, `UP_TO_DATE`, `UPDATED`), call `Save-UpdateResult` with result matching log text. For `UP_TO_DATE`:

```powershell
Save-UpdateResult $StatePath $Machine "UP_TO_DATE" $expected $current "Already current"
```

After successful copy:

```powershell
Save-UpdateResult $StatePath $Machine "UPDATED" $expected $actual "Updated and verified"
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_workstation_auto_update
```

Expected:

```text
OK
```

- [ ] **Step 5: Update runbook**

In `docs/V2_RUNBOOK.md`, under auto-update logs, add:

```text
C:\QuanLyXuong\Client\auto_update_state.json

Can xem cac truong:
- lastResult: UP_TO_DATE / UPDATED / BUSY / WAIT_IDLE / WAIT_PAUSE_QUIET / FAILED
- sourceSha256: hash ban tren NAS
- localSha256: hash ban dang nam tren may
- lastCheckedAt: lan task chay gan nhat
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/Update-WorkstationClientIfIdle.ps1 tests/test_workstation_auto_update.py docs/V2_RUNBOOK.md
git commit -m "update: record workstation auto-update state"
```

---

### Task 8: CNC status tach bridge va NcStudio

**Files:**
- Modify: `app/cnc_legacy_bridge.py`
- Modify: `app/server.py`
- Modify: `app/Dashboard.py`
- Modify: `tests/test_cnc_legacy_bridge.py`
- Modify: `tests/test_dashboard_v2_status.py`

- [ ] **Step 1: Add bridge test for health payload**

In `tests/test_cnc_legacy_bridge.py`, add:

```python
    def test_post_ping_includes_ncstudio_health_fields(self):
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["payload"] = json
            class Response:
                def raise_for_status(self): pass
            return Response()

        with patch("cnc_legacy_bridge.requests.post", fake_post), \
             patch("cnc_legacy_bridge.read_ncstudio_health", return_value={
                 "cnc_share_online": True,
                 "ncstudio_log_mtime": "2026-07-16 08:00:00",
                 "ncstudio_state": "RUNNING",
                 "ncstudio_last_line": "normal finished",
             }):
            cnc_legacy_bridge.post_ping("http://server", r"\\CNC\CNC\CLIENT_CNC\file_history.csv")

        self.assertEqual(captured["payload"]["machine"], "CNC")
        self.assertEqual(captured["payload"]["extra"]["ncstudio_state"], "RUNNING")
        self.assertTrue(captured["payload"]["extra"]["cnc_share_online"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge.CncLegacyBridgeTests.test_post_ping_includes_ncstudio_health_fields
```

Expected:

```text
ERROR
```

- [ ] **Step 3: Extend ping payload model**

In `app/server.py`, update `PingPayload`:

```python
class PingPayload(BaseModel):
    machine: str
    version: str
    hostname: Optional[str] = None
    pid: Optional[int] = None
    start_time: Optional[str] = None
    instance_id: Optional[str] = None
    extra: Optional[dict] = None
```

In `ping_client`, after existing app_info writes:

```python
        if data.extra:
            for key, value in data.extra.items():
                conn.execute(
                    "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
                    (str(key), json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) else str(value)),
                )
```

- [ ] **Step 4: Add CNC health reader in bridge**

In `app/cnc_legacy_bridge.py`, add:

```python
def read_ncstudio_health(log_path=DEFAULT_NCSTUDIO_LOG):
    info = {
        "cnc_share_online": False,
        "ncstudio_log_mtime": "",
        "ncstudio_state": "UNKNOWN",
        "ncstudio_last_line": "",
    }
    try:
        if not os.path.exists(log_path):
            return info
        info["cnc_share_online"] = True
        mtime = datetime.fromtimestamp(os.path.getmtime(log_path))
        info["ncstudio_log_mtime"] = mtime.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = [line.strip() for line in handle.readlines() if line.strip()]
        last_line = lines[-1] if lines else ""
        info["ncstudio_last_line"] = last_line[-240:]
        if "Nc Studio exits" in last_line:
            info["ncstudio_state"] = "EXITED"
        elif (datetime.now() - mtime).total_seconds() > 900:
            info["ncstudio_state"] = "STALE"
        else:
            info["ncstudio_state"] = "RUNNING"
        return info
    except Exception as exc:
        info["ncstudio_state"] = "ERROR"
        info["ncstudio_last_line"] = str(exc)
        return info
```

Update `post_ping()` payload:

```python
        "extra": read_ncstudio_health(),
```

- [ ] **Step 5: Dashboard displays CNC fields**

In `inspect_machine_db`, after app_info load, add:

```python
            info["cnc_share_online"] = app_info.get("cnc_share_online", "")
            info["ncstudio_state"] = app_info.get("ncstudio_state", "")
            info["ncstudio_log_mtime"] = app_info.get("ncstudio_log_mtime", "")
            info["ncstudio_last_line"] = app_info.get("ncstudio_last_line", "")
```

In `get_v2_status_snapshot`, warn:

```python
        if machine["machine"] == "CNC" and machine.get("online") and machine.get("ncstudio_state") in ("EXITED", "STALE", "ERROR"):
            warnings.append(f"CNC bridge online but NcStudio {machine.get('ncstudio_state')}")
```

- [ ] **Step 6: Add dashboard test**

Add to `DashboardV2StatusTests`:

```python
    def test_cnc_bridge_online_but_ncstudio_exited_warns(self):
        self.make_machine_db("CNC")
        db_path = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('ncstudio_state', 'EXITED')")
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('ncstudio_log_mtime', '2026-07-16 08:00:00')")
        conn.commit()
        conn.close()

        status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        cnc = next(item for item in status["machines"] if item["machine"] == "CNC")
        self.assertEqual(cnc["ncstudio_state"], "EXITED")
        self.assertTrue(any("CNC bridge online but NcStudio EXITED" in item for item in status["warnings"]))
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge tests.test_dashboard_v2_status
```

Expected:

```text
OK
```

- [ ] **Step 8: Commit**

```powershell
git add app/cnc_legacy_bridge.py app/server.py app/Dashboard.py tests/test_cnc_legacy_bridge.py tests/test_dashboard_v2_status.py
git commit -m "cnc: report NcStudio health separately from bridge"
```

---

### Task 9: Docs va runbook restart sach

**Files:**
- Modify: `docs/V2_RUNBOOK.md`
- Modify: `docs/HEALTHCHECK_RUNBOOK.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update `docs/V2_RUNBOOK.md`**

Add:

```markdown
## Restart sach khi thay ban moi

Truoc khi bao "da cap nhat", kiem tra khong co process trung:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Test-QuanLyXuongHealth.ps1 -Role Server
```

Neu thay `Duplicate process`, khong deploy tiep. Chay restart runtime bang quyen Admin/NSSM:

```powershell
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Start-V2Runtime.ps1 -Restart
```

Sau restart phai thay:

```text
server_Local count=1
Dashboard_Local count=1
cnc_legacy_bridge count=1
```

Neu `Access is denied`, dung NSSM service hoac mo PowerShell Run as Administrator. Khong start them process moi khi process cu chua dung.
```

- [ ] **Step 2: Update `docs/HEALTHCHECK_RUNBOOK.md`**

Add:

```markdown
## Duplicate process

`Test-QuanLyXuongHealth.ps1 -Role Server` se canh bao neu co hon 1 process cung vai tro:

- `server_Local`
- `Dashboard_Local`
- `cnc_legacy_bridge`

Day la loi van hanh can xu ly truoc khi debug dashboard, vi co the gay log trung, ping trung, version nhay nguoc va trang thai CNC sai.
```

- [ ] **Step 3: Update changelog**

Add under `Unreleased`:

```markdown
- On dinh van hanh:
  - Unit test server khong con ghi log vao `C:\QuanLyXuong\Server_Log.txt`.
  - Healthcheck canh bao duplicate `server_Local`, `Dashboard_Local`, `cnc_legacy_bridge`.
  - Runtime/restart dashboard verify chi co 1 process sau khi start.
  - Dashboard `/api/v2_status` hien duplicate process, expected version va health CNC/NcStudio.
```

- [ ] **Step 4: Commit**

```powershell
git add docs/V2_RUNBOOK.md docs/HEALTHCHECK_RUNBOOK.md CHANGELOG.md
git commit -m "docs: document clean V2 runtime operations"
```

---

### Task 10: Verification va deploy an toan

**Files:**
- No source edit in this task.

- [ ] **Step 1: Run full test**

Run:

```powershell
python -m unittest discover -s tests
```

Expected:

```text
OK
```

- [ ] **Step 2: Run quality gate**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Test-QuanLyXuongCode.ps1
```

Expected:

```text
Quality gate OK
```

- [ ] **Step 3: Build release**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Build-Release.ps1 -Clean
```

Expected:

```text
Build complete: \\192.168.1.188\AI\Tools\dist-new
```

- [ ] **Step 4: Backup before deploy**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Backup-QuanLyXuongData.ps1
```

Expected:

```text
Backup complete
```

- [ ] **Step 5: Publish or dashboard-only deploy**

If code touched server/runtime scripts/client, use full publish path from runbook. If only dashboard UI, use dashboard-only restart. For this plan, server/runtime scripts changed, so prefer full controlled deploy:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Publish-Release.ps1
```

Expected:

```text
Publish complete
```

- [ ] **Step 6: Restart clean**

Run from elevated PowerShell on server machine:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Start-V2Runtime.ps1 -Restart
```

Expected:

```text
server_Local count=1
Dashboard_Local count=1
cnc_legacy_bridge count=1
```

- [ ] **Step 7: Verify live health**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File \\192.168.1.188\AI\Tools\scripts\Test-QuanLyXuongHealth.ps1 -Role Server
```

Expected:

```text
SUMMARY ok=
warn=0
```

Open:

```text
http://192.168.1.104:5000/api/v2_status
```

Expected:

```text
runtime_processes.server_Local.count = 1
runtime_processes.Dashboard_Local.count = 1
runtime_processes.cnc_legacy_bridge.count = 1
```

- [ ] **Step 8: Commit deploy docs if changed**

```powershell
git status --short
git push origin main
```

Expected:

```text
main -> main
```

or `Everything up-to-date` if branch already pushed.

---

## Out of Scope cho plan nay

- Khong sua lai cong thuc `%/ETA` InBat/InDecal/CNC trong chang nay.
- Khong tach lon `Dashboard.py` thanh module rieng trong chang nay.
- Khong noi QCVL production queue.
- Khong sua KiotViet/Zalo/Auto_CRM, vi V2 da chot khong dung lam luong chinh.

Sau khi plan nay xong, moi nen lap plan rieng:

1. `InBat progress correctness`: replay live PrintMon, chot feed/pass/khong xoay sai kho.
2. `Dashboard module split`: tach stats/status/preview/template de sua UI an toan hon.
3. `CNC path ETA v2`: them feedrate/Z/arc/pause vao tinh thoi gian.

---

## Self-Review 1

**Spec coverage:** Plan bao phu 4 van de da neu: duplicate process, test nhiem log live, version lech, CNC status sai nghia. Co task docs va deploy.

**Gap found:** Auto-update state cua may tram chua co cach nhin ro may da lay hash nao. Da them Task 7.

**Red-flag scan:** Khong co muc rong, khong co viec de ngo, khong co step noi chung chung. Cac code step co snippet cu the.

## Self-Review 2

**Spec coverage sau khi doc lai docs:** Master plan yeu cau rollback/backup/preflight. Da them Task 10 backup/build/verify. V2 runbook yeu cau khong restart client khi khong can; plan nay dung full deploy vi server/runtime scripts thay doi.

**Gap found:** Dashboard can hien process duplicate trong `/api/v2_status`, khong chi PowerShell healthcheck. Da them Task 5.

**Type consistency:** Ten keys dung thong nhat: `runtime_processes`, `expected_version`, `version_ok`, `ncstudio_state`.

## Self-Review 3

**Spec coverage cuoi:** Plan khong tron sang fix %/ETA, de tranh qua rong. Cac fix van hanh co thu tu an toan: test isolation -> healthcheck -> runtime guard -> dashboard status -> version/auto-update -> CNC semantic -> docs/deploy.

**Risk check:** Task 8 cham `server.py` ping payload. Vi Pydantic cho optional `extra`, client cu van gui payload cu binh thuong. Dashboard keys moi neu thieu thi rong, khong pha UI cu.

**Execution readiness:** Moi task co file, test, lenh chay, expected output, commit rieng. Co the giao subagent tung task.

