import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import server


class ServerReprintNoiseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_dir = server.DB_DIR
        self.old_thumb_dir = server.THUMB_DIR
        server.DB_DIR = self.temp_dir.name
        server.THUMB_DIR = os.path.join(self.temp_dir.name, "Thumbnails")
        os.makedirs(server.THUMB_DIR, exist_ok=True)
        server.init_all_databases()
        self.addCleanup(self.restore_globals)

    def restore_globals(self):
        server.DB_DIR = self.old_db_dir
        server.THUMB_DIR = self.old_thumb_dir

    def post_event(self, event_type, event_time, event_id, thumbnail_b64=None, path=None, machine="inbat", forced_base_id=None, machine_meta=None):
        payload = server.RequestData(
            machine=machine,
            path=path or r"D:\2026-07-10\New Folder\thanhnhan_450x60_bron_catdan2dau.prt",
            event_type=event_type,
            event_time=event_time,
            event_id=event_id,
            idempotency_key=event_id,
            thumbnail_b64=thumbnail_b64,
            forced_base_id=forced_base_id,
            machine_meta=machine_meta,
        )
        return asyncio.run(server.log_event(payload))

    def rows(self, machine="InBat"):
        conn = sqlite3.connect(os.path.join(self.temp_dir.name, f"{machine}.db"))
        conn.row_factory = sqlite3.Row
        try:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT file_hash, file_name, file_path, status, updated_time, run_count, history, machine_meta_json FROM files ORDER BY updated_time"
                )
            ]
        finally:
            conn.close()

    def test_indecal_rename_audit_is_stored_on_server(self):
        payload = server.RenameAuditPayload(
            machine="indecal",
            action="RENAME_FAIL_NO_META",
            prn_path=r"D:\2026-07-13\New Folder\12.prn",
            file_size=1234,
            error="no meta",
            event_time="2026-07-13 09:10:11",
        )

        result = server.receive_indecal_rename_audit(payload)

        self.assertEqual(result["status"], "ok")
        audit_db = os.path.join(self.temp_dir.name, "indecal_rename_audit.db")
        conn = sqlite3.connect(audit_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(row) for row in conn.execute("SELECT machine, action, prn_path, file_size, error, event_time FROM rename_audit")]
        finally:
            conn.close()
        self.assertEqual(rows, [{
            "machine": "InDecal",
            "action": "RENAME_FAIL_NO_META",
            "prn_path": r"D:\2026-07-13\New Folder\12.prn",
            "file_size": 1234,
            "error": "no meta",
            "event_time": "2026-07-13 09:10:11",
        }])

    def test_ping_stores_client_instance_details(self):
        payload = server.PingPayload(
            machine="indecal",
            version="V2.0.9_AUTO_UPDATE_IDLE",
            hostname="DECAL-PC",
            pid=4321,
            start_time="2026-07-13 16:30:00",
            instance_id="DECAL-PC-4321-abcd",
        )

        result = server.ping_client(payload)

        self.assertEqual(result["status"], "ok")
        conn = sqlite3.connect(os.path.join(self.temp_dir.name, "InDecal.db"))
        try:
            info = dict(conn.execute("SELECT key, value FROM app_info").fetchall())
        finally:
            conn.close()
        self.assertEqual(info["version"], "V2.0.9_AUTO_UPDATE_IDLE")
        self.assertEqual(info["hostname"], "DECAL-PC")
        self.assertEqual(info["pid"], "4321")
        self.assertEqual(info["start_time"], "2026-07-13 16:30:00")
        self.assertEqual(info["instance_id"], "DECAL-PC-4321-abcd")

    def test_printing_after_done_creates_reprint_row_waiting_for_second_done(self):
        self.post_event("PRINTING", "2026-07-10 15:26:40", "evt-print-1")
        self.post_event("DONE", "2026-07-10 15:27:57", "evt-done-1")
        self.post_event("PRINTING", "2026-07-10 15:29:33", "evt-print-reprint")

        rows = self.rows()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "DONE")
        self.assertEqual(rows[0]["run_count"], 1)
        self.assertEqual(rows[1]["status"], "PRINTING")
        reprint_history = json.loads(rows[1]["history"])
        self.assertEqual(reprint_history[0]["event"], "In lại sau khi đã xong - chờ tín hiệu xong")

    def test_second_done_after_reprint_marks_done_as_extra_run(self):
        self.post_event("PRINTING", "2026-07-10 15:26:40", "evt-print-1")
        self.post_event("DONE", "2026-07-10 15:27:57", "evt-done-1")
        self.post_event("PRINTING", "2026-07-10 15:29:33", "evt-print-reprint")
        self.post_event("DONE", "2026-07-10 15:35:10", "evt-done-2")

        rows = self.rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "DONE")
        self.assertEqual(rows[0]["run_count"], 2)
        self.assertIn("(x2)", rows[0]["file_name"])

    def test_same_logical_done_with_different_uuid_is_ignored(self):
        path = r"D:\2026-07-10\New Folder\thanhnhan_450x60_bron_catdan2dau.prt"

        self.post_event("DONE", "2026-07-10 15:27:57", "uuid-first", path=path)
        self.post_event("DONE", "2026-07-10 15:27:57", "uuid-replayed", path=path)

        rows = self.rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "DONE")
        self.assertEqual(rows[0]["run_count"], 1)

    def test_done_replayed_without_new_active_run_does_not_increment_run_count(self):
        path = r"D:\CNC\2026-07-13\xp_120x80mica.tap"

        self.post_event("CUTTING", "2026-07-13 15:11:19", "evt-cut", path=path, machine="cnc")
        self.post_event("DONE", "2026-07-13 15:23:33", "evt-done-history", path=path, machine="cnc")
        self.post_event("DONE", "2026-07-13 15:23:32", "evt-done-ncstudio", path=path, machine="cnc")

        rows = self.rows("CNC")
        history = json.loads(rows[0]["history"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "DONE")
        self.assertEqual(rows[0]["run_count"], 1)
        self.assertNotIn("(x2)", rows[0]["file_name"])
        self.assertEqual([item["status"] for item in history].count("DONE"), 1)

    def test_storage_day_uses_event_time_before_server_today(self):
        day = server.storage_day_for_event(
            "2026-07-10 15:27:57",
            r"D:\2026-07-11\New Folder\thanhnhan_450x60_bron_catdan2dau.prt",
        )

        self.assertEqual(day, "2026-07-10")

    def test_delete_keeps_thumbnail_when_hash_changes_to_deleted_hash(self):
        tiny_jpg_b64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2w=="
        path = r"D:\2026-07-10\ntdq_800x310.tif"

        self.post_event("EXPORT", "2026-07-10 08:00:00", "evt-export-thumb", tiny_jpg_b64, path)
        active_rows = self.rows()
        self.assertEqual(active_rows[0]["status"], "EXPORTED")
        self.assertTrue(os.path.exists(os.path.join(server.THUMB_DIR, active_rows[0]["file_hash"] + ".jpg")))

        self.post_event("DELETE", "2026-07-10 08:18:57", "evt-delete-thumb", None, path)
        deleted_rows = self.rows()

        self.assertEqual(deleted_rows[0]["status"], "DELETED")
        self.assertTrue(os.path.exists(os.path.join(server.THUMB_DIR, deleted_rows[0]["file_hash"] + ".jpg")))
    def test_short_indecal_runtime_path_does_not_overwrite_full_rip_path(self):
        full_path = r"D:\2026-07-11\New Folder\13~hhhh_decal_62x62.prn"
        short_path = "13~hhhh_decal_62x62.prn"

        self.post_event("RIP", "2026-07-11 16:14:55", "evt-rip-path", path=full_path, machine="indecal")
        self.post_event("PRINTING", "2026-07-11 16:15:07", "evt-print-short-path", path=short_path, machine="indecal")

        rows = self.rows("InDecal")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PRINTING")
        self.assertEqual(rows[0]["file_path"], full_path)

    def test_indecal_forced_base_id_merges_runtime_log_with_rip_record(self):
        rip_path = r"D:\2026-07-11\New Folder\19~huong_121x240.prn"
        runtime_path = "19~unexpected_runtime_name.prn"

        self.post_event("RIP", "2026-07-11 16:56:53", "evt-rip-forced", path=rip_path, machine="indecal")
        self.post_event(
            "PRINTING",
            "2026-07-11 17:10:56",
            "evt-print-forced",
            path=runtime_path,
            machine="indecal",
            forced_base_id="huong_121x240",
        )

        rows = self.rows("InDecal")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PRINTING")
        self.assertEqual(rows[0]["file_path"], rip_path)

    def test_machine_meta_is_stored_with_file_row(self):
        self.post_event(
            "EXPORT",
            "2026-07-13 09:57:00",
            "evt-cnc-meta",
            path=r"D:\CNC\2026-07-13\f8_120x67.tap",
            machine="cnc",
            machine_meta={"line_count": 32195, "x_max": 1198.496, "width_mm": 1199.495},
        )

        rows = self.rows("CNC")
        stored = json.loads(rows[0]["machine_meta_json"])

        self.assertEqual(stored["line_count"], 32195)
        self.assertAlmostEqual(stored["width_mm"], 1199.495)

    def test_duplicate_running_status_can_refresh_machine_meta(self):
        path = r"D:\2026-07-13\New Folder\12~hl_120x240.prn"

        self.post_event(
            "PRINTING",
            "2026-07-13 14:40:55",
            "evt-print-start",
            path=path,
            machine="indecal",
            machine_meta={"current_pass": 1, "total_pass": 429, "progress_percent": 0.2},
        )
        self.post_event(
            "PRINTING",
            "2026-07-13 14:44:09",
            "evt-print-progress",
            path=path,
            machine="indecal",
            machine_meta={"current_pass": 136, "total_pass": 429, "progress_percent": 31.7},
        )

        rows = self.rows("InDecal")
        stored = json.loads(rows[0]["machine_meta_json"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PRINTING")
        self.assertEqual(stored["current_pass"], 136)
        self.assertAlmostEqual(stored["progress_percent"], 31.7)

    def test_running_delete_uses_stored_progress_percent(self):
        path = r"D:\2026-07-13\New Folder\14~xpppp1_122x164.prn"

        self.post_event(
            "PRINTING",
            "2026-07-13 15:38:03",
            "evt-print-progress-delete",
            path=path,
            machine="indecal",
            machine_meta={"current_pass": 192, "total_pass": 295, "progress_percent": 65.08},
        )
        self.post_event("DELETE", "2026-07-13 15:43:55", "evt-delete-progress", path=path, machine="indecal")

        rows = self.rows("InDecal")
        history = json.loads(rows[0]["history"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "DELETED")
        self.assertEqual(history[-1]["cancel_type"], "production_cancel")
        self.assertAlmostEqual(history[-1]["progress_percent"], 65.08)

    def test_cnc_pause_keeps_cutting_row_instead_of_deleted(self):
        path = r"D:\CNC\2026-07-14\nsss_120x120.tap"
        self.post_event("CUTTING", "2026-07-14 11:09:00", "evt-cnc-cut", path=path, machine="cnc")
        self.post_event("PAUSE", "2026-07-14 11:09:04", "evt-cnc-pause", path=path, machine="cnc")

        rows = self.rows("CNC")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "CUTTING")
        history = json.loads(rows[0]["history"])
        self.assertEqual(history[-1]["status"], "PAUSED")
        self.assertEqual(history[-1]["event"], "PAUSE")

    def test_cnc_cutting_after_pause_marks_resume(self):
        path = r"D:\CNC\2026-07-14\nsss_120x120.tap"
        self.post_event("CUTTING", "2026-07-14 11:09:00", "evt-cnc-cut", path=path, machine="cnc")
        self.post_event("PAUSE", "2026-07-14 11:09:04", "evt-cnc-pause", path=path, machine="cnc")
        self.post_event("CUTTING", "2026-07-14 11:09:14", "evt-cnc-resume", path=path, machine="cnc")

        rows = self.rows("CNC")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "CUTTING")
        history = json.loads(rows[0]["history"])
        self.assertEqual(history[-1]["status"], "CUTTING")
        self.assertTrue(history[-1]["resume_after_pause"])

    def test_rollover_marks_previous_day_row_and_keeps_new_day_row_separate(self):
        old_path = r"D:\CNC\2026-07-14\loi_f8_120x29.tap"
        new_path = r"D:\CNC\2026-07-15\loi_f8_120x29_Ngay14.tap"

        self.post_event("CUTTING", "2026-07-14 16:59:13", "evt-cnc-cut-old-day", path=old_path, machine="cnc")
        self.post_event(
            "ROLLOVER",
            "2026-07-15 07:00:01",
            "evt-cnc-rollover",
            path=old_path,
            machine="cnc",
            machine_meta={
                "rollover_source_path": old_path,
                "rollover_source_name": "loi_f8_120x29.tap",
                "rollover_target_path": new_path,
                "rollover_target_name": "loi_f8_120x29_Ngay14.tap",
                "rollover_reason": "new_day",
            },
        )
        self.post_event("WRONG_DAY", "2026-07-15 07:00:02", "evt-cnc-new-day", path=new_path, machine="cnc")

        rows = self.rows("CNC")
        rows_by_path = {row["file_path"]: row for row in rows}
        old_history = json.loads(rows_by_path[old_path]["history"])
        old_meta = json.loads(rows_by_path[old_path]["machine_meta_json"])

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows_by_path[old_path]["status"], "ROLLED_OVER")
        self.assertEqual(rows_by_path[new_path]["status"], "WRONG_DAY")
        self.assertEqual(old_history[-1]["status"], "ROLLED_OVER")
        self.assertEqual(old_history[-1]["event"], "Chuyển qua ngày mới")
        self.assertEqual(old_history[-1]["new_path"], new_path)
        self.assertEqual(old_meta["rollover_target_name"], "loi_f8_120x29_Ngay14.tap")

    def test_indecal_printing_after_recent_running_delete_revives_same_row(self):
        path = r"D:\2026-07-13\New Folder\14~xpppp1_122x164.prn"

        self.post_event(
            "PRINTING",
            "2026-07-13 15:38:03",
            "evt-print-before-false-delete",
            path=path,
            machine="indecal",
            machine_meta={"current_pass": 15, "total_pass": 295, "progress_percent": 5.08},
        )
        self.post_event("DELETE", "2026-07-13 15:38:33", "evt-false-delete", path=path, machine="indecal")
        self.post_event(
            "PRINTING",
            "2026-07-13 15:38:38",
            "evt-print-after-false-delete",
            path="14~xpppp1_122x164.prn",
            machine="indecal",
            machine_meta={"current_pass": 20, "total_pass": 295, "progress_percent": 6.78},
        )

        rows = self.rows("InDecal")
        history = json.loads(rows[0]["history"])
        stored = json.loads(rows[0]["machine_meta_json"])

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "PRINTING")
        self.assertEqual(rows[0]["file_path"], path)
        self.assertEqual([item["status"] for item in history], ["PRINTING", "DELETED", "PRINTING"])
        self.assertTrue(history[-1]["resume_after_delete"])
        self.assertEqual(stored["current_pass"], 20)
        self.assertAlmostEqual(stored["progress_percent"], 6.78)


if __name__ == "__main__":
    unittest.main()
