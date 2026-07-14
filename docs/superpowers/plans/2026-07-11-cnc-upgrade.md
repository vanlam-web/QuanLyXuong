# CNC Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade CNC monitoring so V2 shows true CNC state, classifies CNC jobs correctly, avoids duplicate bridge/runtime processes, and prepares a safe path to native Win7 CNC client later.

**Architecture:** Keep current V1 CNC client and server-side `cnc_legacy_bridge` as the safe production path first. Add CNC health parsing from `NCSTUDIO.LOG`, send health to server `app_info`, and show separate states for LAN machine, bridge, and NcStudio. Only after this is stable, add richer CNC job classification and native Win7 client.

**Tech Stack:** Python 3, FastAPI `server.py`, Flask `Dashboard.py`, SQLite app DBs, PyInstaller runtime, Windows LAN shares, Win7 32-bit CNC machine, `unittest`.

---

## Scope

This plan only upgrades CNC inside QuanLyXuong V2.

Do not touch QCVL integration here.

Do not deploy native V2 directly to CNC until server-side bridge/dashboard are stable for at least several real production runs.

## Current Evidence

- CNC host: `CNC`, IP `192.168.1.33`, LAN share readable.
- `\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG` last line at audit: `Nc Studio exits`.
- `\\CNC\CNC\CLIENT_CNC\state_CNC.json` can still update while NcStudio is closed.
- Current dashboard `CNC DANG MO` comes from server bridge ping, not from NcStudio.
- Server had duplicate processes:
  - 2 `server_Local.exe`
  - 2 `Dashboard_Local.exe`
  - 2 `cnc_legacy_bridge.exe`
- `huong_120x240.tap` was DONE but file move was blocked by WinError 32, leaving file in root and `New Folder`.
- `5p ngang chuan dut vip1.tap` is expected stop/template, not real waste.

## Important Risks Found During Plan Review

- A normal lock file can become stale after crash or forced stop. The bridge lock must include PID and remove stale locks only when the PID is no longer alive.
- Reading `NCSTUDIO.LOG` through LAN can be slow. Bridge must read it on a separate health interval, not on every CSV polling cycle.
- Do not use live `/api/ping` against `C:\QuanLyXuong\Data\CNC.db` as the main test. Unit tests must cover storage logic first; live API check is only deploy verification.
- Build outputs are created in `dist-new` by `Build-Release.ps1`, then published to `dist` by `Publish-Release.ps1`. Deployment must not assume direct build into `dist`.
- Runtime duplicates may come from both NSSM and `Start-V2Runtime.ps1`. Startup ownership must be clarified before judging script failure.
- Decision: NSSM is the single runtime owner on boot. Current running service is `khoidongbot` (`C:\nssm\nssm.exe`, Auto, Running). `C:\nssm\KhoiDongBot.bat` and NAS copy `scripts\KhoiDongBot_V2_NSSM.bat` delegate to `Start-V2RuntimeNssm.ps1`, which keeps the server foreground and starts Dashboard/CNC bridge as children.
- Dashboard tests must use real helpers in `test_dashboard_v2_status.py`; no pseudo-code is allowed.
- Plan text and UI fallback labels should be ASCII-safe. Vietnamese display text belongs in Dashboard code after browser verification.

## Files

- Modify: `Z:\Tools\app\cnc_legacy_bridge.py`
  - Add single-instance lock.
  - Read CNC/NcStudio health.
  - Send health fields through `/api/ping`.
- Create: `Z:\Tools\app\cnc_health.py`
  - Focused parser for CNC LAN health and NcStudio log state.
- Modify: `Z:\Tools\app\server.py`
  - Accept extra optional CNC health fields in `/api/ping`.
  - Store health fields in `app_info`.
- Modify: `Z:\Tools\app\Dashboard.py`
  - Show CNC as 3 separate states: LAN machine, bridge, NcStudio.
  - Stop saying `DANG MO` for CNC when only bridge ping is alive.
  - Show move-lock and expected-stop meaning clearly.
- Modify: `Z:\Tools\scripts\Start-V2Runtime.ps1`
  - Stop duplicate runtime more safely.
  - Optionally start bridge with one instance.
- Modify: `Z:\Tools\app\tap_preview.py`
  - Add helper to count TAP lines and resolve source UNC for diagnostics.
- Modify: `Z:\Tools\app\qlx_workstation_logic.py`
  - Add pure CNC log classification helpers for Advanced line and expected stop.
