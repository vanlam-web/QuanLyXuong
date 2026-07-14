# Dashboard Compact Layout C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the live V2 Dashboard into compact Layout C with left sidebar, tabbed main area, visible attention badge, and customer count/m2 statistics from file names.

**Architecture:** Keep the existing Flask single-file dashboard and existing APIs. Add customer m2 fields to `/api/stats`, then refactor the HTML/CSS/JS inside `app/Dashboard.py` to render a compact shell without touching server or QCVL.

**Tech Stack:** Python Flask, SQLite, vanilla JS, Chart.js, PyInstaller.

---

## Current status - 2026-07-14

Layout C da len Dashboard live. Mot so quyet dinh sau da thay doi so voi plan goc:

- Tab chinh hien tai: `San xuat`, `Cho xu ly`, `Bao cao`, `He thong`.
- `Khach hang` khong con la tab rieng; da gop vao `Bao cao`.
- `He thong` gop ca log va cac nguon he thong de giam trung lap.
- Sidebar `Thong ke`:
  - `Tong | hoan thanh | loi` nam tren mot hang.
  - Bo nhan phu `Hoan thanh`/`Loi` trong o tong.
  - Tong dung so lon, mau hoan thanh/loi rieng.
  - Tung may hien hoan thanh ben trai va loi ben phai.
- `/api/stats` tra them:
  - `cancel_by_machine`
  - `cancel_bad_m2_by_machine`
  - customer detail co `cancel_by_machine` va `cancel_bad_m2_by_machine`.
- `/api/data` ho tro `limit`; UI render 20 the dau va tai tiep khi cuon/bam.
- Browser behavior yeu cau:
  - Doi filter co spinner/dang tai.
  - Request cu khong duoc ghi de request moi.
  - Console khong co error/warn lien quan app.
- Deploy dashboard-only moi nhat dung `build-specs\Dashboard.spec`, copy den:
  - `Z:\Tools\dist\Dashboard.exe`
  - `C:\QuanLyXuong\Dashboard_Local.exe`
  - `\\192.168.1.188\AI\Tools\dist\Dashboard.exe`

Verification moi nhat da dung:

```powershell
python -m unittest discover -s Z:\Tools\tests
pyinstaller --clean --distpath Z:\Tools\dist-audit --workpath Z:\Tools\build-dashboard-hotfix-work Z:\Tools\build-specs\Dashboard.spec
powershell -ExecutionPolicy Bypass -File Z:\Tools\scripts\Restart-DashboardV2.ps1
```

Hash Dashboard da deploy ngay 2026-07-14:

```text
A6D8964D0026BAF5FFA742BB2C5D87B7D01A53C4DF77AE4F935E4C4C4487831D
```

---

### Task 1: Stats Data Contract

**Files:**
- Modify: `Z:\Tools\tests\test_dashboard_v2_status.py`
- Modify: `Z:\Tools\app\Dashboard.py`

- [ ] **Step 1: Write failing tests**

Add tests that require `/api/stats` to return customer count and customer m2, and require the HTML template to include Layout C landmarks.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py -k customer`

Expected: FAIL before implementation because `customers_m2` and Layout C landmarks do not exist.

- [ ] **Step 3: Implement stats fields**

In `api_stats()`, add `m2_by_customer`, accumulate `billable_m2` per parsed customer, and return:

```python
"customers_m2": {"labels": [...], "data": [...]}
```

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py`

Expected: all tests pass.

### Task 2: Layout C HTML/CSS/JS

**Files:**
- Modify: `Z:\Tools\app\Dashboard.py`
- Modify: `Z:\Tools\tests\test_dashboard_v2_status.py`

- [ ] **Step 1: Write failing layout test**

Assert the template has:

- `compact-shell`
- `compact-sidebar`
- `compact-main`
- `main-tab-production`
- `customerChart`
- no old default `view-v2`, `view-board`, `view-erp` stacked layout as the visible primary layout

- [ ] **Step 2: Implement Layout C**

Refactor `HTML_TEMPLATE` so first viewport is:

- compact header/filter row
- left sidebar: machine status, quick stats, customer top 5
- right main: tabs `Sản xuất`, `Cần xử lý`, `Luồng`, `Khách hàng`
- default tab: production

Keep old detail modal, card preview, login modal, admin actions, and API calls.

- [ ] **Step 3: Implement JS renderers**

Add or update functions:

- `switchMainTab(tab)`
- `renderSidebarMachines(data)`
- `renderStatsSummary(data)`
- `renderCustomerSummary(data)`
- `renderCustomerChart(data)`
- `renderCompactBoard()`
- `renderAttention(filter)`

Use the same filters for all data.

- [ ] **Step 4: Verify tests**

Run: `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py`

Expected: all tests pass.

### Task 3: Build And Browser Verification

**Files:**
- Build output: `Z:\Tools\dist-dashboard-hotfix\Dashboard.exe`
- Deploy output: `C:\QuanLyXuong\Dashboard_Local.exe`
- Deploy output: `Z:\Tools\dist\Dashboard.exe`

- [ ] **Step 1: Compile**

Run:

```powershell
python -c "import py_compile,tempfile,os; c=os.path.join(tempfile.gettempdir(),'Dashboard_check.pyc'); py_compile.compile(r'Z:\Tools\app\Dashboard.py', cfile=c, doraise=True); print(c)"
```

Expected: command exits 0.

- [ ] **Step 2: Build Dashboard**

Run:

```powershell
pyinstaller --onefile --name Dashboard --distpath Z:\Tools\dist-dashboard-hotfix --workpath Z:\Tools\build-dashboard-hotfix --specpath Z:\Tools\build-dashboard-hotfix-spec --paths Z:\Tools --paths Z:\Tools\app Z:\Tools\app\Dashboard.py
```

Expected: `Z:\Tools\dist-dashboard-hotfix\Dashboard.exe` exists.

- [ ] **Step 3: Deploy Dashboard only**

Run:

```powershell
Get-Process Dashboard_Local -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Copy-Item Z:\Tools\dist-dashboard-hotfix\Dashboard.exe C:\QuanLyXuong\Dashboard_Local.exe -Force
Copy-Item Z:\Tools\dist-dashboard-hotfix\Dashboard.exe Z:\Tools\dist\Dashboard.exe -Force
Start-Process C:\QuanLyXuong\Dashboard_Local.exe -WorkingDirectory C:\QuanLyXuong -WindowStyle Hidden
```

Expected: Dashboard restarts; server remains untouched.

- [ ] **Step 4: Browser check**

Open `http://192.168.1.104:5000/` and verify:

- sidebar is visible
- main production tab is default
- attention badge is visible
- customer chart exists
- count/m2 toggle changes stats, flow chart, and customer chart
- no console errors
