# Estimated Cancel Progress Implementation Plan

**Goal:** Show nearest possible progress percent for files canceled while running, without claiming exactness when data is estimated.

**Architecture:** Keep raw DB data unchanged. Compute display-only progress in `Dashboard.py` from history timing and comparable completed jobs. Use explicit `progress_source` values: `explicit`, `estimated`, or `unknown`.

**Tech Stack:** Python, SQLite, Flask dashboard, unittest.

---

### Task 1: Progress Estimator

**Files:**
- Modify: `Z:\Tools\app\Dashboard.py`
- Test: `Z:\Tools\tests\test_dashboard_v2_status.py`

- [x] Add failing tests for `estimate_cancel_progress`.
- [x] Implement helper that uses explicit `progress_percent` first.
- [x] If no explicit percent, estimate from elapsed runtime divided by average DONE duration for same machine and similar area.
- [x] Return `None` with source `unknown` when no good baseline exists.
- [x] Run `python -m unittest Z:\Tools\tests\test_dashboard_v2_status.py`.

### Task 2: Board API Fields

**Files:**
- Modify: `Z:\Tools\app\Dashboard.py`
- Test: `Z:\Tools\tests\test_dashboard_v2_status.py`

- [x] Add `progress_percent`, `progress_source`, `progress_label`, and `estimated_bad_m2` to canceled items.
- [x] Keep suspect reprint signal out of production error stats.
- [x] Run unit tests.

### Task 3: UI Badge

**Files:**
- Modify: `Z:\Tools\app\Dashboard.py`

- [x] Show one small line on cards: `Tiến độ: 42% ước tính`, `Tiến độ: 42%`, or `Tiến độ: chưa rõ`.
- [x] Show estimated bad area when possible: `Hỏng ~4.44 m2`.
- [x] Avoid duplicate labels.
- [x] Build `Dashboard.exe`, restart runtime, verify in browser.

---

**Deployed:** 2026-07-10.

**Runtime evidence:** `/api/data` returns `KL_220X280.prt` with `Tiến độ: 72% ước tính` and `estimated_bad_m2 = 4.4352`. Browser at `http://192.168.1.104:5000/` shows the badge in `Lỗi/Hủy khi chạy`.