- Test: `Z:\Tools\tests\test_cnc_health.py`
- Test: `Z:\Tools\tests\test_cnc_legacy_bridge.py`
- Test: `Z:\Tools\tests\test_dashboard_v2_status.py`
- Test: `Z:\Tools\tests\test_qlx_workstation_logic.py`
- Doc: `Z:\Tools\docs\AUDIT_CNC_DEEP.md`

---

### Task 1: Add CNC Health Parser

**Files:**
- Create: `Z:\Tools\app\cnc_health.py`
- Test: `Z:\Tools\tests\test_cnc_health.py`

- [ ] **Step 1: Write tests for NcStudio health states**

Create `Z:\Tools\tests\test_cnc_health.py`:

```python
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from cnc_health import read_ncstudio_health


class CncHealthTests(unittest.TestCase):
    def write_log(self, text, mtime=None):
        handle = tempfile.NamedTemporaryFile("wb", suffix=".LOG", delete=False)
        try:
            handle.write(text.encode("gbk", errors="ignore"))
            handle.close()
            if mtime is not None:
                os.utime(handle.name, (mtime, mtime))
            return handle.name
        except Exception:
            handle.close()
            os.unlink(handle.name)
            raise

    def test_detects_ncstudio_exited(self):
        path = self.write_log("M\t2026-07-11 17:45:51\tNc Studio exits\n")
        try:
            health = read_ncstudio_health(path, now_dt=datetime(2026, 7, 11, 18, 0, 0))
            self.assertEqual(health["cnc_ncstudio_state"], "EXITED")
            self.assertEqual(health["cnc_ncstudio_last_event_time"], "2026-07-11 17:45:51")
            self.assertIn("Nc Studio exits", health["cnc_ncstudio_last_line"])
        finally:
            os.unlink(path)

    def test_detects_recent_machining_as_running(self):
        path = self.write_log("M\t2026-07-11 18:01:02\tInitiate a machining task: 'D:\\CNC\\job.tap', from beginning to end\n")
        try:
            health = read_ncstudio_health(path, now_dt=datetime(2026, 7, 11, 18, 2, 0))
            self.assertEqual(health["cnc_ncstudio_state"], "RUNNING")
            self.assertEqual(health["cnc_ncstudio_current_job"], r"D:\CNC\job.tap")
        finally:
            os.unlink(path)

    def test_detects_stale_log(self):
        old_mtime = time.mktime((datetime.now() - timedelta(hours=3)).timetuple())
        path = self.write_log("M\t2026-07-11 16:00:00\tInitiate a simulation: 'D:\\CNC\\old.tap', from beginning to end\n", old_mtime)
        try:
            health = read_ncstudio_health(path, now_dt=datetime.now())
            self.assertEqual(health["cnc_ncstudio_state"], "STALE")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_cnc_health -v
```

Expected:

```text
ModuleNotFoundError: No module named 'cnc_health'
```

- [ ] **Step 3: Implement `cnc_health.py`**

Create `Z:\Tools\app\cnc_health.py`:

