import os
import json
import sqlite3
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

import bridge_qcvl


class BridgeQcvlTests(unittest.TestCase):
    def test_parse_filename_extracts_dimensions_and_quantity(self):
        parsed = bridge_qcvl.parse_filename("KH000001_DECAL-PP_120x50_x2.prn")

        self.assertEqual(parsed["customer_code"], "KH000001")
        self.assertEqual(parsed["width_m"], 1.2)
        self.assertEqual(parsed["height_m"], 0.5)
        self.assertEqual(parsed["quantity"], 2)

    def test_parse_filename_extracts_sl_quantity(self):
        parsed = bridge_qcvl.parse_filename("KH000001_DECAL-PP_120x50_SL5.prn")

        self.assertEqual(parsed["quantity"], 5)

    def test_parse_filename_handles_indecal_prefix(self):
        parsed = bridge_qcvl.parse_filename("23~loi_120x184.prn")

        self.assertEqual(parsed["customer_code"], "loi")
        self.assertEqual(parsed["width_m"], 1.2)
        self.assertEqual(parsed["height_m"], 1.84)

    def test_parse_filename_pending_when_dimension_missing(self):
        parsed = bridge_qcvl.parse_filename("TTT_NHO_MUI1,5.tap")

        self.assertEqual(parsed["customer_code"], "TTT")
        self.assertIsNone(parsed["width_m"])
        self.assertIsNone(parsed["height_m"])
        self.assertEqual(parsed["quantity"], 1)

    def test_make_payload_maps_machine_and_status(self):
        row = {
            "file_hash": "hash-1",
            "file_name": "KH000001_DECAL-PP_120x50_x2.prn",
            "file_path": r"D:\Jobs\KH000001_DECAL-PP_120x50_x2.prn",
            "machine": "InDecal",
            "job_type": "EXPORT",
            "status": "DONE",
            "created_time": "2026-07-09 10:00:00",
            "updated_time": "2026-07-09 10:05:00",
            "run_count": 1,
            "history": "[]",
        }

        payload = bridge_qcvl.make_payload("InDecal", row)

        self.assertEqual(payload["machine"]["code"], "INDECAL")
        self.assertEqual(payload["event_type"], "DONE")
        self.assertEqual(payload["parse_status"], "ok")
        self.assertEqual(payload["parsed"]["quantity"], 2)
        self.assertEqual(len(payload["legacy_event_hash"]), 64)

    def test_make_payload_prefers_rip_header_dimensions_over_filename(self):
        row = {
            "file_hash": "hash-rip",
            "file_name": "yte_600x240.prt",
            "file_path": r"D:\Jobs\yte_600x240.prt",
            "machine": "InBat",
            "job_type": "PRINT",
            "status": "DONE",
            "created_time": "2026-07-14 16:00:00",
            "updated_time": "2026-07-14 16:30:00",
            "run_count": 1,
            "history": "[]",
            "machine_meta_json": json.dumps(
                {
                    "source_kind": "rip_file_header",
                    "width_cm": 240.05,
                    "height_cm": 600.02,
                    "area_m2": 14.404,
                    "metadata_source": r"\\InBat\D\2026-07-14\New Folder\yte_600x240.prt",
                }
            ),
        }

        payload = bridge_qcvl.make_payload("InBat", row)

        self.assertEqual(payload["parse_status"], "ok")
        self.assertEqual(payload["parsed"]["width_m"], 2.4005)
        self.assertEqual(payload["parsed"]["height_m"], 6.0002)
        self.assertEqual(payload["parsed"]["area_m2"], 14.404)
        self.assertEqual(payload["parsed"]["dimension_source"], "rip_file_header")

    def test_payload_shape_matches_schema_required_fields(self):
        schema_path = Path(PROJECT_ROOT) / "docs" / "production-event.schema.json"
        with open(schema_path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)

        row = {
            "file_hash": "hash-2",
            "file_name": "KH000002_140x230.prt",
            "file_path": r"D:\Jobs\KH000002_140x230.prt",
            "machine": "InBat",
            "job_type": "PRINT",
            "status": "DONE",
            "created_time": "2026-07-09 11:00:00",
            "updated_time": "2026-07-09 11:05:00",
            "run_count": 1,
            "history": "[]",
        }

        payload = bridge_qcvl.make_payload("InBat", row)

        for field in schema["required"]:
            self.assertIn(field, payload)
        self.assertLessEqual(set(payload.keys()), set(schema["properties"].keys()))

    def test_run_once_dump_jsonl_does_not_save_checkpoint_when_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            db_path = data_dir / "InBat.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    create table files (
                        file_hash text,
                        file_name text,
                        file_path text,
                        machine text,
                        job_type text,
                        status text,
                        created_time text,
                        updated_time text,
                        run_count integer,
                        history text
                    )
                    """
                )
                conn.execute(
                    """
                    insert into files values (
                        'hash-3',
                        'KH000003_120x50_x2.prn',
                        'D:\\Jobs\\KH000003_120x50_x2.prn',
                        'InBat',
                        'PRINT',
                        'DONE',
                        '2026-07-09 12:00:00',
                        '2026-07-09 12:05:00',
                        1,
                        '[]'
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            state_file = Path(temp_dir) / "state.json"
            dump_file = Path(temp_dir) / "events.jsonl"
            log_file = Path(temp_dir) / "bridge.log"
            args = Namespace(
                data_dir=str(data_dir),
                state_file=str(state_file),
                log_file=str(log_file),
                api_base_url="",
                api_token="",
                since_minutes=60 * 24 * 365,
                limit=10,
                timeout=1,
                dry_run=True,
                dump_jsonl=str(dump_file),
                save_checkpoint=False,
            )

            failed = bridge_qcvl.run_once(args)

            self.assertEqual(failed, 0)
            payloads = [json.loads(line) for line in dump_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["raw_file_name"], "KH000003_120x50_x2.prn")
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["processed"], {})

    def test_run_once_includes_machine_meta_json_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            db_path = data_dir / "InBat.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    create table files (
                        file_hash text,
                        file_name text,
                        file_path text,
                        machine text,
                        job_type text,
                        status text,
                        created_time text,
                        updated_time text,
                        run_count integer,
                        history text,
                        machine_meta_json text
                    )
                    """
                )
                conn.execute(
                    """
                    insert into files values (
                        'hash-4',
                        'yte_600x240.prt',
                        'D:\\Jobs\\yte_600x240.prt',
                        'InBat',
                        'PRINT',
                        'DONE',
                        '2026-07-14 16:00:00',
                        '2026-07-14 16:30:00',
                        1,
                        '[]',
                        ?
                    )
                    """,
                    (
                        json.dumps(
                            {
                                "source_kind": "rip_file_header",
                                "width_cm": 240.05,
                                "height_cm": 600.02,
                                "area_m2": 14.404,
                            }
                        ),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            state_file = Path(temp_dir) / "state.json"
            dump_file = Path(temp_dir) / "events.jsonl"
            log_file = Path(temp_dir) / "bridge.log"
            args = Namespace(
                data_dir=str(data_dir),
                state_file=str(state_file),
                log_file=str(log_file),
                api_base_url="",
                api_token="",
                since_minutes=60 * 24 * 365,
                limit=10,
                timeout=1,
                dry_run=True,
                dump_jsonl=str(dump_file),
                save_checkpoint=False,
            )

            failed = bridge_qcvl.run_once(args)

            self.assertEqual(failed, 0)
            payloads = [json.loads(line) for line in dump_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(payloads[0]["parsed"]["width_m"], 2.4005)
            self.assertEqual(payloads[0]["parsed"]["height_m"], 6.0002)
            self.assertEqual(payloads[0]["parsed"]["dimension_source"], "rip_file_header")


if __name__ == "__main__":
    unittest.main()


