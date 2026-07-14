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
            "Tiến độ: 92%",
        )

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
                status='DONE',
                updated_time='2026-07-13 09:00:00',
                history='[{"status":"DONE","time":"2026-07-13 09:00:00","event":"DONE"}]'
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

    def test_card_preview_has_inline_admin_status_actions(self):
        html = Dashboard.HTML_TEMPLATE

        self.assertIn('id="cardPreviewActions"', html)
        self.assertIn("previewForceUpdate('DONE')", html)
        self.assertIn("previewForceUpdate('DELETED')", html)
        self.assertIn("previewForceUpdate('EXPORTED')", html)
        self.assertIn("data-hash=", html)
        self.assertIn("hash: file.hash", html)
        self.assertIn("syncPreviewAdminActions()", html)
        self.assertIn("has-admin", html)
        self.assertNotIn("has-file", html)
        self.assertNotIn("card.addEventListener('dblclick'", html)

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
        self.assertIn("Hàng chờ", html)
        self.assertIn("In xong", html)
        self.assertIn("Lỗi thật", html)
        self.assertIn("Xóa / hủy", html)
        self.assertIn('class="column col-export queue-column"', html)
        self.assertIn('id="queue-list"', html)
        self.assertNotIn('id="run-compact-list"', html)
        self.assertIn('class="column col-cancel problem-column"', html)
        self.assertIn('class="problem-stack"', html)
        self.assertIn('id="true-problem-list"', html)
        self.assertIn('id="removed-problem-list"', html)
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
        self.assertIn('function selectSystemItem(index)', html)
        self.assertIn('function selectSystemLog(index)', html)
        self.assertIn('window.systemItems = systemItems;', html)
        self.assertIn('window.selectedSystemName', html)
        self.assertIn('window.selectedSystemIndex', html)
        self.assertIn('id="systemViewerBody"', html)
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
        self.assertIn("const offset = 4;", html)
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
        self.assertIn('btn.innerText = "⚙"', html)
        self.assertNotIn('btn.innerText = "Admin"', html)
        self.assertIn("function positionCardPreview(card)", html)
        self.assertIn("window.innerHeight - previewHeight - margin", html)
        self.assertIn("preview.style.maxHeight = maxPreviewHeight + 'px'", html)
        self.assertIn("grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))", html)
        self.assertIn("list.innerHTML = items.map(renderAttentionItem).join('')", html)

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