```python
import os
import re
from datetime import datetime

DEFAULT_NCSTUDIO_LOG = r"\\CNC\Ncstudio V5.5.60\NCSTUDIO.LOG"
STALE_AFTER_SECONDS = 20 * 60

TIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
JOB_RE = re.compile(r"'([^']+)'")


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _parse_line_time(line):
    match = TIME_RE.search(line or "")
    if not match:
        return ""
    return match.group(1)


def _parse_job(line):
    match = JOB_RE.search(line or "")
    return match.group(1) if match else ""


def _tail_lines(path, max_bytes=65536):
    with open(path, "rb") as f:
        try:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
        except OSError:
            f.seek(0)
        data = f.read()
    return data.decode("gbk", errors="ignore").splitlines()


def read_ncstudio_health(path=DEFAULT_NCSTUDIO_LOG, now_dt=None):
    now_dt = now_dt or datetime.now()
    health = {
        "cnc_ncstudio_log_path": path,
        "cnc_ncstudio_log_exists": "0",
        "cnc_ncstudio_log_mtime": "",
        "cnc_ncstudio_state": "UNKNOWN",
        "cnc_ncstudio_last_line": "",
        "cnc_ncstudio_last_event_time": "",
        "cnc_ncstudio_current_job": "",
    }

    if not os.path.exists(path):
        return health

    mtime = os.path.getmtime(path)
    health["cnc_ncstudio_log_exists"] = "1"
    health["cnc_ncstudio_log_mtime"] = _fmt_ts(mtime)

    lines = [line for line in _tail_lines(path) if line.strip()]
    important = [
        line for line in lines
        if "Initiate a machining task" in line
        or "Initiate a simulation" in line
        or "Nc Studio exits" in line
        or "正常完毕" in line
        or "中断终止" in line
        or "文件" in line
    ]
    last_line = important[-1] if important else (lines[-1] if lines else "")
    health["cnc_ncstudio_last_line"] = last_line[-500:]
    health["cnc_ncstudio_last_event_time"] = _parse_line_time(last_line)

    age_seconds = (now_dt - datetime.fromtimestamp(mtime)).total_seconds()
    if "Nc Studio exits" in last_line:
        health["cnc_ncstudio_state"] = "EXITED"
    elif age_seconds > STALE_AFTER_SECONDS:
        health["cnc_ncstudio_state"] = "STALE"
    elif "Initiate a machining task" in last_line:
        health["cnc_ncstudio_state"] = "RUNNING"
        health["cnc_ncstudio_current_job"] = _parse_job(last_line)
    else:
        health["cnc_ncstudio_state"] = "IDLE_OR_UNKNOWN"

    return health
```

- [ ] **Step 4: Run test and verify it passes**

Run:

```powershell
python -m unittest tests.test_cnc_health -v
```

Expected:

```text
OK
```

---

### Task 2: Add Single-Instance Lock to CNC Bridge

**Files:**
- Modify: `Z:\Tools\app\cnc_legacy_bridge.py`
- Test: `Z:\Tools\tests\test_cnc_legacy_bridge.py`

- [ ] **Step 1: Add failing lock tests**

Append to `Z:\Tools\tests\test_cnc_legacy_bridge.py`:

```python
import tempfile

from cnc_legacy_bridge import acquire_lock, release_lock, is_pid_running


class CncLegacyBridgeLockTests(unittest.TestCase):
    def test_lock_blocks_second_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "bridge.lock")
            first = acquire_lock(lock_path)
            self.assertTrue(first)
            second = acquire_lock(lock_path)
            self.assertFalse(second)
            release_lock(lock_path)
            third = acquire_lock(lock_path)
            self.assertTrue(third)
            release_lock(lock_path)

    def test_stale_lock_is_replaced_when_pid_is_dead(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "bridge.lock")
            with open(lock_path, "w", encoding="utf-8") as f:
                f.write("999999 2026-07-11 10:00:00\n")
            self.assertFalse(is_pid_running(999999))
            self.assertTrue(acquire_lock(lock_path))
            release_lock(lock_path)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge -v
```

Expected:

```text
ImportError: cannot import name 'acquire_lock'
```

- [ ] **Step 3: Implement lock helpers**

In `Z:\Tools\app\cnc_legacy_bridge.py`, add near constants:

```python
DEFAULT_LOCK = r"C:\QuanLyXuong\Data\cnc_legacy_bridge.lock"
_LOCK_HANDLE = None
```

Add functions:

```python
def is_pid_running(pid):
    try:
        if int(pid) <= 0:
            return False
        import subprocess
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            shell=False,
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _read_lock_pid(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.read().strip().split()[0]
        return int(first)
    except Exception:
        return 0


def acquire_lock(path):
    global _LOCK_HANDLE
    if _LOCK_HANDLE:
        return True
    if os.path.exists(path):
        pid = _read_lock_pid(path)
        if pid and not is_pid_running(pid):
            try:
                os.remove(path)
            except Exception:
                return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        _LOCK_HANDLE = os.fdopen(fd, "w", encoding="utf-8")
        _LOCK_HANDLE.write(f"{os.getpid()} {now()}\n")
        _LOCK_HANDLE.flush()
        return True
    except FileExistsError:
        return False


def release_lock(path):
    global _LOCK_HANDLE
    if _LOCK_HANDLE:
        try:
            _LOCK_HANDLE.close()
        except Exception:
            pass
        _LOCK_HANDLE = None
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
```

Add CLI argument:

```python
parser.add_argument("--lock", default=DEFAULT_LOCK)
```

At start of `main()` after `args = parser.parse_args()`:

```python
if not acquire_lock(args.lock):
    print_log(f"Another CNC legacy bridge is already running: {args.lock}")
    return
```

