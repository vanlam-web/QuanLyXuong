import os
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import Dashboard
from qlx_outbox import EventOutbox


class DashboardV2StatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def make_machine_db(self, machine):
        db_path = os.path.join(self.temp_dir.name, f"{machine}.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE files (
                file_hash TEXT PRIMARY KEY,
                file_name TEXT,
                file_path TEXT,
                machine TEXT,
                job_type TEXT,
                status TEXT,
                created_time TEXT,
                updated_time TEXT,
                zalo_sent INTEGER,
                run_count INTEGER,
                history TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-1', 'job.tif', 'D:\\job.tif', ?, 'EXPORT', 'EXPORTED', '2026-07-09 08:00:00', '2026-07-09 08:01:00', 0, 1, '[]')
            """,
            (machine,),
        )
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-2', 'today.tif', 'D:\\today.tif', ?, 'EXPORT', 'RIP', ?, ?, 0, 1, '[]')
            """,
            (machine, Dashboard.now(), Dashboard.now()),
        )
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-3', 'done.tif', 'D:\\done.tif', ?, 'EXPORT', 'DONE', ?, ?, 0, 1, '[]')
            """,
            (machine, Dashboard.now(), Dashboard.now()),
        )
        conn.execute("CREATE TABLE app_info (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO app_info (key, value) VALUES ('version', 'V2.0.0_OUTBOX_READY')")
        conn.execute("INSERT INTO app_info (key, value) VALUES ('last_ping', ?)", (Dashboard.now(),))
        conn.execute("INSERT INTO app_info (key, value) VALUES ('hostname', 'test-pc')")
        conn.execute("INSERT INTO app_info (key, value) VALUES ('pid', '1234')")
        conn.execute("INSERT INTO app_info (key, value) VALUES ('start_time', '2026-07-13 16:00:00')")
        conn.execute("INSERT INTO app_info (key, value) VALUES ('instance_id', 'test-instance')")
        conn.commit()
        conn.close()

    def test_v2_status_reads_machine_db_and_outbox(self):
        self.make_machine_db("InBat")
        outbox = EventOutbox(os.path.join(self.temp_dir.name, "agent_outbox_inbat.db"))
        outbox.enqueue({"machine": "inbat", "path": "D:\\job.tif", "event_type": "EXPORT"})

        status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        self.assertEqual(status["overall"], "WARN")
        self.assertEqual(status["machines"][0]["machine"], "InBat")
        self.assertEqual(status["machines"][0]["total"], 3)
        self.assertEqual(status["machines"][0]["active"], 0)
        self.assertEqual(status["machines"][0]["queued_today"], 1)
        self.assertEqual(status["machines"][0]["unfinished_today"], 1)
        self.assertEqual(status["machines"][0]["old_active"], 1)
        self.assertEqual(status["machines"][0]["done_today"], 1)
        self.assertEqual(status["machines"][0]["version"], "V2.0.0_OUTBOX_READY")
        self.assertTrue(status["machines"][0]["online"])
        self.assertEqual(status["machines"][0]["hostname"], "test-pc")
        self.assertEqual(status["machines"][0]["pid"], "1234")
        self.assertEqual(status["machines"][0]["instance_id"], "test-instance")
        self.assertEqual(status["outboxes"][0]["pending"], 1)
        self.assertTrue(any("pending=1" in warning for warning in status["warnings"]))

    def test_v2_status_reads_cnc_bridge_health_fields(self):
        self.make_machine_db("CNC")
        db_path = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_state', 'RUNNING')")
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_log_mtime', '2026-07-13 13:50:32')")
        conn.execute("INSERT OR REPLACE INTO app_info (key, value) VALUES ('cnc_ncstudio_current_job', 'D:\\CNC\\job.tap')")
        conn.commit()
        conn.close()

        status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        cnc = next(item for item in status["machines"] if item["machine"] == "CNC")
        self.assertEqual(cnc["cnc_ncstudio_state"], "RUNNING")
        self.assertEqual(cnc["cnc_ncstudio_log_mtime"], "2026-07-13 13:50:32")
        self.assertEqual(cnc["cnc_ncstudio_current_job"], "D:\\CNC\\job.tap")

    def test_v2_status_reports_duplicate_runtime_processes(self):
        self.make_machine_db("InBat")
        old_expected = getattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", None)
        Dashboard.EXPECTED_MACHINE_VERSIONS = {
            "InBat": "V2.1.0_TEST",
            "InDecal": "V2.1.0_TEST",
            "CNC": "V2.1.0_TEST_CNC_BRIDGE",
        }
        self.addCleanup(lambda: setattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", old_expected))

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

    def test_v2_status_log_tail_keeps_more_context(self):
        log_path = os.path.join(self.temp_dir.name, "Server_Log.txt")
        with open(log_path, "w", encoding="utf-8") as handle:
            for index in range(250):
                handle.write(f"[2026-07-14 18:00:{index % 60:02d}] line-{index:03d}\n")

        with mock.patch.object(Dashboard, "SERVER_LOG_FILE", log_path), \
             mock.patch.object(Dashboard, "LOG_FILE", os.path.join(self.temp_dir.name, "missing-dashboard.log")), \
             mock.patch.object(Dashboard, "MACHINE_LOG_FILE", os.path.join(self.temp_dir.name, "missing-machine.log")), \
             mock.patch.object(Dashboard, "QCVL_BRIDGE_LOG_FILE", os.path.join(self.temp_dir.name, "missing-qcvl.log")):
            status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        server_log = next(item for item in status["logs"] if item["name"] == "server")
        self.assertEqual(len(server_log["tail"]), Dashboard.SYSTEM_LOG_TAIL_LINES)
        self.assertEqual(server_log["tail"][0], "[2026-07-14 18:00:50] line-050")
        self.assertEqual(server_log["tail"][-1], "[2026-07-14 18:00:09] line-249")

    def test_v2_status_warns_when_online_machine_version_is_not_expected(self):
        self.make_machine_db("InBat")
        old_expected = getattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", None)
        Dashboard.EXPECTED_MACHINE_VERSIONS = {
            "InBat": "V2.1.0_TEST",
            "InDecal": "V2.1.0_TEST",
            "CNC": "V2.1.0_TEST_CNC_BRIDGE",
        }
        self.addCleanup(lambda: setattr(Dashboard, "EXPECTED_MACHINE_VERSIONS", old_expected))

        status = Dashboard.get_v2_status_snapshot(self.temp_dir.name)

        self.assertTrue(any("InBat version V2.0.0_OUTBOX_READY != expected V2.1.0_TEST" in warning for warning in status["warnings"]))
        machine = next(item for item in status["machines"] if item["machine"] == "InBat")
        self.assertEqual(machine["expected_version"], "V2.1.0_TEST")
        self.assertFalse(machine["version_ok"])

    def test_v2_status_separates_waiting_files_from_machine_running(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        today = Dashboard.now()
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-printing', 'printing.prn', 'D:\\printing.prn', 'InDecal', 'PRINTING', 'PRINTING', ?, ?, 0, 1, '[]')
            """,
            (today, today),
        )
        conn.commit()
        conn.close()

        info = Dashboard.inspect_machine_db("InDecal", self.temp_dir.name)

        self.assertEqual(info["active"], 1)
        self.assertEqual(info["running"], 1)
        self.assertEqual(info["queued_today"], 1)
        self.assertEqual(info["unfinished_today"], 2)

    def test_api_data_limited_hides_previous_day_work_resolved_by_later_done(self):
        self.make_machine_db("InDecal")
        self.make_machine_db("CNC")
        for machine in ("InDecal", "CNC"):
            db_path = os.path.join(self.temp_dir.name, f"{machine}.db")
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM files")
            conn.commit()
            conn.close()

        indecal_db = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(indecal_db)
        conn.executemany(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES (?, ?, ?, 'InDecal', 'PRINTING', ?, ?, ?, 0, 1, ?)
            """,
            [
                (
                    "old-rip",
                    "18~loi_decal_70x25.prn",
                    r"D:\2026-07-14\18~loi_decal_70x25.prn",
                    "RIP",
                    "2026-07-14 17:07:02",
                    "2026-07-14 17:07:02",
                    "[]",
                ),
                (
                    "new-done",
                    "18~loi_decal_70x25.prn",
                    r"D:\2026-07-14\18~loi_decal_70x25.prn",
                    "DONE",
                    "2026-07-15 08:03:43",
                    "2026-07-15 08:03:43",
                    json.dumps([{"status": "DONE", "time": "2026-07-15 08:03:43", "event": "In xong"}]),
                ),
            ],
        )
        conn.commit()
        conn.close()

        cnc_db = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(cnc_db)
        conn.execute("ALTER TABLE files ADD COLUMN machine_meta_json TEXT")
        conn.executemany(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES (?, ?, ?, 'CNC', 'CUTTING', ?, ?, ?, 0, 1, ?)
            """,
            [
                (
                    "old-pause",
                    "VCTT_F5_120X50.tap",
                    r"D:\CNC\2026-07-14\VCTT_F5_120X50.tap",
                    "PAUSE",
                    "2026-07-14 17:12:02",
                    "2026-07-14 17:35:45",
                    json.dumps([
                        {"status": "CUTTING", "time": "2026-07-14 17:12:02", "event": "CUTTING"},
                        {"status": "PAUSED", "time": "2026-07-14 17:35:45", "event": "PAUSE"},
                    ]),
                ),
                (
                    "old-delete",
                    "VCTT_F5_120X50.tap",
                    r"D:\CNC\2026-07-14\VCTT_F5_120X50.tap",
                    "DELETED",
                    "2026-07-14 17:12:02",
                    "2026-07-14 17:35:31",
                    json.dumps([
                        {"status": "CUTTING", "time": "2026-07-14 17:12:02", "event": "CUTTING"},
                        {
                            "status": "DELETED",
                            "time": "2026-07-14 17:35:31",
                            "event": "DELETE",
                            "old_status": "CUTTING",
                            "cancel_type": "production_cancel",
                        },
                    ]),
                ),
                (
                    "new-done",
                    "vctt_f5_120x50.tap",
                    r"D:\CNC\2026-07-15\vctt_f5_120x50.tap",
                    "DONE",
                    "2026-07-15 07:42:26",
                    "2026-07-15 07:46:00",
                    json.dumps([{"status": "DONE", "time": "2026-07-15 07:46:00", "event": "Cắt xong"}]),
                ),
            ],
        )
        cnc_size_meta = json.dumps({"width_mm": 1182.0, "height_mm": 2014.548, "area_m2": 2.381195736})
        conn.executemany(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history, machine_meta_json)
            VALUES (?, ?, ?, 'CNC', 'CUTTING', ?, ?, ?, 0, 1, ?, ?)
            """,
            [
                (
                    "old-export-renamed",
                    "loi_f8_120x29.tap",
                    r"D:\CNC\2026-07-14\loi_f8_120x29.tap",
                    "EXPORTED",
                    "2026-07-14 16:59:13",
                    "2026-07-14 16:59:13",
                    "[]",
                    json.dumps({"width_mm": 1195.662, "height_mm": 290.017, "area_m2": 0.346762306254}),
                ),
                (
                    "new-done-renamed",
                    "loi_f8_120x29_ngay14.tap",
                    r"D:\CNC\2026-07-15\loi_f8_120x29_ngay14.tap",
                    "DONE",
                    "2026-07-15 08:12:29",
                    "2026-07-15 08:24:31",
                    json.dumps([{"status": "DONE", "time": "2026-07-15 08:24:31", "event": "Cắt xong"}]),
                    json.dumps({"width_mm": 1195.662, "height_mm": 290.017, "area_m2": 0.346762306254}),
                ),
                (
                    "old-export-size-renamed",
                    "lh444_mica.tap",
                    r"D:\CNC\2026-07-14\lh444_mica.tap",
                    "EXPORTED",
                    "2026-07-14 08:26:59",
                    "2026-07-14 08:26:59",
                    "[]",
                    cnc_size_meta,
                ),
                (
                    "new-done-size-renamed",
                    "118x201_ngay14.tap",
                    r"D:\CNC\2026-07-15\118x201_ngay14.tap",
                    "DONE",
                    "2026-07-15 08:52:09",
                    "2026-07-15 09:21:02",
                    json.dumps([{"status": "DONE", "time": "2026-07-15 09:21:02", "event": "Cắt xong"}]),
                    cnc_size_meta,
                ),
            ],
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_crm_dir = Dashboard.BASE_DATA_CRM
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.BASE_DATA_CRM = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "BASE_DATA_CRM", old_crm_dir))

        with mock.patch.object(
            Dashboard,
            "find_existing_tap",
            side_effect=AssertionError("board list must not scan tap files"),
        ):
            with Dashboard.app.test_client() as client:
                response = client.get("/api/data?start=2026-07-14&end=2026-07-14&machine=all&limit=50")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        visible_names = [
            item["name"].lower()
            for bucket in ("EXPORTED", "RIP", "RUNNING", "CANCELED", "REMOVED")
            for item in payload[bucket]
        ]

        self.assertNotIn("18~loi_decal_70x25.prn", visible_names)
        self.assertNotIn("vctt_f5_120x50.tap", visible_names)
        self.assertNotIn("loi_f8_120x29.tap", visible_names)
        self.assertNotIn("lh444_mica.tap", visible_names)
        self.assertEqual(payload["COUNTS"]["RIP"], 0)
        self.assertEqual(payload["COUNTS"]["RUNNING"], 0)
        self.assertEqual(payload["COUNTS"]["CANCELED"], 0)
        self.assertEqual(payload["COUNTS"]["QUEUE"], 0)
        self.assertEqual(payload["COUNTS"]["PROBLEM"], 0)

    def test_v2_status_reads_indecal_rename_audit(self):
        db_path = os.path.join(self.temp_dir.name, "indecal_rename_audit.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE rename_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine TEXT,
                action TEXT,
                prn_path TEXT,
                meta_path TEXT,
                target_prn_path TEXT,
                source_image_path TEXT,
                target_image_path TEXT,
                file_size INTEGER,
                retry_count INTEGER,
                error TEXT,
                event_time TEXT,
                received_time TEXT,
                extra_json TEXT
            )
            """
        )
        today = Dashboard.now().split(" ")[0]
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
            VALUES ('InDecal', 'RENAME_FAIL_NO_META', 'D:\\x.prn', '', '', '', '', 12, 0, 'no meta', ?, ?, '{}')
            """,
            (f"{today} 09:10:11", Dashboard.now()),
        )
        conn.commit()
        conn.close()

        audit = Dashboard.inspect_indecal_rename_audit(self.temp_dir.name)

        self.assertTrue(audit["exists"])
        self.assertEqual(audit["total"], 1)
        self.assertEqual(audit["today"], 1)
        self.assertEqual(audit["fail_today"], 1)
        self.assertEqual(audit["recent"][0]["action"], "RENAME_FAIL_NO_META")

    def test_v2_status_does_not_count_rename_race_ok_as_indecal_rename_error(self):
        db_path = os.path.join(self.temp_dir.name, "indecal_rename_audit.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE rename_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine TEXT,
                action TEXT,
                prn_path TEXT,
                meta_path TEXT,
                target_prn_path TEXT,
                source_image_path TEXT,
                target_image_path TEXT,
                file_size INTEGER,
                retry_count INTEGER,
                error TEXT,
                event_time TEXT,
                received_time TEXT,
                extra_json TEXT
            )
            """
        )
        today = Dashboard.now().split(" ")[0]
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
            VALUES ('InDecal', 'RENAME_RACE_OK', 'D:\\6.prn', 'D:\\VHC_120X40._tf',
                    'D:\\6~VHC_120X40.prn', '', '', 12, 0, '[WinError 2] source vanished after target existed', ?, ?, '{}')
            """,
            (f"{today} 10:06:02", Dashboard.now()),
        )
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
            VALUES ('InDecal', 'RENAME_FAIL_NO_META', 'D:\\7.prn', '', '', '', '', 12, 0, 'no meta', ?, ?, '{}')
            """,
            (f"{today} 10:20:00", Dashboard.now()),
        )
        conn.commit()
        conn.close()

        audit = Dashboard.inspect_indecal_rename_audit(self.temp_dir.name)

        self.assertEqual(audit["today"], 2)
        self.assertEqual(audit["fail_today"], 1)

    def test_v2_status_ignores_old_rename_failures_resolved_by_later_ok(self):
        db_path = os.path.join(self.temp_dir.name, "indecal_rename_audit.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE rename_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine TEXT,
                action TEXT,
                prn_path TEXT,
                meta_path TEXT,
                target_prn_path TEXT,
                source_image_path TEXT,
                target_image_path TEXT,
                file_size INTEGER,
                retry_count INTEGER,
                error TEXT,
                event_time TEXT,
                received_time TEXT,
                extra_json TEXT
            )
            """
        )
        today = Dashboard.now().split(" ")[0]
        for minute in range(0, 9):
            conn.execute(
                """
                INSERT INTO rename_audit
                    (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                     target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
                VALUES ('InDecal', 'RENAME_FAIL_REPLACE', 'D:\\7.prn', 'D:\\TTP_120x325._tf',
                        'D:\\7~TTP_120x325.prn', '', '', 12, 0,
                        '[WinError 32] locked', ?, ?, '{}')
                """,
                (f"{today} 17:00:{minute:02d}", Dashboard.now()),
            )
        conn.execute(
            """
            INSERT INTO rename_audit
                (machine, action, prn_path, meta_path, target_prn_path, source_image_path,
                 target_image_path, file_size, retry_count, error, event_time, received_time, extra_json)
            VALUES ('InDecal', 'RENAME_OK', 'D:\\7.prn', 'D:\\TTP_120x325._tf',
                    'D:\\7~TTP_120x325.prn', '', '', 12, 0, '', ?, ?, '{}')
            """,
            (f"{today} 17:05:07", Dashboard.now()),
        )
        conn.commit()
        conn.close()

        audit = Dashboard.inspect_indecal_rename_audit(self.temp_dir.name)

        self.assertEqual(audit["today"], 10)
        self.assertEqual(audit["fail_today"], 0)

    def test_machine_status_separates_machine_log_from_admin_web_update(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET updated_time='2026-07-11 18:33:01',
                history='[{"status":"DELETED","time":"2026-07-11 18:33:01","event":"ADMIN_DELETE"}]'
            WHERE file_hash='hash-1'
            """
        )
        conn.execute(
            """
            UPDATE files
            SET updated_time='2026-07-11 17:25:19',
                history='[{"status":"PRINTING","time":"2026-07-11 17:14:57","event":"PRINTING"},{"status":"DONE","time":"2026-07-11 17:25:19","event":"In xong"}]'
            WHERE file_hash='hash-2'
            """
        )
        conn.execute(
            """
            UPDATE files
            SET updated_time='2026-07-11 10:00:00',
                history='[{"status":"DONE","time":"2026-07-11 10:00:00","event":"In xong"}]'
            WHERE file_hash='hash-3'
            """
        )
        conn.commit()
        conn.close()

        info = Dashboard.inspect_machine_db("InDecal", self.temp_dir.name)

        self.assertEqual(info["latest_update"], "2026-07-11 18:33:01")
        self.assertEqual(info["latest_machine_update"], "2026-07-11 17:25:19")
        self.assertEqual(info["latest_admin_update"], "2026-07-11 18:33:01")

    def test_ping_host_does_not_call_dns_after_ping_failure(self):
        failed_ping = mock.Mock(returncode=1)
        with mock.patch.object(Dashboard.subprocess, "run", return_value=failed_ping) as run_mock:
            with mock.patch.object(Dashboard.socket, "gethostbyname") as dns_mock:
                self.assertFalse(Dashboard.ping_host("InDecal"))

        run_mock.assert_called_once()
        dns_mock.assert_not_called()

    def test_stale_v2_ping_does_not_block_status_with_network_probe(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE app_info SET value='2026-07-11 17:55:02' WHERE key='last_ping'")
        conn.commit()
        conn.close()

        with mock.patch.object(Dashboard, "ping_host", side_effect=AssertionError("network probe should not run")):
            info = Dashboard.inspect_machine_db("InDecal", self.temp_dir.name)

        self.assertFalse(info["online"])
        self.assertFalse(info["network_online"])

    def test_active_file_with_later_machine_run_is_not_currently_running(self):
        rows = [
            (
                "hash-17",
                "17~hh3_110x60.prn",
                r"D:\2026-07-11\New Folder\17~hh3_110x60.prn",
                "PRINTING",
                "2026-07-11 16:17:57",
                "2026-07-11 16:59:27",
                1,
                json.dumps([
                    {"status": "EXPORTED", "time": "2026-07-11 16:17:57"},
                    {"status": "RIP", "time": "2026-07-11 16:26:17"},
                    {"status": "PRINTING", "time": "2026-07-11 16:59:27"},
                ]),
                0,
            ),
            (
                "hash-admin",
                "xd4.tif",
                r"D:\2026-07-11\xd4.tif",
                "DELETED",
                "2026-07-11 15:00:00",
                "2026-07-11 18:33:01",
                1,
                json.dumps([
                    {"status": "DELETED", "time": "2026-07-11 18:33:01", "event": "ADMIN_DELETE"},
                ]),
                0,
            ),
            (
                "hash-18",
                "18~hh4_100x70.prn",
                r"D:\2026-07-11\New Folder\18~hh4_100x70.prn",
                "DONE",
                "2026-07-11 16:18:57",
                "2026-07-11 17:05:16",
                1,
                json.dumps([
                    {"status": "PRINTING", "time": "2026-07-11 17:02:23"},
                    {"status": "DONE", "time": "2026-07-11 17:05:16"},
                ]),
                0,
            ),
        ]

        later = Dashboard.find_later_machine_run(
            rows,
            "17~hh3_110x60.prn",
            Dashboard.active_start_time(rows[0][7], rows[0][5]),
        )

        self.assertEqual(later["name"], "18~hh4_100x70.prn")
        self.assertEqual(later["time"], "2026-07-11 17:02:23")

    def test_quantity_and_reprint_classification(self):
        self.assertEqual(Dashboard.parse_expected_runs("KH_120x50_x5.prn"), 5)
        self.assertEqual(Dashboard.parse_expected_runs("KH_120x50_SL4.prn"), 4)
        self.assertEqual(Dashboard.parse_expected_runs("KH_120x50_xsl3.prn"), 3)
        self.assertEqual(Dashboard.parse_expected_runs("KH_120x50.prn"), 1)

        correct_multi = Dashboard.classify_reprint("KH_120x50_x5.prn", 5)
        self.assertFalse(correct_multi["needs_review"])
        self.assertEqual(correct_multi["billable_runs"], 5)

        one_log_for_quantity = Dashboard.classify_reprint("KH_120x50_x5.prn", 1)
        self.assertFalse(one_log_for_quantity["needs_review"])
        self.assertEqual(one_log_for_quantity["billable_runs"], 5)

        over_quantity = Dashboard.classify_reprint("KH_120x50_x2.prn", 3)
        self.assertTrue(over_quantity["needs_review"])
        self.assertEqual(over_quantity["extra_runs"], 1)

        unknown_repeat = Dashboard.classify_reprint("KH_120x50.prn", 2)
        self.assertTrue(unknown_repeat["needs_review"])

    def test_confirmed_reprint_runs_clear_review_on_board_item(self):
        history = json.dumps([
            {"status": "PRINTING", "time": "2026-07-15 10:00:00", "event": "PRINTING"},
            {"status": "DONE", "time": "2026-07-15 10:04:00", "event": "DONE"},
            {
                "status": "DONE",
                "time": "2026-07-15 10:05:00",
                "event": "ADMIN_CONFIRM_RUNS",
                "confirmed_runs": 4,
            },
        ])
        item = Dashboard.build_board_item(
            "InDecal",
            (
                "hash-confirm",
                "Bevang1.prn",
                r"D:\Jobs\Bevang1.prn",
                "DONE",
                "2026-07-15 10:00:00",
                "2026-07-15 10:05:00",
                4,
                history,
                0,
                "{}",
            ),
            set(),
            {},
            [],
            [],
        )

        self.assertFalse(item["reprint_needs_review"])
        self.assertEqual(item["reprint_label"], "Đã xác nhận In x4 đúng")

    def test_deleted_source_file_is_not_production_error(self):
        source_delete = Dashboard.classify_deleted_job(
            "InBat",
            "job_120x50.tif",
            '[{"status":"EXPORTED","time":"2026-07-10 08:00:00"},{"status":"DELETED","event":"DELETE","old_status":"EXPORTED"}]',
        )
        self.assertFalse(source_delete["is_production_error"])
        self.assertEqual(source_delete["type"], "source_delete")

        production_cancel = Dashboard.classify_deleted_job(
            "InBat",
            "job_120x50.prt",
            '[{"status":"PRINTING","time":"2026-07-10 08:00:00"},{"status":"DELETED","event":"DELETE","old_status":"PRINTING"}]',
        )
        self.assertTrue(production_cancel["is_production_error"])
        self.assertEqual(production_cancel["type"], "production_cancel")

    def test_admin_delete_is_separate_from_source_delete(self):
        admin_delete = Dashboard.classify_deleted_job(
            "InDecal",
            "xd4.tif",
            '[{"status":"DELETED","time":"2026-07-11 18:33:01","event":"ADMIN_DELETE"}]',
        )

        self.assertFalse(admin_delete["is_production_error"])
        self.assertEqual(admin_delete["type"], "admin_delete")
        self.assertEqual(admin_delete["label"], "Quản trị xóa")

    def test_active_reprint_waiting_for_done_is_marked_for_review(self):
        info = Dashboard.classify_active_reprint(
            '[{"status":"PRINTING","time":"2026-07-10 15:29:33","event":"In lại sau khi đã xong - chờ tín hiệu xong"}]'
        )

        self.assertTrue(info["is_reprint_waiting_done"])
        self.assertEqual(info["label"], "In lại sau khi đã xong - chờ tín hiệu xong")

    def test_reprint_cancel_after_done_is_clear_cancel_not_review(self):
        info = Dashboard.classify_reprint_cancel_after_done(
            "job_120x50.prt",
            has_done_before=True,
            is_production_error=True,
        )

        self.assertTrue(info["is_reprint_cancel_after_done"])
        self.assertFalse(info["needs_review"])
        self.assertNotIn("cần xác nhận", info["label"])
        self.assertIn("cần kiểm tra tín hiệu/máy", info["label"])

    def test_prior_done_too_fast_is_not_trusted(self):
        info = Dashboard.assess_prior_done_duration(
            "job_450x60.prt",
            [
                '[{"status":"PRINTING","time":"2026-07-10 15:26:40"},{"status":"DONE","time":"2026-07-10 15:27:57"}]'
            ],
            [
                {
                    "file_name": "sample_450x60.prt",
                    "history": '[{"status":"PRINTING","time":"2026-07-10 13:00:00"},{"status":"DONE","time":"2026-07-10 13:08:00"}]',
                }
            ],
        )

        self.assertTrue(info["is_suspicious"])
        self.assertFalse(info["trusted"])
        self.assertIn("DONE trước đó quá nhanh", info["label"])

    def test_prior_done_normal_duration_is_trusted(self):
        info = Dashboard.assess_prior_done_duration(
            "job_450x60.prt",
            [
                '[{"status":"PRINTING","time":"2026-07-10 15:00:00"},{"status":"DONE","time":"2026-07-10 15:08:00"}]'
            ],
            [
                {
                    "file_name": "sample_450x60.prt",
                    "history": '[{"status":"PRINTING","time":"2026-07-10 13:00:00"},{"status":"DONE","time":"2026-07-10 13:08:00"}]',
                }
            ],
        )

        self.assertFalse(info["is_suspicious"])
        self.assertTrue(info["trusted"])

    def test_small_indecal_done_near_history_is_trusted(self):
        info = Dashboard.assess_prior_done_duration(
            "1~LOI_120X20.prn",
            [
                '[{"status":"PRINTING","time":"2026-07-11 11:12:19"},{"status":"DONE","time":"2026-07-11 11:13:20"}]'
            ],
            [
                {
                    "file_name": "sample_120x20.prn",
                    "history": '[{"status":"PRINTING","time":"2026-07-11 10:00:00"},{"status":"DONE","time":"2026-07-11 10:01:26"}]',
                },
                {
                    "file_name": "sample2_120x20.prn",
                    "history": '[{"status":"PRINTING","time":"2026-07-11 10:10:00"},{"status":"DONE","time":"2026-07-11 10:11:10"}]',
                },
            ],
        )

        self.assertFalse(info["is_suspicious"])
        self.assertTrue(info["trusted"])

    def test_cnc_horizontal_template_delete_is_expected_stop(self):
        info = Dashboard.classify_deleted_job(
            "CNC",
            "5p ngang chuan dut vip1.tap",
            '[{"status":"CUTTING","time":"2026-07-11 15:43:13"},{"status":"DELETED","time":"2026-07-11 15:45:01"}]',
        )

        self.assertEqual(info["type"], "cnc_expected_stop")
        self.assertFalse(info["is_production_error"])
        self.assertIn("CNC", info["label"])

    def test_estimate_cancel_progress_uses_explicit_percent_first(self):
        progress = Dashboard.estimate_cancel_progress(
            "job_100x100.prt",
            '[{"status":"PRINTING","time":"2026-07-10 10:00:00"},{"status":"DELETED","time":"2026-07-10 10:03:00","progress_percent":37}]',
            [],
        )

        self.assertEqual(progress["progress_percent"], 37)
        self.assertEqual(progress["progress_source"], "explicit")
        self.assertEqual(progress["progress_label"], "Tiến độ: 37%")

    def test_estimate_cancel_progress_from_done_duration_samples(self):
        progress = Dashboard.estimate_cancel_progress(
            "job_100x100.prt",
            '[{"status":"PRINTING","time":"2026-07-10 10:00:00"},{"status":"DELETED","time":"2026-07-10 10:05:00"}]',
            [
                {
                    "file_name": "done_100x100.prt",
                    "history": '[{"status":"PRINTING","time":"2026-07-10 09:00:00"},{"status":"DONE","time":"2026-07-10 09:10:00"}]',
                }
            ],
        )

        self.assertEqual(progress["progress_percent"], 50)
        self.assertEqual(progress["progress_source"], "estimated")
        self.assertEqual(progress["progress_label"], "Tiến độ: 50% ước tính")

    def test_estimate_cancel_progress_unknown_without_baseline(self):
        progress = Dashboard.estimate_cancel_progress(
            "job_100x100.prt",
            '[{"status":"PRINTING","time":"2026-07-10 10:00:00"},{"status":"DELETED","time":"2026-07-10 10:05:00"}]',
            [],
        )

        self.assertIsNone(progress["progress_percent"])
        self.assertEqual(progress["progress_source"], "unknown")
        self.assertEqual(progress["progress_label"], "Tiến độ: chưa rõ")

    def test_active_progress_label_uses_machine_meta_percent(self):
        self.assertEqual(
            Dashboard.active_progress_label({"progress_percent": 92.3, "current_pass": 396, "total_pass": 429}),
            "Tiến độ: 92% | Bước in 396/429",
        )

    def test_active_progress_label_shows_cnc_current_line(self):
        self.assertEqual(
            Dashboard.active_progress_label({"progress_percent": 40.35, "current_line": 12732, "line_count": 31557}),
            "Tiến độ: 40% | Dòng 12.732/31.557",
        )

    def test_active_progress_label_pass_count_without_percent(self):
        self.assertEqual(
            Dashboard.active_progress_label({"current_pass": 251, "total_pass": 460, "progress_source": "inbat_printfile_steps"}),
            "Tiến độ: 55% | Bước in 251/460",
        )

    def test_apply_live_print_progress_enriches_matching_inbat_job(self):
        raw = bytearray(b"xxD:\\Jobs\\utteo2_300x230.prt")
        raw.extend(b"\x00" * (272 - len(raw)))
        raw[260:264] = (1).to_bytes(4, "little")
        raw[264:268] = (39).to_bytes(4, "little")
        raw[268:272] = (545).to_bytes(4, "little")
        progress_path = os.path.join(self.temp_dir.name, "PrintFile.ini")
        with open(progress_path, "wb") as f:
            f.write(raw)

        item = {"machine": "InBat", "name": "utteo2_300x230.prt", "status": "PRINTING", "machine_meta": {"height_cm": 230.0}}
        with mock.patch.object(Dashboard, "INBAT_PRINTFILE_PATHS", (progress_path,)):
            Dashboard.apply_live_print_progress(item)

        self.assertEqual(item["machine_meta"]["current_pass"], 39)
        self.assertEqual(item["machine_meta"]["total_pass"], 96)
        self.assertEqual(item["machine_meta"]["printmon_total_pass"], 545)
        self.assertEqual(item["machine_meta"]["progress_source"], "inbat_feed_length_steps")
        self.assertAlmostEqual(item["machine_meta"]["progress_percent"], 39 * 100.0 / 96)

    def test_build_board_item_corrects_inbat_printmon_total_from_feed_length(self):
        row = (
            "hash-kl",
            "kl_487x260.prt",
            r"D:\2026-07-15\New Folder\kl_487x260.prt",
            "PRINTING",
            "2026-07-15 16:57:00",
            "2026-07-15 17:03:00",
            1,
            '[{"status":"PRINTING","time":"2026-07-15 16:57:00"}]',
            0,
            json.dumps({
                "current_pass": 148,
                "total_pass": 410,
                "height_cm": 487.045,
                "width_cm": 260.043,
                "progress_percent": 36.1,
                "progress_source": "inbat_printfile_steps",
            }),
        )

        with mock.patch.object(Dashboard, "read_live_inbat_print_event", return_value=None):
            item = Dashboard.build_board_item("InBat", row, set(), {}, [], [])

        self.assertEqual(item["machine_meta"]["total_pass"], 203)
        self.assertEqual(item["machine_meta"]["printmon_total_pass"], 410)
        self.assertEqual(item["progress_label"], "Tiến độ: 73% | Bước in 148/203")

    def test_inbat_thumbnail_prefers_design_source_over_rip_preview(self):
        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        calls = []
        item = {
            "hash": "hash-inbat",
            "machine": "InBat",
            "file_path": r"D:\job.prt",
            "machine_meta": {
                "design_metadata_source": r"D:\job.tif",
                "preview_source": r"D:\job.prt",
                "metadata_source": r"D:\job.prt",
            },
        }

        def fake_generate(source, target):
            calls.append(source)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(b"thumb")
            Dashboard.write_thumb_source_marker(target, source)
            return True

        with mock.patch.object(Dashboard, "THUMB_DIR", thumb_dir), \
            mock.patch.object(Dashboard, "find_machine_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "find_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "collect_machine_file_meta_for_server", return_value={}), \
            mock.patch.object(Dashboard, "generate_thumb_from_source", side_effect=fake_generate):
            self.assertTrue(Dashboard.ensure_item_thumbnail(item))

        self.assertEqual(calls[0], r"D:\job.tif")
        marker_path = os.path.join(thumb_dir, "hash-inbat.jpg.src")
        with open(marker_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), r"D:\job.tif")

    def test_existing_unmarked_inbat_thumbnail_is_regenerated(self):
        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, "hash-inbat.jpg")
        with open(thumb_path, "wb") as handle:
            handle.write(b"old")
        item = {
            "hash": "hash-inbat",
            "machine": "InBat",
            "machine_meta": {"design_metadata_source": r"D:\job.tif"},
        }

        def fake_generate(source, target):
            with open(target, "wb") as handle:
                handle.write(b"new")
            Dashboard.write_thumb_source_marker(target, source)
            return True

        with mock.patch.object(Dashboard, "THUMB_DIR", thumb_dir), \
            mock.patch.object(Dashboard, "find_machine_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "find_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "collect_machine_file_meta_for_server", return_value={}), \
            mock.patch.object(Dashboard, "generate_thumb_from_source", side_effect=fake_generate):
            self.assertTrue(Dashboard.ensure_item_thumbnail(item))

        with open(thumb_path, "rb") as handle:
            self.assertEqual(handle.read(), b"new")
        with open(thumb_path + ".src", "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), r"D:\job.tif")

    def test_existing_inbat_thumbnail_is_kept_when_regenerate_source_missing(self):
        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = os.path.join(thumb_dir, "hash-inbat.jpg")
        with open(thumb_path, "wb") as handle:
            handle.write(b"old")
        item = {
            "hash": "hash-inbat",
            "machine": "InBat",
            "machine_meta": {"design_metadata_source": r"D:\missing.tif"},
        }

        with mock.patch.object(Dashboard, "THUMB_DIR", thumb_dir), \
            mock.patch.object(Dashboard, "find_machine_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "find_thumbnail_source", return_value=None), \
            mock.patch.object(Dashboard, "collect_machine_file_meta_for_server", return_value={}), \
            mock.patch.object(Dashboard, "generate_thumb_from_source", return_value=False):
            self.assertTrue(Dashboard.ensure_item_thumbnail(item))

        with open(thumb_path, "rb") as handle:
            self.assertEqual(handle.read(), b"old")

    def test_active_running_without_real_progress_does_not_show_estimated_percent(self):
        row = (
            "hash-active",
            "banner_100x100.prt",
            r"D:\2026-07-15\New Folder\banner_100x100.prt",
            "PRINTING",
            "2026-07-15 08:00:00",
            "2026-07-15 08:01:00",
            1,
            '[{"status":"PRINTING","time":"2026-07-15 08:00:00"}]',
            0,
            "{}",
        )

        with mock.patch.object(Dashboard, "read_live_inbat_print_event", return_value=None):
            item = Dashboard.build_board_item("InBat", row, set(), {}, [], [])

        self.assertNotIn("progress_label", item)
        self.assertNotIn("progress_percent", item)
        self.assertNotIn("progress_source", item)

    def test_done_item_drops_stale_live_progress(self):
        row = (
            "hash-done",
            "banner_100x100.prt",
            r"D:\2026-07-15\New Folder\banner_100x100.prt",
            "DONE",
            "2026-07-15 08:00:00",
            "2026-07-15 08:30:00",
            1,
            '[{"status":"PRINTING","time":"2026-07-15 08:00:00"},{"status":"DONE","time":"2026-07-15 08:30:00"}]',
            0,
            '{"progress_percent":54.5,"current_pass":251,"total_pass":460,"progress_source":"inbat_printfile","area_m2":1.0}',
        )

        item = Dashboard.build_board_item("InBat", row, set(), {}, [], [])

        self.assertEqual(item["status"], "DONE")
        self.assertNotIn("progress_label", item)
        self.assertNotIn("progress_percent", item)
        self.assertNotIn("progress_source", item)
        self.assertNotIn("progress_percent", item["machine_meta"])
        self.assertNotIn("current_pass", item["machine_meta"])
        self.assertNotIn("total_pass", item["machine_meta"])
        self.assertEqual(item["machine_meta"]["area_m2"], 1.0)

    def test_build_board_item_refreshes_missing_real_size_from_machine_file(self):
        row = (
            "hash-size",
            "banner_450x70.prt",
            r"D:\2026-07-15\New Folder\banner_450x70.prt",
            "DONE",
            "2026-07-15 08:00:00",
            "2026-07-15 08:10:00",
            1,
            '[{"status":"DONE","time":"2026-07-15 08:10:00"}]',
            0,
            "{}",
        )

        with mock.patch.object(
            Dashboard,
            "collect_machine_file_meta_for_server",
            return_value={"source_kind": "rip_file_header", "width_cm": 459.0, "height_cm": 70.0, "area_m2": 3.213},
        ) as meta_mock:
            item = Dashboard.build_board_item("InBat", row, set(), {}, [], [])

        meta_mock.assert_called_once()
        self.assertEqual(item["machine_meta"]["source_kind"], "rip_file_header")
        self.assertAlmostEqual(item["machine_meta"]["width_cm"], 459.0)
        self.assertAlmostEqual(item["machine_meta"]["height_cm"], 70.0)

    def test_build_board_item_marks_last_paused_cnc_job(self):
        row = (
            "hash-nsss",
            "nsss_120x120.tap",
            r"D:\CNC\2026-07-14\nsss_120x120.tap",
            "CUTTING",
            "2026-07-14 10:36:18",
            "2026-07-14 11:24:58",
            1,
            '[{"status":"CUTTING","time":"2026-07-14 11:09:14"},{"status":"PAUSED","time":"2026-07-14 11:24:58","event":"PAUSE"}]',
            0,
            '{"progress_percent":40.35,"current_line":12732,"line_count":31557}',
        )

        item = Dashboard.build_board_item("CNC", row, set(), {}, [], [])

        self.assertTrue(item["is_paused"])
        self.assertEqual(item["stage_key"], "PAUSED")
        self.assertEqual(item["stage_label"], "Đang dừng")
        self.assertEqual(item["progress_label"], "Tiến độ: 40% | Dòng 12.732/31.557")
        self.assertIn("/cnc-progress-thumb/hash-nsss.jpg", item["preview_url"])

    def test_build_board_item_marks_direct_pause_status_as_stopped(self):
        row = (
            "hash-vctt",
            "VCTT_F5_120X50.tap",
            r"D:\CNC\2026-07-14\VCTT_F5_120X50.tap",
            "PAUSE",
            "2026-07-14 17:12:02",
            "2026-07-14 17:35:45",
            1,
            '[{"status":"CUTTING","time":"2026-07-14 17:12:02"},{"status":"PAUSE","time":"2026-07-14 17:35:29","event":"PAUSE"}]',
            0,
            '{"progress_percent":90.75,"current_line":22442,"line_count":24729}',
        )

        item = Dashboard.build_board_item("CNC", row, set(), {}, [], [])

        self.assertTrue(item["is_paused"])
        self.assertEqual(item["stage_key"], "PAUSED")
        self.assertEqual(item["stage_label"], "Đang dừng")
        self.assertEqual(item["progress_label"], "Tiến độ: 91% | Dòng 22.442/24.729")
        self.assertIn("/cnc-progress-thumb/hash-vctt.jpg", item["preview_url"])

    def test_cnc_cancel_progress_does_not_estimate_bad_m2_from_cut_percent(self):
        row = (
            "hash-ns",
            "ns_f5_120x101.tap",
            r"D:\CNC\2026-07-14\ns_f5_120x101.tap",
            "DELETED",
            "2026-07-14 10:57:59",
            "2026-07-14 11:08:23",
            1,
            '[{"status":"CUTTING","time":"2026-07-14 10:57:59"},{"status":"DELETED","time":"2026-07-14 11:08:23","event":"DELETE","old_status":"CUTTING","progress_percent":12}]',
            0,
            '{"source_kind":"tap","area_m2":1.2,"progress_percent":12,"current_line":120,"line_count":1000}',
        )

        item = Dashboard.build_board_item("CNC", row, set(), {}, [], [])

        self.assertEqual(item["progress_label"], "Tiến độ: 12%")
        self.assertNotIn("estimated_bad_m2", item)

    def test_estimate_active_progress_from_cnc_line_count_samples(self):
        progress = Dashboard.estimate_active_progress(
            "xp3.tap",
            '[{"status":"CUTTING","time":"2026-07-13 17:04:58"}]',
            [
                {
                    "file_name": "xp2.tap",
                    "history": '[{"status":"CUTTING","time":"2026-07-13 16:29:24"},{"status":"DONE","time":"2026-07-13 16:42:26"}]',
                    "machine_meta": {"line_count": 8000},
                }
            ],
            {"line_count": 8000},
            now_dt=Dashboard.datetime.strptime("2026-07-13 17:08:53", "%Y-%m-%d %H:%M:%S"),
        )

        self.assertEqual(progress["progress_source"], "estimated")
        self.assertEqual(progress["progress_percent"], 30)
        self.assertEqual(progress["progress_label"], "Tiến độ: 30% ước tính")

    def test_estimate_active_progress_uses_tap_line_count_without_done_samples(self):
        progress = Dashboard.estimate_active_progress(
            "f3_120x75.tap",
            '[{"status":"CUTTING","time":"2026-07-14 08:24:25"}]',
            [],
            {"source_kind": "tap", "line_count": 3339},
            now_dt=Dashboard.datetime.strptime("2026-07-14 08:27:31", "%Y-%m-%d %H:%M:%S"),
        )

        self.assertEqual(progress["progress_source"], "tap_line_fallback")
        self.assertEqual(progress["progress_percent"], 50)
        self.assertEqual(progress["progress_label"], "Tiến độ: 50% ước tính")

    def test_estimate_active_progress_uses_print_area_without_done_samples(self):
        progress = Dashboard.estimate_active_progress(
            "ttttp_300x250.prt",
            '[{"status":"PRINTING","time":"2026-07-14 08:57:52"}]',
            [],
            {"metadata_source": r"\\InBat\D\2026-07-13\New Folder\ttttp_300x250.prt"},
            now_dt=Dashboard.datetime.strptime("2026-07-14 08:59:10", "%Y-%m-%d %H:%M:%S"),
        )

        self.assertEqual(progress["progress_source"], "print_area_fallback")
        self.assertEqual(progress["progress_percent"], 12)
        self.assertEqual(progress["progress_label"], "Tiến độ: 12% ước tính")

    def test_dedupe_visible_items_keeps_latest_duplicate_cancel(self):
        items = [
            {"machine": "InDecal", "name": "14~xpppp1_122x164.prn", "cancel_type": "production_cancel", "updated": "2026-07-13 15:38:33"},
            {"machine": "InDecal", "name": "14~xpppp1_122x164.prn", "cancel_type": "production_cancel", "updated": "2026-07-13 15:43:55"},
        ]

        deduped = Dashboard.dedupe_visible_items(items)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["updated"], "2026-07-13 15:43:55")

    def test_filter_removed_items_hides_old_delete_when_same_job_is_done(self):
        removed = [
            {"machine": "InDecal", "name": "25~temm_hlll_125x103.prn", "updated": "2026-07-13 17:14:08"}
        ]
        done = [
            {"machine": "InDecal", "name": "25~temm_hlll_125x103.prn", "updated": "2026-07-13 17:26:29"}
        ]

        filtered = Dashboard.filter_removed_items_with_later_done(removed, done)

        self.assertEqual(filtered, [])

    def test_filter_removed_items_hides_source_renamed_to_later_done(self):
        removed = [
            {"machine": "InDecal", "name": "hoatho_118x78_ngay11.tif", "updated": "2026-07-13 07:45:08"}
        ]
        done = [
            {"machine": "InDecal", "name": "1~HOATHO_118X78_Ngay11_Ngay12.prn", "updated": "2026-07-13 07:53:25"}
        ]

        filtered = Dashboard.filter_removed_items_with_later_done(removed, done)

        self.assertEqual(filtered, [])

    def test_filter_removed_items_hides_explicit_source_renamed_done(self):
        removed = [
            {
                "machine": "InDecal",
                "name": "HOATHO_120X80_Ngay11.tif",
                "updated": "2026-07-13 07:45:08",
                "cancel_type": "source_renamed_done",
            }
        ]

        filtered = Dashboard.filter_removed_items_with_later_done(removed, [])

        self.assertEqual(filtered, [])

    def test_filter_removed_items_hides_done_cleanup(self):
        removed = [
            {
                "machine": "InDecal",
                "name": "11~ghep_105x220.prn",
                "updated": "2026-07-13 14:09:49",
                "cancel_type": "done_cleanup",
            }
        ]

        filtered = Dashboard.filter_removed_items_with_later_done(removed, [])

        self.assertEqual(filtered, [])

    def test_source_renamed_done_label_is_not_delete_wording(self):
        info = Dashboard.classify_deleted_job(
            "InDecal",
            "HOATHO_120X80_Ngay11.tif",
            '[{"status":"DELETED","event":"ADMIN_CLEAN_RENAMED_DONE","cancel_type":"source_renamed_done"}]',
        )

        self.assertFalse(info["is_production_error"])
        self.assertEqual(info["type"], "source_renamed_done")
        self.assertEqual(info["label"], "Đã đổi tên/in xong")

    def test_filter_removed_items_keeps_unrelated_partial_name_match(self):
        removed = [
            {"machine": "InDecal", "name": "hoatho_118x78_ngay11.tif", "updated": "2026-07-13 07:45:08"}
        ]
        done = [
            {"machine": "InDecal", "name": "1~HOATHO_120X80_Ngay11_Ngay12.prn", "updated": "2026-07-13 07:53:25"}
        ]

        filtered = Dashboard.filter_removed_items_with_later_done(removed, done)

        self.assertEqual(filtered, removed)

    def test_delete_after_done_is_cleanup_not_production_cancel(self):
        info = Dashboard.classify_deleted_job(
            "CNC",
            "xp3.tap",
            '[{"status":"CUTTING","time":"2026-07-13 17:04:58"},{"status":"DONE","time":"2026-07-13 17:10:50"},{"status":"DELETED","time":"2026-07-13 17:11:11"}]',
        )

        self.assertFalse(info["is_production_error"])
        self.assertEqual(info["type"], "done_cleanup")
        self.assertIn("sau khi xong", info["label"])


    def test_cancel_rate_uses_bad_m2_not_cancel_job_count(self):
        rate = Dashboard.calculate_cancel_rate_by_m2(total_done_m2=97.0, total_bad_m2=3.0)

        self.assertAlmostEqual(rate, 3.0)

    def test_cancel_rate_is_zero_without_bad_m2(self):
        rate = Dashboard.calculate_cancel_rate_by_m2(total_done_m2=97.0, total_bad_m2=0.0)

        self.assertEqual(rate, 0)

    def test_parse_area_handles_missing_decimal_outlier_names(self):
        self.assertAlmostEqual(Dashboard.parse_area_python("quochoang_366x2544.prt"), 9.31104)
        self.assertAlmostEqual(Dashboard.parse_area_python("NTDQq_800x310.prt"), 24.8)

    def test_stats_returns_machine_flow_count_and_m2(self):
        self.make_machine_db("InBat")
        self.make_machine_db("InDecal")

        inbat_db = os.path.join(self.temp_dir.name, "InBat.db")
        conn = sqlite3.connect(inbat_db)
        conn.execute(
            """
            UPDATE files
            SET file_name='banner_100x200_x2.prt',
                updated_time='2026-07-11 09:10:00',
                run_count=2
            WHERE file_hash='hash-3'
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InBat")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("machine_flow", payload)
        self.assertIn("machine_flow_m2", payload)
        self.assertEqual(payload["machine_flow"]["labels"], [str(i).zfill(2) for i in range(24)])
        self.assertEqual(payload["machine_flow"]["datasets"][0]["data"][9], 1)
        self.assertAlmostEqual(payload["machine_flow_m2"]["datasets"][0]["data"][9], 4.0)

    def test_stats_returns_customer_count_and_m2(self):
        self.make_machine_db("InBat")

        inbat_db = os.path.join(self.temp_dir.name, "InBat.db")
        conn = sqlite3.connect(inbat_db)
        conn.execute(
            """
            UPDATE files
            SET file_name='khachhang_100x200_x2.prt',
                updated_time='2026-07-11 09:10:00',
                run_count=2
            WHERE file_hash='hash-3'
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InBat")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["customers"]["labels"][0], "KHACHHANG")
        self.assertEqual(payload["customers"]["data"][0], 1)
        self.assertEqual(payload["customers_m2"]["labels"][0], "KHACHHANG")
        self.assertAlmostEqual(payload["customers_m2"]["data"][0], 4.0)
        detail = payload["customer_details"]["KHACHHANG"]
        self.assertEqual(detail["summary"]["total_jobs"], 1)
        self.assertAlmostEqual(detail["summary"]["total_m2"], 4.0)
        self.assertEqual(detail["by_machine"]["InBat"], 1)
        self.assertAlmostEqual(detail["by_machine_m2"]["InBat"], 4.0)
        self.assertEqual(detail["machine_flow"]["labels"], [str(i).zfill(2) for i in range(24)])
        self.assertEqual(detail["machine_flow"]["datasets"][0]["data"][9], 1)
        self.assertAlmostEqual(detail["machine_flow_m2"]["datasets"][0]["data"][9], 4.0)

    def test_stats_strips_machine_sequence_prefix_from_customer_name(self):
        self.make_machine_db("InDecal")

        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='8~TTP_120x325.prn',
                updated_time='2026-07-11 09:10:00',
                run_count=1
            WHERE file_hash='hash-3'
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_crm_dir = Dashboard.BASE_DATA_CRM
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.BASE_DATA_CRM = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "BASE_DATA_CRM", old_crm_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InDecal")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("TTP", payload["customers"]["labels"])
        self.assertIn("TTP", payload["customers_m2"]["labels"])
        self.assertIn("TTP", payload["customer_details"])
        self.assertNotIn("8~TTP", payload["customers"]["labels"])

    def test_stats_returns_cancel_totals_by_machine_for_sidebar(self):
        self.make_machine_db("InBat")

        inbat_db = os.path.join(self.temp_dir.name, "InBat.db")
        conn = sqlite3.connect(inbat_db)
        conn.execute(
            """
            UPDATE files
            SET file_name='khachloi_100x200.prt',
                updated_time='2026-07-11 09:10:00',
                run_count=1
            WHERE file_hash='hash-3'
            """
        )
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-cancel', 'khachloi_100x200.prt', 'D:\\khachloi_100x200.prt', 'InBat', 'PRINTING', 'DELETED', '2026-07-11 10:00:00', '2026-07-11 10:05:00', 0, 1, ?)
            """,
            (
                '[{"status":"PRINTING","time":"2026-07-11 10:00:00"},{"status":"DELETED","time":"2026-07-11 10:05:00","progress_percent":50}]',
            ),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InBat")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["summary"]["total_jobs"], 1)
        self.assertEqual(payload["summary"]["cancel_jobs"], 1)
        self.assertAlmostEqual(payload["summary"]["total_m2"], 2.0)
        self.assertAlmostEqual(payload["summary"]["cancel_bad_m2"], 1.0)
        self.assertEqual(payload["cancel_by_machine"]["InBat"], 1)
        self.assertAlmostEqual(payload["cancel_bad_m2_by_machine"]["InBat"], 1.0)
        detail = payload["customer_details"]["KHACHLOI"]
        self.assertEqual(detail["summary"]["cancel_jobs"], 1)
        self.assertAlmostEqual(detail["summary"]["cancel_bad_m2"], 1.0)
        self.assertEqual(detail["cancel_by_machine"]["InBat"], 1)
        self.assertAlmostEqual(detail["cancel_bad_m2_by_machine"]["InBat"], 1.0)

    def test_stats_counts_production_cancel_embedded_in_done_history(self):
        self.make_machine_db("InDecal")

        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        history = json.dumps([
            {"status": "EXPORTED", "time": "2026-07-11 09:00:00", "event": "Xuất file"},
            {"status": "RIP", "time": "2026-07-11 09:05:00", "event": "Rip file"},
            {"status": "PRINTING", "time": "2026-07-11 09:10:00", "event": "PRINTING"},
            {
                "status": "DELETED",
                "time": "2026-07-11 09:12:00",
                "event": "DELETE",
                "old_status": "PRINTING",
                "cancel_type": "production_cancel",
                "reason": "Hủy khi đang chạy",
                "progress_percent": 25,
            },
            {"status": "PRINTING", "time": "2026-07-11 09:13:00", "event": "PRINTING", "resume_after_delete": True},
            {"status": "DONE", "time": "2026-07-11 09:25:00", "event": "In xong"},
        ], ensure_ascii=False)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='khachloi_100x200.prn',
                status='DONE',
                updated_time='2026-07-11 09:25:00',
                run_count=1,
                history=?
            WHERE file_hash='hash-3'
            """,
            (history,),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InDecal")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["summary"]["cancel_jobs"], 1)
        self.assertAlmostEqual(payload["summary"]["cancel_bad_m2"], 0.5)
        self.assertEqual(payload["cancel_by_machine"]["InDecal"], 1)
        self.assertAlmostEqual(payload["cancel_bad_m2_by_machine"]["InDecal"], 0.5)
        detail = payload["customer_details"]["KHACHLOI"]
        self.assertEqual(detail["summary"]["cancel_jobs"], 1)
        self.assertAlmostEqual(detail["summary"]["cancel_bad_m2"], 0.5)

    def test_stats_customer_top_respects_machine_filter(self):
        self.make_machine_db("InBat")
        self.make_machine_db("InDecal")

        updates = [
            ("InBat", "hash-3", "inbatkhach_100x100.prt", "2026-07-11 09:10:00"),
            ("InDecal", "hash-3", "decalkhach_100x100.prn", "2026-07-11 10:10:00"),
        ]
        for machine, file_hash, file_name, updated_time in updates:
            db_path = os.path.join(self.temp_dir.name, f"{machine}.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                UPDATE files
                SET file_name=?,
                    updated_time=?,
                    run_count=1
                WHERE file_hash=?
                """,
                (file_name, updated_time, file_hash),
            )
            conn.commit()
            conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            all_response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=ALL")
            inbat_response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InBat")
            indecal_response = client.get("/api/stats?start=2026-07-11&end=2026-07-11&machine=InDecal")

        all_payload = all_response.get_json()
        inbat_payload = inbat_response.get_json()
        indecal_payload = indecal_response.get_json()

        self.assertIn("INBATKHACH", all_payload["customers"]["labels"])
        self.assertIn("DECALKHACH", all_payload["customers"]["labels"])
        self.assertEqual(inbat_payload["customers"]["labels"], ["INBATKHACH"])
        self.assertEqual(inbat_payload["customers"]["data"], [1])
        self.assertEqual(indecal_payload["customers"]["labels"], ["DECALKHACH"])
        self.assertEqual(indecal_payload["customers"]["data"], [1])

    def test_update_status_uses_hash_when_duplicate_file_names_exist(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='same_name.prn',
                status='EXPORTED',
                updated_time='2026-07-13 08:00:00',
                history='[{"status":"EXPORTED","time":"2026-07-13 08:00:00","event":"EXPORT"}]'
            WHERE file_hash='hash-1'
            """
        )
        conn.execute(
            """
            UPDATE files
            SET file_name='same_name.prn',
                status='EXPORTED',
                updated_time='2026-07-13 09:00:00',
                history='[{"status":"EXPORTED","time":"2026-07-13 09:00:00","event":"EXPORT"}]'
            WHERE file_hash='hash-3'
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_pin = Dashboard.ADMIN_PIN
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.ADMIN_PIN = "8888"
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "ADMIN_PIN", old_pin))

        with Dashboard.app.test_client() as client:
            response = client.post(
                "/api/update_status",
                json={
                    "machine": "InDecal",
                    "name": "same_name.prn",
                    "hash": "hash-3",
                    "status": "DELETED",
                    "pin": "8888",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

        conn = sqlite3.connect(db_path)
        rows = dict(conn.execute("SELECT file_hash, status FROM files WHERE file_name='same_name.prn'").fetchall())
        selected_history = conn.execute("SELECT history FROM files WHERE file_hash='hash-3'").fetchone()[0]
        conn.close()

        self.assertEqual(rows["hash-1"], "EXPORTED")
        self.assertEqual(rows["hash-3"], "DELETED")
        self.assertIn("ADMIN_DELETE", selected_history)

    def test_update_status_does_not_append_delete_when_already_deleted(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        initial_history = '[{"status":"DELETED","time":"2026-07-14 07:06:26","event":"ADMIN_DELETE"}]'
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='8~error.prn',
                status='DELETED',
                updated_time='2026-07-14 07:06:26',
                history=?
            WHERE file_hash='hash-3'
            """,
            (initial_history,),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_pin = Dashboard.ADMIN_PIN
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.ADMIN_PIN = "8888"
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "ADMIN_PIN", old_pin))

        with Dashboard.app.test_client() as client:
            response = client.post(
                "/api/update_status",
                json={"machine": "InDecal", "name": "8~error.prn", "hash": "hash-3", "status": "DELETED", "pin": "8888"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertTrue(response.get_json()["already_current"])

        conn = sqlite3.connect(db_path)
        status, history = conn.execute("SELECT status, history FROM files WHERE file_hash='hash-3'").fetchone()
        conn.close()

        self.assertEqual(status, "DELETED")
        self.assertEqual(history, initial_history)

    def test_update_status_blocks_done_to_deleted_from_normal_admin_action(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        initial_history = '[{"status":"DONE","time":"2026-06-23 14:04:14","event":"DONE"}]'
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='8~error.prn',
                status='DONE',
                updated_time='2026-06-23 14:04:14',
                history=?
            WHERE file_hash='hash-3'
            """,
            (initial_history,),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_pin = Dashboard.ADMIN_PIN
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.ADMIN_PIN = "8888"
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "ADMIN_PIN", old_pin))

        with Dashboard.app.test_client() as client:
            response = client.post(
                "/api/update_status",
                json={"machine": "InDecal", "name": "8~error.prn", "hash": "hash-3", "status": "DELETED", "pin": "8888"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("DONE", payload["error"])

        conn = sqlite3.connect(db_path)
        status, history = conn.execute("SELECT status, history FROM files WHERE file_hash='hash-3'").fetchone()
        conn.close()

        self.assertEqual(status, "DONE")
        self.assertEqual(history, initial_history)

    def test_update_status_confirm_runs_keeps_done_and_appends_review_event(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        initial_history = '[{"status":"DONE","time":"2026-07-15 10:04:00","event":"DONE"}]'
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='Bevang1.prn',
                status='DONE',
                updated_time='2026-07-15 10:04:00',
                run_count=4,
                history=?
            WHERE file_hash='hash-3'
            """,
            (initial_history,),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_pin = Dashboard.ADMIN_PIN
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.ADMIN_PIN = "8888"
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "ADMIN_PIN", old_pin))

        with Dashboard.app.test_client() as client:
            response = client.post(
                "/api/update_status",
                json={
                    "machine": "InDecal",
                    "name": "Bevang1.prn",
                    "hash": "hash-3",
                    "status": "CONFIRM_RUNS",
                    "pin": "8888",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

        conn = sqlite3.connect(db_path)
        status, run_count, history = conn.execute(
            "SELECT status, run_count, history FROM files WHERE file_hash='hash-3'"
        ).fetchone()
        conn.close()
        events = json.loads(history)

        self.assertEqual(status, "DONE")
        self.assertEqual(run_count, 4)
        self.assertEqual(events[-1]["event"], "ADMIN_CONFIRM_RUNS")
        self.assertEqual(events[-1]["confirmed_runs"], 4)

    def test_api_data_limited_returns_first_page_with_total_counts(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        for idx in range(55):
            stamp = f"2026-07-13 10:{idx % 60:02d}:00"
            conn.execute(
                """
                INSERT INTO files
                    (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
                VALUES
                    (?, ?, ?, 'InDecal', 'PRINTING', 'DONE', ?, ?, 0, 1, '[]')
                """,
                (f"done-extra-{idx}", f"done_extra_{idx}.prn", f"D:\\done_extra_{idx}.prn", stamp, stamp),
            )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/data?start=2026-07-13&end=2026-07-13&machine=InDecal&limit=20")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["DONE"]), 20)
        self.assertEqual(payload["COUNTS"]["DONE"], 55)

    def test_api_data_limited_does_not_resolve_thumbnails_synchronously(self):
        self.make_machine_db("InDecal")
        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with mock.patch.object(
            Dashboard,
            "collect_machine_file_meta_for_server",
            side_effect=AssertionError("board list must not scan machine shares"),
        ), mock.patch.object(
            Dashboard,
            "generate_thumb_from_source",
            side_effect=AssertionError("board list must not generate thumbnails"),
        ):
            with Dashboard.app.test_client() as client:
                response = client.get("/api/data?start=2026-07-15&end=2026-07-15&machine=InDecal&limit=20")

        self.assertEqual(response.status_code, 200)
        self.assertIn("DONE", response.get_json())

    def test_api_data_limited_returns_paused_machine_file_without_running_count(self):
        self.make_machine_db("CNC")
        db_path = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO files
                (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
            VALUES
                ('hash-paused', 'VCTT_F5_120X50.tap', 'D:\\CNC\\2026-07-14\\VCTT_F5_120X50.tap', 'CNC', 'CUTTING', 'PAUSE',
                 '2026-07-14 17:12:02', '2026-07-14 17:35:45', 0, 1,
                 '[{"status":"CUTTING","time":"2026-07-14 17:12:02"},{"status":"PAUSE","time":"2026-07-14 17:35:29","event":"PAUSE"}]')
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/data?start=2026-07-14&end=2026-07-14&machine=CNC&limit=20")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        paused = [item for item in payload["RUNNING"] if item["name"] == "VCTT_F5_120X50.tap"]
        self.assertEqual(len(paused), 1)
        self.assertEqual(paused[0]["stage_key"], "PAUSED")
        self.assertEqual(paused[0]["stage_label"], "Đang dừng")
        self.assertEqual(payload["COUNTS"]["RUNNING"], 0)

    def test_cnc_progress_thumb_falls_back_to_static_thumb_without_current_line(self):
        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        with open(os.path.join(thumb_dir, "hash-old.jpg"), "wb") as handle:
            handle.write(b"static-thumb")

        db_path = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE files (
                file_hash TEXT PRIMARY KEY,
                file_name TEXT,
                file_path TEXT,
                machine_meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO files (file_hash, file_name, file_path, machine_meta_json)
            VALUES ('hash-old', 'old.tap', 'D:\\CNC\\old.tap', '{}')
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_thumb_dir = Dashboard.THUMB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.THUMB_DIR = thumb_dir
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "THUMB_DIR", old_thumb_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/cnc-progress-thumb/hash-old.jpg?v=v2-7000")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, b"static-thumb")

    def test_missing_thumb_is_generated_from_design_source(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")

        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        design_path = os.path.join(self.temp_dir.name, "yte_600x240.jpg")
        Image.new("RGB", (80, 40), "green").save(design_path)

        db_path = os.path.join(self.temp_dir.name, "InBat.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE files (
                file_hash TEXT PRIMARY KEY,
                file_name TEXT,
                file_path TEXT,
                updated_time TEXT,
                machine_meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO files (file_hash, file_name, file_path, updated_time, machine_meta_json)
            VALUES ('hash-preview', 'yte_600x240.prt', 'D:\\2026-07-14\\New Folder\\yte_600x240.prt',
                    '2026-07-15 08:36:09', ?)
            """,
            (json.dumps({"design_metadata_source": design_path}),),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_thumb_dir = Dashboard.THUMB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.THUMB_DIR = thumb_dir
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "THUMB_DIR", old_thumb_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/thumbs/hash-preview.jpg")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertTrue(os.path.exists(os.path.join(thumb_dir, "hash-preview.jpg")))
        self.assertGreater(len(response.data), 100)

    def test_item_thumbnail_generated_from_indecal_ready_rip_fallback(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")

        thumb_dir = os.path.join(self.temp_dir.name, "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        preview_path = os.path.join(self.temp_dir.name, "Vietphuong2.prn.bmp")
        Image.new("RGB", (80, 40), "blue").save(preview_path)

        old_thumb_dir = Dashboard.THUMB_DIR
        Dashboard.THUMB_DIR = thumb_dir
        self.addCleanup(lambda: setattr(Dashboard, "THUMB_DIR", old_thumb_dir))

        row = (
            "hash-indecal",
            "Vietphuong2.prn",
            "Vietphuong2.prn",
            "PRINTING",
            "2026-07-15 16:27:25",
            "2026-07-15 16:34:53",
            1,
            '[{"status":"PRINTING","time":"2026-07-15 16:27:25"}]',
            0,
            json.dumps({"metadata_source": "Vietphuong2.prn"}),
        )

        with mock.patch.object(Dashboard, "collect_machine_file_meta_for_server") as collect_mock:
            collect_mock.return_value = {
                "resolved_file_path": r"\\InDecal\D\Tem\Vietphuong2.prn",
                "preview_source": preview_path,
            }

            item = Dashboard.build_board_item("InDecal", row, set(), {}, [], [])

        collect_mock.assert_called_with(
            "InDecal",
            "Vietphuong2.prn",
            "Vietphuong2.prn",
            "2026-07-15 16:34:53",
        )
        self.assertTrue(item["has_thumbnail"])
        self.assertTrue(os.path.exists(os.path.join(thumb_dir, "hash-indecal.jpg")))

    def test_cnc_progress_thumb_uses_existing_progress_cache_before_tap_lookup(self):
        progress_dir = os.path.join(self.temp_dir.name, "thumbs", "cnc_progress")
        os.makedirs(progress_dir, exist_ok=True)
        with open(os.path.join(progress_dir, "v2_hash-run_2000_123.jpg"), "wb") as handle:
            handle.write(b"progress-cache")

        db_path = os.path.join(self.temp_dir.name, "CNC.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE files (
                file_hash TEXT PRIMARY KEY,
                file_name TEXT,
                file_path TEXT,
                machine_meta_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO files (file_hash, file_name, file_path, machine_meta_json)
            VALUES ('hash-run', 'run.tap', 'D:\\CNC\\missing.tap',
                    '{"current_line": 1900, "metadata_source": "D:\\\\CNC\\\\missing.tap"}')
            """
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        old_progress_dir = Dashboard.CNC_PROGRESS_THUMB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        Dashboard.CNC_PROGRESS_THUMB_DIR = progress_dir
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))
        self.addCleanup(lambda: setattr(Dashboard, "CNC_PROGRESS_THUMB_DIR", old_progress_dir))

        with mock.patch.object(Dashboard, "find_existing_tap", side_effect=AssertionError("tap lookup should not run")):
            with Dashboard.app.test_client() as client:
                response = client.get("/cnc-progress-thumb/hash-run.jpg?v=v2-2000")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        self.assertEqual(response.data, b"progress-cache")

    def test_api_data_problem_counts_match_visible_items_after_cleanup_filter(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        conn = sqlite3.connect(db_path)
        rows = [
            (
                "cleanup-deleted",
                "old_120x40.tif",
                "D:\\old_120x40.tif",
                "DELETED",
                "2026-07-14 08:00:00",
                '[{"status":"DELETED","time":"2026-07-14 08:00:00","event":"DELETE"}]',
            ),
            (
                "cleanup-done",
                "1~old_120x40.prn",
                "D:\\1~old_120x40.prn",
                "DONE",
                "2026-07-14 08:10:00",
                '[{"status":"DONE","time":"2026-07-14 08:10:00","event":"DONE"}]',
            ),
            (
                "real-delete",
                "real_delete.prn",
                "D:\\real_delete.prn",
                "DELETED",
                "2026-07-14 09:00:00",
                '[{"status":"DELETED","time":"2026-07-14 09:00:00","event":"ADMIN_DELETE"}]',
            ),
        ]
        for file_hash, name, path, status, stamp, history in rows:
            conn.execute(
                """
                INSERT INTO files
                    (file_hash, file_name, file_path, machine, job_type, status, created_time, updated_time, zalo_sent, run_count, history)
                VALUES
                    (?, ?, ?, 'InDecal', 'PRINTING', ?, ?, ?, 0, 1, ?)
                """,
                (file_hash, name, path, status, stamp, stamp, history),
            )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/data?start=2026-07-14&end=2026-07-14&machine=InDecal&limit=20")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["COUNTS"]["REMOVED"], 1)
        self.assertEqual(payload["COUNTS"]["PROBLEM"], 1)
        self.assertEqual([item["name"] for item in payload["REMOVED"]], ["real_delete.prn"])

    def test_api_data_keeps_production_cancel_history_as_real_error_after_done(self):
        self.make_machine_db("InDecal")
        db_path = os.path.join(self.temp_dir.name, "InDecal.db")
        history = json.dumps([
            {"status": "EXPORTED", "time": "2026-07-14 14:55:29", "event": "Xuất file"},
            {"status": "RIP", "time": "2026-07-14 15:15:51", "event": "Rip file"},
            {"status": "PRINTING", "time": "2026-07-14 16:11:10", "event": "PRINTING"},
            {
                "status": "DELETED",
                "time": "2026-07-14 16:11:17",
                "event": "DELETE",
                "old_status": "PRINTING",
                "cancel_type": "production_cancel",
                "reason": "Hủy khi đang chạy",
                "progress_percent": 0.6993006993006993,
            },
            {"status": "PRINTING", "time": "2026-07-14 16:11:30", "event": "PRINTING", "resume_after_delete": True},
            {"status": "DONE", "time": "2026-07-14 16:21:50", "event": "In xong"},
        ])
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            UPDATE files
            SET file_name='9~utteo1_pp_120x240.prn',
                file_path='D:\\9~utteo1_pp_120x240.prn',
                status='DONE',
                created_time='2026-07-14 14:55:29',
                updated_time='2026-07-14 16:21:50',
                history=?
            WHERE file_hash='hash-3'
            """,
            (history,),
        )
        conn.commit()
        conn.close()

        old_db_dir = Dashboard.DB_DIR
        Dashboard.DB_DIR = self.temp_dir.name
        self.addCleanup(lambda: setattr(Dashboard, "DB_DIR", old_db_dir))

        with Dashboard.app.test_client() as client:
            response = client.get("/api/data?start=2026-07-14&end=2026-07-14&machine=InDecal&limit=20")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        done_names = [item["name"] for item in payload["DONE"]]
        canceled = [item for item in payload["CANCELED"] if item["name"] == "9~utteo1_pp_120x240.prn"]

        self.assertIn("9~utteo1_pp_120x240.prn", done_names)
        self.assertEqual(len(canceled), 1)
        self.assertEqual(payload["COUNTS"]["CANCELED"], 1)
        self.assertEqual(payload["COUNTS"]["PROBLEM"], 1)
        self.assertEqual(canceled[0]["cancel_type"], "production_cancel")
        self.assertEqual(canceled[0]["cancel_reason"], "Hủy khi đang chạy")
        self.assertEqual(canceled[0]["updated"], "2026-07-14 16:11:17")
        self.assertEqual(canceled[0]["time_short"], "16:11:17")
        self.assertEqual(canceled[0]["progress_source"], "explicit")

    def test_stats_ui_keeps_only_machine_flow_chart_with_metric_toggle_above_summary(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertNotIn("Hiệu suất diện tích (m2)", html)
        self.assertNotIn("Top khách hàng VIP (số đơn)", html)
        self.assertIn("Báo cáo khách hàng và đơn hàng", html)
        self.assertIn("Đơn hàng theo máy", html)
        self.assertIn("Khách hàng theo tên file", html)
        self.assertIn('class="erp-sum-card total-summary-card"', html)
        self.assertIn('class="total-summary-row"', html)
        self.assertIn('class="total-summary-value done-value"', html)
        self.assertIn('class="total-summary-value error-value"', html)
        self.assertNotIn('id="erp-total-label"', html)
        self.assertNotIn('id="erp-total-error-label"', html)
        self.assertNotIn("document.getElementById('erp-total-label')", html)
        self.assertNotIn("document.getElementById('erp-total-error-label')", html)
        self.assertIn('input[type="date"]::-webkit-calendar-picker-indicator', html)
        self.assertIn("data:image/svg+xml", html)
        self.assertIn("%23f3f6fb", html)

    def test_card_preview_has_inline_admin_status_actions(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('id="cardPreviewActions"', html)
        self.assertIn("adminStatusUpdateBusy", html)
        self.assertIn("setAdminStatusBusy(true)", html)
        self.assertIn("setAdminStatusBusy(false)", html)
        self.assertIn("previewForceUpdate('DONE')", html)
        self.assertIn("previewForceUpdate('DELETED')", html)
        self.assertIn("previewForceUpdate('EXPORTED')", html)
        self.assertIn("data-hash=", html)
        self.assertIn("hash: file.hash", html)
        self.assertIn("syncPreviewAdminActions()", html)
        self.assertIn("has-admin", html)
        self.assertNotIn("has-file", html)
        self.assertNotIn("card.addEventListener('dblclick'", html)

    def test_board_sanitize_keeps_real_production_cancel_visible(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn("type === 'production_cancel'", html)
        self.assertIn("clean.COUNTS.CANCELED = clean.CANCELED.length", html)
        self.assertIn("clean.COUNTS.PROBLEM = clean.COUNTS.CANCELED + clean.COUNTS.REMOVED", html)

    def test_detail_modal_has_confirm_runs_admin_action(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('id="confirmRunsBtn"', html)
        self.assertIn("function confirmRuns()", html)
        self.assertIn("status: 'CONFIRM_RUNS'", html)
        self.assertIn("reprint_needs_review", html)
        self.assertIn("Xác nhận In x", html)

    def test_card_preview_has_lightweight_print_progress_overlay(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('id="cardPreviewImageWrap"', html)
        self.assertIn('id="cardPreviewProgress"', html)
        self.assertIn("preview-print-progress", html)
        self.assertIn("syncPreviewPrintProgress(card)", html)
        self.assertIn("file.machine === 'InBat' || file.machine === 'InDecal'", html)
        self.assertIn("--print-progress", html)

    def test_cnc_progress_cache_buckets_nearby_lines(self):
        self.assertEqual(Dashboard.cnc_progress_cache_line(70194), 70000)
        self.assertEqual(Dashboard.cnc_progress_cache_line(70499), 70000)
        self.assertEqual(Dashboard.cnc_progress_cache_line(70501), 71000)

    def test_main_tabs_do_not_show_unused_excel_export_button(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertNotIn('title="Xuất Excel"', html)
        self.assertNotIn('aria-label="Xuất Excel"', html)
        self.assertNotIn('onclick="exportExcel()"', html)
        self.assertNotIn("function exportExcel()", html)

    def test_machine_sidebar_uses_compact_power_toggle_not_text_status_pill(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn("machine-power-toggle", html)
        self.assertIn("machinePowerTitle", html)
        self.assertIn("runningPowerTitle", html)
        self.assertIn('aria-label="${escapeHtml(runningPowerTitle)}"', html)
        self.assertNotIn("const onlineText = m.online ? 'ĐANG MỞ'", html)
        self.assertNotIn('<span class="status-pill ${onlineClass}">${onlineText}</span>', html)

    def test_card_preview_detail_hides_machine_meta_source_kind(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn("<span>Kích thước</span>", html)
        self.assertIn("function displayPrintSizeCm(file)", html)
        self.assertIn("sameAreaSize(raw, design)", html)
        self.assertIn("Khổ in", html)
        self.assertNotIn("Khổ in thật", html)
        self.assertIn("Khổ ảnh", html)
        self.assertIn("<span>Khổ thiết kế</span>", html)
        self.assertIn("<span>DPI</span>", html)
        self.assertNotIn("<span>Nguồn</span>", html)
        self.assertNotIn("meta.source_kind === 'rip_preview_bmp'", html)

    def test_production_filter_shows_loading_and_limits_rendered_cards(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('id="refreshBtn"', html)
        self.assertIn("setBoardLoading(true)", html)
        self.assertIn("setBoardLoading(false)", html)
        self.assertIn("const BOARD_PAGE_INCREMENT = 20", html)
        self.assertIn("renderCardList(items, totalCount)", html)
        self.assertIn("loadMoreBoard(event)", html)
        self.assertIn("bấm hoặc cuộn để tải", html)
        self.assertIn("visible.length >= Math.max(1, boardVisibleLimit - 1)", html)
        self.assertIn("scheduleStatsFetch(currentMainTab === 'flow' ? 0 : 900)", html)
        self.assertIn("&limit=${boardVisibleLimit}", html)
        self.assertNotIn("function applyGlobalFilters() {\r\n            fetchData();\r\n            fetchERP();", html)
        self.assertIn('id="orderFlowChart"', html)
        self.assertIn('id="flowCustomerChart"', html)
        self.assertIn('class="flow-report-stack"', html)
        self.assertNotIn('class="flow-side-grid"', html)
        self.assertNotIn('id="flowCustomerList"', html)
        self.assertNotIn('id="flowAlertList"', html)
        self.assertNotIn('id="flowMachineList"', html)
        self.assertIn('id="flowMetricCount"', html)
        self.assertIn('id="orderFlowTitle"', html)
        self.assertIn('id="reportDetailGrid"', html)
        self.assertIn('id="clearCustomerFilterBtn"', html)
        self.assertIn("let selectedReportCustomer = '';", html)
        self.assertIn("function selectReportCustomer(customer)", html)
        self.assertIn("function clearCustomerFilter()", html)
        self.assertIn("function renderReportDetail(data)", html)
        self.assertIn('id="erp-total-error-main"', html)
        self.assertIn('id="erp-inbat-error"', html)
        self.assertIn('id="erp-indecal-error"', html)
        self.assertIn('id="erp-cnc-error"', html)
        self.assertIn("const totalError = flowMetric === 'm2' ? Number(summary.cancel_bad_m2 || 0) : Number(summary.cancel_jobs || 0);", html)
        self.assertIn("data.cancel_bad_m2_by_machine", html)
        self.assertIn("data.cancel_by_machine", html)
        self.assertNotIn('id="erp-err-rate"', html)
        self.assertIn("grid-template-rows: minmax(170px, 1fr) minmax(160px, 0.95fr) minmax(118px, auto);", html)
        self.assertIn(".report-detail-panel { display: grid; gap: 8px; min-height: 0; overflow: hidden; }", html)
        self.assertIn("function compactFlow(flow)", html)
        self.assertIn("function flowTickLabel(label, spanDays)", html)
        self.assertIn("function flowSpanDays(labels)", html)
        self.assertIn("if (spanDays > 120)", html)
        self.assertIn("return day <= 15 ? `01/${month}` : `15/${month}`;", html)
        self.assertIn("return String(date.getDate()).padStart(2, '0');", html)
        self.assertIn("const keepIndexes = labels.map((label, index) =>", html)
        self.assertIn("function trimOuterEmptyFlow(flow)", html)
        self.assertIn("const firstDataIndex = labels.findIndex(hasValue);", html)
        self.assertIn("let lastDataIndex = labels.length - 1;", html)
        self.assertIn("const flow = trimOuterEmptyFlow(selectedCustomerFlow(data, flowMetric) || fallbackFlow);", html)
        self.assertIn("const spanDays = flowSpanDays(flow.labels || []);", html)
        self.assertIn("callback: function(value) { return flowTickLabel(this.getLabelForValue(value), spanDays); }", html)
        self.assertNotIn("const flow = bucketFlowForDisplay(selectedCustomerFlow(data, flowMetric) || fallbackFlow);", html)
        self.assertNotIn("bucketFlowForDisplay(selectedCustomerFlow(data, flowMetric) || fallbackFlow)", html)
        self.assertIn("window.lastRenderedFlowLabels = flow.labels || [];", html)
        self.assertLess(html.index('id="flowMetricCount"'), html.index('class="erp-summary-row"'))

    def test_quick_date_clamps_current_ranges_to_today_and_shows_loading(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn("if (end > today) end = today;", html)
        self.assertIn("setReportLoading(true);", html)
        self.assertIn("function setReportLoading(isLoading, message)", html)
        self.assertIn("if (statsRequestId !== requestId) return;", html)

    def test_dashboard_template_has_compact_layout_c_landmarks(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('class="compact-shell"', html)
        self.assertIn('class="compact-sidebar"', html)
        self.assertIn('class="compact-main"', html)
        self.assertIn('id="main-tab-production"', html)
        self.assertIn('id="customerChart"', html)
        self.assertIn('id="attentionBadge"', html)
        self.assertIn('id="compact-empty-state"', html)
        self.assertIn("compact-board.all-empty", html)
        self.assertNotIn(".compact-board.all-empty {\n            display: none;", html)
        self.assertIn(".compact-board.all-empty + .empty-state", html)
        self.assertNotIn('<h2>Hàng chờ', html)
        self.assertIn('<h2>In xong', html)
        self.assertNotIn('<h2>Lỗi / thao tác', html)
        self.assertIn("Hàng chờ", html)
        self.assertIn("In xong", html)
        self.assertIn("Lỗi", html)
        self.assertIn("Hủy", html)
        self.assertIn('class="column col-export queue-column"', html)
        self.assertIn('id="queue-list"', html)
        self.assertIn('id="queue-tab-all"', html)
        self.assertIn('id="queue-tab-export"', html)
        self.assertIn('id="queue-tab-rip"', html)
        self.assertNotIn('id="queue-tab-running"', html)
        self.assertNotIn('id="count-queue-running"', html)
        self.assertIn("function showMachineRunningPreview(event, machine)", html)
        self.assertIn("function runningProgressPercent(file)", html)
        self.assertIn("function runningSizeLabel(file)", html)
        self.assertIn("function displayPrintSizeCm(file)", html)
        self.assertIn("function runningRealSizeLabel(file)", html)
        self.assertIn("function cardSizeLabel(file)", html)
        self.assertIn("const cardSize = cardSizeLabel(file);", html)
        self.assertIn('class="card-real-size"', html)
        self.assertIn("${cardSize ? ` | <span class=\"card-real-size\">${escapeHtml(cardSize)}</span>` : ''}", html)
        self.assertIn("function runningActiveLabel(machine, runningFile, progress, changed)", html)
        self.assertIn("const runningActive = runningActiveLabel(m.machine, runningFile, runningProgress, runningProgressChanged);", html)
        self.assertIn("const runningPowerClass = runningFile ? (runningPaused ? 'is-paused-running' : 'is-active-running') : powerClass;", html)
        self.assertIn("const runningPowerTitle = runningFile ? runningPowerStatusTitle(m.machine, runningFile, runningProgress) : machinePowerTitle(m);", html)
        self.assertIn("const runningProgressChanged = hasRunningProgressChanged(m.machine, runningFile, runningProgress);", html)
        self.assertIn('${runningActive ? `<span class="machine-status-kpi ${runningPaused ? \'is-paused\' : \'is-running\'} ${runningProgressChanged ? \'is-updated\' : \'\'}">${runningActive}</span>` : \'\'}', html)
        self.assertIn(".machine-status-kpi { display: inline-flex; align-items: center; gap: 4px; padding: 0;", html)
        self.assertIn(".machine-status-kpi.is-paused { color: #fde68a; }", html)
        self.assertIn(".machine-status-kpi.is-running { color: #bbf7d0; }", html)
        self.assertNotIn(".machine-status-kpi.is-paused { color: #fde68a; background:", html)
        self.assertNotIn(".machine-status-kpi.is-running { color: #bbf7d0; background:", html)
        self.assertIn(".machine-power-toggle.is-active-running, .machine-power-toggle.is-paused-running {\n            width: auto;", html)
        self.assertIn("border-radius: 0;\n            min-width: 0;", html)
        self.assertIn(".machine-power-toggle.is-active-running::before { content: '▶';", html)
        self.assertIn(".machine-power-toggle.is-paused-running::before { content: '⏸';", html)
        self.assertNotIn('<span class="machine-status-icon">⏸</span>', html)
        self.assertNotIn('<span class="machine-status-icon">▶</span>', html)
        self.assertIn("function hasRunningProgressChanged(machine, runningFile, progress)", html)
        self.assertIn("function runningEtaInfo(file)", html)
        self.assertIn("const runningEtaSamples = new Map();", html)
        self.assertIn("const RUNNING_ETA_STORAGE_KEY = 'qlx_running_eta_samples_v2';", html)
        self.assertIn("function runningProgressCounter(file)", html)
        self.assertIn("function sampledRemainingMs(file, counter)", html)
        self.assertIn("const count = counter.count;", html)
        self.assertIn("const total = counter.total;", html)
        self.assertIn("if (last && (last.count > count || Math.abs(Number(last.total || 0) - total) > 0.001)) samples.length = 0;", html)
        self.assertIn("elapsed >= 20000", html)
        self.assertIn("gained >= 1", html)
        self.assertIn("saveRunningEtaSamples();", html)
        self.assertIn("runningEtaSamples.delete(key);", html)
        self.assertNotIn("if (file?.machine === 'InBat') return 'còn lại chưa rõ';", html)
        self.assertIn("const counter = runningProgressCounter(file);", html)
        self.assertIn("if (machine === 'InBat' || machine === 'InDecal') {", html)
        self.assertIn("const pathCount = Number(meta.current_path_length || 0);", html)
        self.assertIn("const pathTotal = Number(meta.total_path_length || 0);", html)
        self.assertIn("if (Number.isFinite(pathCount) && Number.isFinite(pathTotal) && pathTotal > 0) return { count: pathCount, total: pathTotal };", html)
        self.assertIn("return 'đang tính thời gian';", html)
        self.assertIn('file.status === "DONE" ? " | Đã xong"', html)
        self.assertIn("const isPaused = file.status === 'PAUSE' || file.stage_key === 'PAUSED' || file.is_paused;", html)
        self.assertIn("if (!isPrinting && !isPaused) return;", html)
        self.assertIn('data-running-hash="${escapeHtml(runningFile?.hash || \'\')}"', html)
        self.assertIn('class="machine-running-file"', html)
        self.assertIn('class="machine-running-real-size"', html)
        self.assertIn('${runningSize ? ` | <span class="machine-running-size">${escapeHtml(runningSize)}</span>` : \'\'}', html)
        self.assertNotIn('class="machine-running-meta"', html)
        self.assertIn('class="machine-running-eta">${escapeHtml(runningEta)}</div>', html)
        self.assertIn('class="machine-running-progress"', html)
        self.assertIn('style="width: ${runningProgress.percent}%"', html)
        self.assertNotIn('class="machine-running-percent"', html)
        self.assertIn("runningPaused", html)
        self.assertIn("is-paused", html)
        self.assertIn("is-running", html)
        self.assertIn("return 'tạm dừng';", html)
        self.assertIn("@keyframes machine-running-pulse", html)
        self.assertIn("let previewLoadToken = 0;", html)
        self.assertIn("const previewImageCache = new Map();", html)
        self.assertIn("function preloadPreviewImage(src)", html)
        self.assertIn("let machineProgressPollTimer = null;", html)
        self.assertIn("const MACHINE_PROGRESS_POLL_MS = 3000;", html)
        self.assertIn("function startMachineProgressPolling()", html)
        self.assertIn("function stopMachineProgressPolling()", html)
        self.assertIn("machineProgressPollTimer = setInterval(() => {", html)
        self.assertIn("fetchData();", html)
        self.assertIn("}, MACHINE_PROGRESS_POLL_MS);", html)
        self.assertIn('.card[data-thumb*="/cnc-progress-thumb/"]', html)
        self.assertIn("setTimeout(run, 50);", html)
        self.assertIn("const sameSource = src && img.getAttribute('src') === src;", html)
        self.assertIn("if (loadToken !== previewLoadToken) return;", html)
        self.assertIn("let productionQueueTab = 'QUEUE';", html)
        self.assertIn("QUEUE: fExport.map(f => ({...f, stage_label: 'Xuất', stage_key: 'EXPORTED'}))", html)
        self.assertIn("--stage-export:#00a3ff", html)
        self.assertIn("--stage-rip:#a855f7", html)
        self.assertIn("--stage-run:#22c55e", html)
        self.assertIn('class="stage-chip ${cardStageClass}"', html)
        self.assertIn(".card.stage-done .card-name { color: #86efac; }", html)
        self.assertIn("renderCardList(fDone.map(f => ({...f, stage_key: 'DONE'})), boardCount('DONE', fDone.length))", html)
        self.assertIn("--ui-active-bg:#173154", html)
        self.assertIn("box-shadow: inset 0 -2px 0 var(--ui-active-shadow)", html)
        self.assertIn("function setProductionQueueTab(tab)", html)
        self.assertNotIn('id="run-compact-list"', html)
        self.assertIn('class="column col-cancel problem-column"', html)
        self.assertIn('id="problem-tab-all"', html)
        self.assertIn('id="problem-tab-canceled"', html)
        self.assertIn('id="problem-tab-removed"', html)
        self.assertIn('id="problem-list"', html)
        self.assertIn("let productionProblemTab = 'PROBLEM';", html)
        self.assertIn("PROBLEM: trueProblemItems.concat(removedProblemItems).sort(sortFn)", html)
        self.assertIn("function setProductionProblemTab(tab)", html)
        self.assertNotIn('class="problem-stack"', html)
        self.assertNotIn('id="true-problem-list"', html)
        self.assertNotIn('id="removed-problem-list"', html)
        self.assertIn('repeat(3, minmax(220px, 1fr))', html)
        self.assertIn('grid-template-columns: repeat(2, minmax(220px, 1fr))', html)
        self.assertIn('@media screen and (min-width: 1800px)', html)
        self.assertIn('grid-template-columns: 340px minmax(0, 1fr)', html)
        self.assertIn('grid-template-columns: repeat(3, minmax(320px, 1fr))', html)
        self.assertIn('grid-template-columns: 1fr auto', html)
        self.assertIn('grid-column: 1 / -1', html)
        self.assertIn('flex-wrap: wrap', html)
        self.assertIn("Chờ xử lý", html)
        self.assertIn('title="Việc chờ xử lý"', html)
        self.assertLess(html.index('id="tab-system"'), html.index('id="tab-attention"'))
        self.assertIn('function positionDetailModal(anchorEl)', html)
        self.assertIn('openDetailModal(item.dataset.machine, item.dataset.name, item)', html)
        self.assertIn('positionDetailModal(currentDetailAnchor);', html)
        self.assertIn('id="main-tab-technical"', html)
        self.assertNotIn('id="tab-technical"', html)
        self.assertNotIn('title="6 bước kỹ thuật">Kỹ thuật</button>', html)
        self.assertIn('id="main-tab-customers"', html)
        self.assertNotIn('id="tab-customers"', html)
        self.assertIn('onclick="switchMainTab(\'flow\')" title="Mở báo cáo khách hàng"', html)
        self.assertIn('id="tab-system"', html)
        self.assertIn(">Hệ thống</button>", html)
        self.assertIn('id="main-tab-system"', html)
        self.assertIn('id="v2-status-body" class="status-shell system-status-body"', html)
        self.assertNotIn('id="tab-log"', html)
        self.assertNotIn(">Log</button>", html)
        self.assertNotIn('id="main-tab-log"', html)
        self.assertIn('id="system-log-body" class="system-log-body"', html)
        self.assertIn("'system'].includes(tab)", html)
        self.assertIn("#main-tab-system .status-overview,", html)
        self.assertIn("#main-tab-system .ops-advanced-grid { display: none; }", html)
        self.assertIn("Không thấy file outbox trên server", html)
        self.assertIn("Outbox hiện chỉ phục vụ retry", html)
        self.assertIn("class=\"system-note-list\"", html)
        self.assertIn("version_history", html)
        self.assertIn("Lịch sử đổi bản", html)
        self.assertIn("Bản đang chạy", html)
        self.assertIn("Ping cuối", html)
        self.assertIn("version-status-table", html)
        self.assertIn("version-history-table", html)
        self.assertIn("function showVersionHistory(machine)", html)
        self.assertIn("version-inline-history", html)
        self.assertIn("selectedRow.after(historyRow)", html)
        self.assertNotIn("Chọn 1 máy ở bảng trên để xem", html)
        self.assertIn("data-version-machine", html)
        self.assertIn(".system-status-body { height: 100%; overflow: hidden; padding-right: 2px; display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 10px; }", html)
        self.assertIn(".system-viewer-head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto;", html)
        self.assertIn('id="systemViewerNote" class="system-viewer-note"', html)
        self.assertIn(".system-viewer-path { display: none; }", html)
        self.assertIn(".system-viewer-body .log-tail { height: 100%; max-height: none; margin: 0; box-sizing: border-box; overflow: auto; }", html)
        self.assertIn('class="system-source-list"', html)
        self.assertIn("class=\"system-source-btn ${index === selectedSystemIndex ? 'active' : ''}\"", html)
        self.assertIn('class="system-source-name"', html)
        self.assertIn('class="system-viewer"', html)
        self.assertNotIn('class="log-source-meta"', html)
        self.assertNotIn('class="log-source-path"', html)
        self.assertIn('const latestFirstLogTail = (log.tail || []).slice().reverse();', html)
        self.assertIn("body: `<div class=\"log-tail\">${escapeHtml(latestFirstLogTail.join(", html)
        self.assertIn('function selectSystemItem(index)', html)
        self.assertIn('function selectSystemLog(index)', html)
        self.assertIn('window.systemItems = systemItems;', html)
        self.assertIn('window.selectedSystemName', html)
        self.assertIn('window.selectedSystemIndex', html)
        self.assertIn('id="systemViewerBody"', html)
        self.assertIn('if (tail) tail.scrollTop = 0;', html)
        self.assertNotIn('<div class="status-card full machine-status-card"><h3>Máy sản xuất</h3>', html)
        self.assertNotIn('<details class="detail-card ops-advanced" open>', html)
        self.assertIn("name: 'Outbox'", html)
        self.assertIn("name: 'Phiên bản'", html)
        self.assertIn("name: 'Tổng quan'", html)
        self.assertIn("name: 'InDecal rename/RIP'", html)
        self.assertIn("data.rename_audit || {}", html)
        self.assertIn("Audit rename, meta, RIP của máy InDecal", html)
        self.assertNotIn("name: 'Ghi chú'", html)
        self.assertNotIn("name: 'Ghi chú 2'", html)
        self.assertIn("const offset = 5;", html)
        self.assertIn("name: 'Tiến trình V2'", html)
        self.assertIn("runtimeProcesses", html)
        self.assertIn("Bản mong đợi", html)
        self.assertIn(".machine-health", html)
        self.assertIn("NcStudio:", html)
        self.assertIn('<div class="system-note-row"><span>Máy đang mở</span>', html)
        self.assertIn("Xuất file", html)
        self.assertIn('class="flow-dashboard"', html)
        self.assertIn('class="flow-report-stack"', html)
        self.assertIn('id="orderFlowChart"', html)
        self.assertIn('id="flowCustomerChart"', html)
        self.assertIn(">Báo cáo</button>", html)
        self.assertNotIn("Xem 6 bước kỹ thuật", html)
        self.assertNotIn("flow-detail-open", html)
        self.assertNotIn("setupProductionModeToggle", html)
        self.assertNotIn(">Chờ chạy", html)
        self.assertNotIn(">Vấn đề", html)
        self.assertIn('id="authBtn"', html)
        self.assertIn('class="top-navbar-brand"', html)
        self.assertIn('/assets/brand-logo.png', html)
        self.assertIn('function machineIcon(machine)', html)
        self.assertIn('machine-icon machine-icon-InBat', html)
        self.assertIn('machine-icon machine-icon-InDecal', html)
        self.assertIn('machine-icon machine-icon-CNC', html)
        self.assertIn('btn.innerHTML = accountIconMarkup()', html)
        self.assertIn('class="account-icon"', html)
        self.assertNotIn('btn.innerText = "⚙"', html)
        self.assertNotIn('btn.innerText = "Admin"', html)
        self.assertIn("function positionCardPreview(card)", html)
        self.assertIn("window.innerHeight - previewHeight - margin", html)
        self.assertIn("preview.style.maxHeight = maxPreviewHeight + 'px'", html)
        self.assertIn(".card-preview { position: fixed;", html)
        self.assertIn("keepPosition: previewPinned", html)
        self.assertIn("if (!keepPosition) positionCardPreview(card)", html)
        self.assertNotIn("preview.style.left = (window.scrollX + leftViewport) + 'px'", html)
        self.assertNotIn("preview.style.top = (window.scrollY + topViewport) + 'px'", html)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))", html)
        self.assertIn("list.innerHTML = items.map(renderAttentionItem).join('')", html)

    def test_dashboard_public_assets_are_served(self):
        with Dashboard.app.test_client() as client:
            logo_response = client.get("/assets/brand-logo.png")
            icon_response = client.get("/assets/machine-icons/inbat.svg")

        self.assertEqual(logo_response.status_code, 200)
        self.assertEqual(icon_response.status_code, 200)
        self.assertIn(b"<svg", icon_response.data[:320])
        logo_response.close()
        icon_response.close()

    def test_inbat_uses_green_machine_color(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn("--machine-inbat:#22c55e", html)
        self.assertIn("InBat: '#22c55e'", html)
        self.assertNotIn("--machine-inbat:#ffd700", html)
        self.assertNotIn("InBat: '#ffd700'", html)

    def test_missing_thumbnail_reason_reports_deleted_source(self):
        reason = Dashboard.missing_thumbnail_reason({
            "name": "xd4.tif",
            "file_path": r"D:\2026-07-11\xd4.tif",
            "has_thumbnail": False,
        })

        self.assertIn("xd4.tif", reason)
        self.assertIn("xóa", reason)

    def test_missing_thumbnail_reason_reports_incomplete_path(self):
        reason = Dashboard.missing_thumbnail_reason({
            "name": "13~hhhh_decal_62x62.prn",
            "file_path": "13~hhhh_decal_62x62.prn",
            "has_thumbnail": False,
        })

        self.assertIn("đường dẫn", reason)

    def test_build_attention_items_prioritizes_actionable_jobs(self):
        items = Dashboard.build_attention_items({
            "CANCELED": [
                {
                    "machine": "InBat",
                    "name": "fast_done_450x60.prt",
                    "cancel_reason": "DONE trước đó quá nhanh (1 phút 17 giây) - cần kiểm tra tín hiệu/máy",
                    "progress_source": "estimated",
                    "has_thumbnail": True,
                },
                {
                    "machine": "InDecal",
                    "name": "unknown_120x100.prn",
                    "cancel_reason": "Hủy khi đang chạy",
                    "progress_source": "unknown",
                    "has_thumbnail": False,
                    "hash": "cancel-hash",
                },
            ],
            "RUNNING": [
                {
                    "machine": "InBat",
                    "name": "reprint_120x50.prt",
                    "reprint_needs_review": True,
                    "reprint_label": "In lại sau khi đã xong - chờ tín hiệu xong",
                    "has_thumbnail": True,
                }
            ],
            "REMOVED": [
                {
                    "machine": "InBat",
                    "name": "missing_800x310.tif",
                    "cancel_reason": "Xóa file xuất",
                    "has_thumbnail": False,
                    "hash": "abc",
                }
            ],
        })

        titles = [item["title"] for item in items]
        self.assertIn("DONE quá nhanh", titles)
        self.assertIn("Chưa rõ % hỏng", titles)
        self.assertIn("Cần xác nhận in lại", titles)
        self.assertIn("Thiếu ảnh preview", titles)

    def test_removed_source_delete_missing_preview_is_not_action_item(self):
        items = Dashboard.build_attention_items({
            "CANCELED": [],
            "REMOVED": [
                {
                    "machine": "InDecal",
                    "name": "xd4.tif",
                    "cancel_reason": "Xóa file xuất",
                    "cancel_type": "source_delete",
                    "has_thumbnail": False,
                    "hash": "abc",
                },
                {
                    "machine": "InDecal",
                    "name": "admin_deleted.tif",
                    "cancel_reason": "Quản trị xóa",
                    "cancel_type": "admin_delete",
                    "has_thumbnail": False,
                    "hash": "def",
                },
            ],
        })

        self.assertEqual(items, [])

    def test_stale_active_attention_is_not_duplicated_as_reprint(self):
        items = Dashboard.build_attention_items({
            "CANCELED": [
                {
                    "machine": "InDecal",
                    "name": "17~hh3_110x60.prn",
                    "cancel_reason": "Thiếu tín hiệu kết thúc.",
                    "stale_active": True,
                    "reprint_needs_review": True,
                    "reprint_label": "Cần xác nhận: thiếu tín hiệu kết thúc",
                    "has_thumbnail": True,
                },
            ],
        })

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Thiếu tín hiệu kết thúc")

if __name__ == "__main__":
    unittest.main()