Wrap main loop:

```python
try:
    state = load_state(args.state)
    while True:
        try:
            state = run_once(args, state)
            save_state(args.state, state)
        except Exception as exc:
            print_log(f"Bridge error: {exc}")
        if not args.loop:
            break
        time.sleep(max(2, args.interval))
finally:
    release_lock(args.lock)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge -v
```

Expected:

```text
OK
```

---

### Task 3: Send CNC Health From Bridge

**Files:**
- Modify: `Z:\Tools\app\cnc_legacy_bridge.py`
- Test: `Z:\Tools\tests\test_cnc_legacy_bridge.py`

- [ ] **Step 1: Add test for ping payload**

Append:

```python
from cnc_legacy_bridge import build_ping_payload


class CncLegacyBridgePingTests(unittest.TestCase):
    def test_build_ping_payload_includes_health_fields(self):
        payload = build_ping_payload({
            "cnc_ncstudio_state": "EXITED",
            "cnc_ncstudio_log_mtime": "2026-07-11 17:45:51",
        })
        self.assertEqual(payload["machine"], "cnc")
        self.assertEqual(payload["version"], "V2.0.2_CNC_LEGACY_BRIDGE")
        self.assertEqual(payload["hostname"], "CNC qua bridge V1")
        self.assertEqual(payload["cnc_ncstudio_state"], "EXITED")
        self.assertEqual(payload["cnc_ncstudio_log_mtime"], "2026-07-11 17:45:51")
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge -v
```

Expected:

```text
ImportError: cannot import name 'build_ping_payload'
```

- [ ] **Step 3: Implement payload builder**

In `Z:\Tools\app\cnc_legacy_bridge.py`, import:

```python
from cnc_health import read_ncstudio_health
```

Add:

```python
def build_ping_payload(health=None):
    payload = {
        "machine": "cnc",
        "version": BRIDGE_VERSION,
        "hostname": "CNC qua bridge V1",
        "cnc_bridge_host": socket.gethostname(),
        "cnc_bridge_source": DEFAULT_HISTORY,
    }
    if health:
        payload.update(health)
    return payload
```

Change `post_ping`:

```python
def post_ping(api_base, source_path, health=None):
    payload = build_ping_payload(health)
    payload["cnc_bridge_source"] = source_path
    res = requests.post(f"{api_base}/api/ping", json=payload, timeout=5)
    res.raise_for_status()
    print_log(f"Ping V2 OK from {source_path}")
```

Change `run_once`:

```python
last_health_read = float(state.get("last_health_read_ts") or 0)
health = state.get("last_health") or {}
if time.time() - last_health_read >= args.health_interval:
    health = read_ncstudio_health()
    state["last_health"] = health
    state["last_health_read_ts"] = time.time()
post_ping(args.api, args.history, health)
```

Add CLI argument:

```python
parser.add_argument("--health-interval", type=int, default=60)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_cnc_legacy_bridge tests.test_cnc_health -v
```

Expected:

```text
OK
```

---

### Task 4: Store CNC Health in Server `app_info`

**Files:**
- Modify: `Z:\Tools\app\server.py`
- Test: `Z:\Tools\tests\test_server_ping_health.py`

- [ ] **Step 1: Add server ping model fields**

In `Z:\Tools\app\server.py`, change `PingPayload`:

```python
class PingPayload(BaseModel):
    machine: str
    version: str
    hostname: Optional[str] = None
    cnc_bridge_host: Optional[str] = None
    cnc_bridge_source: Optional[str] = None
    cnc_ncstudio_log_path: Optional[str] = None
    cnc_ncstudio_log_exists: Optional[str] = None
    cnc_ncstudio_log_mtime: Optional[str] = None
    cnc_ncstudio_state: Optional[str] = None
    cnc_ncstudio_last_line: Optional[str] = None
    cnc_ncstudio_last_event_time: Optional[str] = None
    cnc_ncstudio_current_job: Optional[str] = None
```

- [ ] **Step 2: Store only known health keys**

Create helper near `PingPayload`:

```python
CNC_PING_INFO_KEYS = (
    "cnc_bridge_host",
    "cnc_bridge_source",
    "cnc_ncstudio_log_path",
    "cnc_ncstudio_log_exists",
    "cnc_ncstudio_log_mtime",
    "cnc_ncstudio_state",
    "cnc_ncstudio_last_line",
    "cnc_ncstudio_last_event_time",
    "cnc_ncstudio_current_job",
)


def ping_extra_app_info(data):
    rows = []
    for key in CNC_PING_INFO_KEYS:
        value = getattr(data, key, None)
        if value is not None:
            rows.append((key, str(value)))
    return rows
```

In `/api/ping`, after hostname insert:

```python
        for key, value in ping_extra_app_info(data):
            conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)", (key, value))
```

- [ ] **Step 3: Add pure unit test for stored keys**

Create `Z:\Tools\tests\test_server_ping_health.py`:

```python
import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from server import PingPayload, ping_extra_app_info


class ServerPingHealthTests(unittest.TestCase):
    def test_ping_extra_app_info_keeps_known_cnc_fields(self):
        data = PingPayload(
            machine="cnc",
            version="TEST",
            hostname="CNC qua bridge V1",
            cnc_ncstudio_state="EXITED",
            cnc_ncstudio_log_mtime="2026-07-11 17:45:51",
        )
        rows = dict(ping_extra_app_info(data))
        self.assertEqual(rows["cnc_ncstudio_state"], "EXITED")
        self.assertEqual(rows["cnc_ncstudio_log_mtime"], "2026-07-11 17:45:51")
        self.assertNotIn("hostname", rows)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run unit test**

Run:

```powershell
python -m unittest tests.test_server_ping_health -v
```

Expected:

```text
OK
```

- [ ] **Step 5: Manual verify via API after deploy only**

Run after build/deploy only, because it writes live `C:\QuanLyXuong\Data\CNC.db`:

```powershell
$body = @{
  machine = "cnc"
  version = "TEST"
  hostname = "CNC qua bridge V1"
  cnc_ncstudio_state = "EXITED"
  cnc_ncstudio_log_mtime = "2026-07-11 17:45:51"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ping" -Method Post -ContentType "application/json" -Body $body
```

Expected:

```text
status : ok
```

Then check DB:

```powershell
python -c "import sqlite3; c=sqlite3.connect(r'C:\QuanLyXuong\Data\CNC.db'); print(dict(c.execute('select key,value from app_info').fetchall()))"
```

Expected keys include:

```text
cnc_ncstudio_state
cnc_ncstudio_log_mtime
```

---

### Task 5: Show True CNC Status on Dashboard

**Files:**
- Modify: `Z:\Tools\app\Dashboard.py`
- Test: `Z:\Tools\tests\test_dashboard_v2_status.py`

- [ ] **Step 1: Add failing test for CNC bridge vs NcStudio**

In `Z:\Tools\tests\test_dashboard_v2_status.py`, add a test using the existing helpers in that file:

```python
def test_cnc_v2_status_separates_bridge_from_ncstudio(self):
    self.make_machine_db("CNC")
    db_path = os.path.join(self.temp_dir.name, "CNC.db")
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('version', 'V2.0.2_CNC_LEGACY_BRIDGE')")
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('hostname', 'CNC qua bridge V1')")
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('last_ping', ?)", (Dashboard.now(),))
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_bridge_host', 'SERVER-PC')")
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_state', 'EXITED')")
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_log_mtime', '2026-07-11 17:45:51')")
    conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_last_event_time', '2026-07-11 17:45:51')")
    conn.commit()
    conn.close()

    snapshot = Dashboard.get_v2_status_snapshot(self.temp_dir.name)
    cnc = next(m for m in snapshot["machines"] if m["machine"] == "CNC")
    self.assertTrue(cnc["online"])
    self.assertEqual(cnc["cnc_ncstudio_state"], "EXITED")
    self.assertIn("NcStudio", cnc["online_label"])
    self.assertNotEqual(cnc["online_label"], "DANG MO")
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status -v
```

Expected:

```text
KeyError: 'cnc_ncstudio_state'
```

- [ ] **Step 3: Load CNC health fields in status snapshot**

In `Dashboard.py`, inside `inspect_machine_db`, after `app_info = dict(...)`, add:

```python
            for key in (
                "cnc_bridge_host",
                "cnc_bridge_source",
                "cnc_ncstudio_log_path",
                "cnc_ncstudio_log_exists",
                "cnc_ncstudio_log_mtime",
                "cnc_ncstudio_state",
                "cnc_ncstudio_last_line",
                "cnc_ncstudio_last_event_time",
                "cnc_ncstudio_current_job",
            ):
                info[key] = app_info.get(key, "")
```

- [ ] **Step 4: Change CNC label logic**

After existing online label logic, add:

```python
            if machine == "CNC":
                state = info.get("cnc_ncstudio_state") or ""
                last_event = info.get("cnc_ncstudio_last_event_time") or info.get("cnc_ncstudio_log_mtime") or ""
                if state == "EXITED":
                    info["online_label"] = f"BRIDGE MO / NcStudio DA THOAT {last_event}".strip()
                elif state == "RUNNING":
                    info["online_label"] = "BRIDGE MO / NcStudio DANG CHAY"
                elif state == "STALE":
                    info["online_label"] = "BRIDGE MO / NcStudio KHONG CO LOG MOI"
                elif info["online"]:
                    info["online_label"] = "BRIDGE MO / CNC CHUA RO"
```

- [ ] **Step 5: Update dashboard machine card UI**

In JS rendering for V2 status machine cards, for CNC add fields:

```javascript
const cncExtra = m.machine === "CNC" ? `
  <div class="machine-extra">
    <div><span>Bridge</span><b>${escapeHtml(m.cnc_bridge_host || 'dang ping qua server')}</b></div>
    <div><span>NcStudio</span><b>${escapeHtml(m.cnc_ncstudio_state || 'chua ro')}</b></div>
    <div><span>Log NcStudio</span><b>${escapeHtml(m.cnc_ncstudio_log_mtime || 'chua doc duoc')}</b></div>
  </div>
` : '';
```

Place `cncExtra` inside the card below normal status lines.

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m unittest tests.test_dashboard_v2_status -v
```

Expected:

```text
OK
```

---

### Task 6: Classify CNC Expected Stop and Move-After-DONE More Strictly

**Files:**
- Modify: `Z:\Tools\app\qlx_workstation_logic.py`
- Modify: `Z:\Tools\app\Dashboard.py`
- Test: `Z:\Tools\tests\test_qlx_workstation_logic.py`
- Test: `Z:\Tools\tests\test_dashboard_v2_status.py`

- [ ] **Step 1: Add pure logic tests**

Append to `test_qlx_workstation_logic.py`:

```python
from qlx_workstation_logic import parse_cnc_advanced_line, is_cnc_expected_stop_name


def test_cnc_advanced_line_extracts_end_line(self):
    line = "M\t2026-07-11 15:43:31\tInitiate a machining task (Advanced): 'D:\\CNC\\Luu\\5p ngang chuan dut vip1.tap', from <first line> to L194"
    info = parse_cnc_advanced_line(line)
    self.assertEqual(info["path"], r"D:\CNC\Luu\5p ngang chuan dut vip1.tap")
    self.assertEqual(info["end_line"], 194)


def test_cnc_expected_stop_name(self):
    self.assertTrue(is_cnc_expected_stop_name("5p ngang chuan dut vip1.tap"))
    self.assertFalse(is_cnc_expected_stop_name("huong_120x240.tap"))
```

- [ ] **Step 2: Implement pure helpers**

In `qlx_workstation_logic.py`:

```python
import re

CNC_ADVANCED_RE = re.compile(r"'([^']+)'.*?\bto\s+L(\d+)", re.IGNORECASE)


def parse_cnc_advanced_line(line: str) -> dict:
    match = CNC_ADVANCED_RE.search(line or "")
    if not match:
        return {"path": "", "end_line": None}
    return {"path": match.group(1), "end_line": int(match.group(2))}


def is_cnc_expected_stop_name(file_name: str) -> bool:
    normalized = (file_name or "").lower()
    return "ngang chuan dut" in normalized or "chuan dut" in normalized
```

- [ ] **Step 3: Dashboard classification**

In `Dashboard.py`, keep existing `is_cnc_expected_stop`, but make it call same naming rule or match:

```python
def is_cnc_expected_stop(machine, file_name):
    if str(machine or "").strip().upper() != "CNC":
        return False
    normalized = str(file_name or "").lower()
    return "chuan dut" in normalized or "ngang chuan dut" in normalized
```

In `classify_deleted_job`, keep:

```python
if is_cnc_expected_stop(machine, file_name):
    return {
        "type": "cnc_expected_stop",
        "label": "CNC file mẫu dừng đúng điểm cắt",
        "is_production_error": False,
        "progress_percent": None,
    }
```

- [ ] **Step 4: Tests**

Run:

```powershell
python -m unittest tests.test_qlx_workstation_logic tests.test_dashboard_v2_status -v
```

Expected:

```text
OK
```

---

### Task 7: Add CNC TAP Diagnostics for Preview and Percent

**Files:**
- Modify: `Z:\Tools\app\tap_preview.py`
- Test: `Z:\Tools\tests\test_tap_preview.py`

- [ ] **Step 1: Add tests**

Append:

```python
from tap_preview import count_tap_lines, estimate_line_progress


def test_count_tap_lines(self):
    path = self.write_tap("G0X0Y0\nG1X10Y0\nM30\n")
    try:
        self.assertEqual(count_tap_lines(path), 3)
    finally:
        os.unlink(path)


def test_estimate_line_progress_caps_at_100(self):
    self.assertEqual(estimate_line_progress(194, 195), 99)
    self.assertEqual(estimate_line_progress(300, 195), 100)
    self.assertIsNone(estimate_line_progress(None, 195))
```

- [ ] **Step 2: Implement helpers**

In `tap_preview.py`:

```python
def count_tap_lines(path):
    count = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def estimate_line_progress(end_line, total_lines):
    if end_line is None or not total_lines:
        return None
    value = int(round((float(end_line) / float(total_lines)) * 100))
    return max(0, min(100, value))
```

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m unittest tests.test_tap_preview -v
```

Expected:

```text
OK
```

---

### Task 8: Improve Runtime Start Script Against Duplicates and NSSM Ownership

**Files:**
- Modify: `Z:\Tools\scripts\Start-V2Runtime.ps1`
- Create/Modify: `Z:\Tools\scripts\Start-V2RuntimeNssm.ps1`
- Inspect: `Z:\Tools\scripts\KhoiDongBot_V2_NSSM.bat`

- [ ] **Step 1: Check runtime ownership before changing start behavior**

Run:

```powershell
nssm status QuanLyXuongV2 2>$null
nssm status QuanLyXuong 2>$null
Get-CimInstance Win32_Process -Filter "name = 'server_Local.exe' or name = 'Dashboard_Local.exe' or name = 'cnc_legacy_bridge.exe'" |
  Select-Object ProcessId, Name, CommandLine
```

Expected:

```text
Know whether NSSM or Start-V2Runtime.ps1 owns startup.
```

Rule:

```text
Only one owner may start server/Dashboard/bridge.
If NSSM owns startup, Start-V2Runtime.ps1 should be used by NSSM script or manual deploy, not as another always-on launcher.
```

- [ ] **Step 2: Stop CNC bridge exe explicitly**

Add to restart block:

```powershell
    Stop-IfRunning "cnc_legacy_bridge"
```

- [ ] **Step 3: Add process check after start**

After starting processes:

```powershell
function Show-ProcessCount([string]$ProcessName) {
    $items = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
    Write-Host "$ProcessName count=$($items.Count)"
    foreach ($item in $items) {
        Write-Host "  pid=$($item.Id) path=$($item.Path)"
    }
}

Show-ProcessCount "server_Local"
Show-ProcessCount "Dashboard_Local"
Show-ProcessCount "cnc_legacy_bridge"
```

- [ ] **Step 4: Manual test in safe window**

Run only when production accepts restart:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Start-V2Runtime.ps1" -Restart
```

Expected:

```text
server_Local count=1
Dashboard_Local count=1
cnc_legacy_bridge count=1
```

If NSSM starts another server, note it and move service ownership to NSSM or script, not both.

---

### Task 9: Build and Deploy Bridge/Dashboard Safely

**Files:**
- Build outputs: `Z:\Tools\dist-new`
- Published runtime dist: `Z:\Tools\dist`
- Local runtime: `C:\QuanLyXuong`

- [ ] **Step 1: Run full tests**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected:

```text
OK
```

- [ ] **Step 2: Compile touched Python**

Run:

```powershell
python -m py_compile app\cnc_health.py app\cnc_legacy_bridge.py app\server.py app\Dashboard.py app\tap_preview.py app\qlx_workstation_logic.py
```

Expected: no output.

- [ ] **Step 3: Build release into `dist-new`**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Build-Release.ps1"
```

Expected outputs:

```text
Z:\Tools\dist-new\server.exe
Z:\Tools\dist-new\Dashboard.exe
Z:\Tools\dist-new\cnc_legacy_bridge.exe
```

- [ ] **Step 4: Test built executables**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Test-BuiltExecutables.ps1"
```

Expected:

```text
All required built executables pass smoke test.
```

- [ ] **Step 5: Publish release to `dist` with rollback backup**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Publish-Release.ps1" -ReleaseName "cnc-health-v2"
```

Expected:

```text
Release copied to Z:\Tools\dist
Rollback saved under Z:\Tools\releases
```

- [ ] **Step 6: Deploy during safe moment**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Start-V2Runtime.ps1" -Restart
```

Expected:

```text
V2 runtime started.
server_Local count=1
Dashboard_Local count=1
cnc_legacy_bridge count=1
```

- [ ] **Step 7: Verify dashboard API**

Run:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v2_status" -TimeoutSec 5 | ConvertTo-Json -Depth 6
```

Expected CNC fields:

```text
cnc_ncstudio_state
cnc_ncstudio_log_mtime
cnc_bridge_host
```

- [ ] **Step 8: Verify browser**

Open:

```text
http://192.168.1.104:5000/
```

Expected:

```text
CNC card shows:
- Bridge V2
- May CNC LAN
- NcStudio
```

---

### Task 10: Prepare Native Win7 CNC Client, No Deployment Yet

**Files:**
- Modify later: `Z:\Tools\app\QuanLyXuong.py`
- Create later: `Z:\Tools\docs\CNC_WIN7_NATIVE_CLIENT.md`

- [ ] **Step 1: Document target**

Create `Z:\Tools\docs\CNC_WIN7_NATIVE_CLIENT.md`:

```markdown
# CNC Win7 Native Client

Goal: run native V2 on CNC Win7 32-bit after bridge path is stable.

Requirements:
- Python 3.6 or 3.8 32-bit build.
- No heavy new packages.
- Read `C:\Program Files\Weihong\Ncstudio V5.5.60\Ncstudio.log`.
- Write local outbox in `C:\QuanLyXuong\Data\outbox`.
- Send events to server when LAN OK.
- Keep server-side legacy bridge as fallback for 1-2 weeks.

Deploy rule:
- Do not replace V1 CNC client until dashboard can distinguish bridge/NcStudio health correctly.
- Test with real CNC operator present.
```

- [ ] **Step 2: Do not deploy native client**

No build, no copy to CNC in this task.

---

## Verification Checklist

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python -m py_compile app\cnc_health.py app\cnc_legacy_bridge.py app\server.py app\Dashboard.py app\tap_preview.py app\qlx_workstation_logic.py` passes.
- [ ] `C:\QuanLyXuong\Data\CNC.db app_info` contains CNC health keys.
- [ ] Dashboard no longer says plain `DANG MO` for CNC when only bridge ping is alive.
- [ ] Duplicate bridge process blocked.
- [ ] `5p ngang chuan dut vip1.tap` not counted as production waste.
- [ ] Move-lock after DONE shown as file-management issue, not active cutting.
- [ ] No native CNC client deployed yet.

## Rollback Plan

If dashboard/server upgrade fails:

1. Stop runtime only after confirming this is a rollback window:

```powershell
Get-Process server_Local,Dashboard_Local,cnc_legacy_bridge -ErrorAction SilentlyContinue | Stop-Process -Force
```

2. Roll back to previous release backup:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Rollback-Release.ps1"
```

3. Start old runtime:

```powershell
powershell -ExecutionPolicy Bypass -File "Z:\Tools\scripts\Start-V2Runtime.ps1" -Restart
```

4. Confirm:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v2_status" -TimeoutSec 5
```

## Execution Order

1. Task 1: health parser.
2. Task 2: bridge lock.
3. Task 3: bridge sends CNC health.
4. Task 4: server stores health.
5. Task 5: dashboard shows true CNC state.
6. Task 6: CNC expected stop/move classification.
7. Task 7: TAP diagnostics.
8. Task 8: runtime duplicate guard.
9. Task 9: build/deploy safe.
10. Task 10: native Win7 notes only.

## Self-Review

- Spec coverage: Covers CNC LAN, NcStudio log, duplicate bridge, dashboard status, expected stop, move lock, TAP diagnostics, safe deploy, native Win7 later.
- Placeholder scan: No TBD/TODO remains.
- Type consistency: CNC health keys use `cnc_*` strings in bridge, server, dashboard.
- Risk check: First deploy changes run on server side only. CNC Win7 native deployment is explicitly delayed.
