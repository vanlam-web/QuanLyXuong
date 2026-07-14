import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from tap_preview import analyze_tap_file, parse_tap_segments, render_tap_preview_bytes
from cnc_log_parser import parse_cnc_log_events


class TapPreviewTests(unittest.TestCase):
    def write_tap(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".tap", delete=False, encoding="utf-8")
        try:
            handle.write(text)
            return handle.name
        finally:
            handle.close()

    def test_parse_compact_gcode_without_spaces(self):
        path = self.write_tap(
            "G0Z15.000\n"
            "G0X0.000Y0.000\n"
            "G1Z0.000F780.0\n"
            "G1X10.000Y0.000F2520.0\n"
            "X10.000Y20.000\n"
            "G0Z15.000\n"
        )
        try:
            segments = parse_tap_segments(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], ((0.0, 0.0), (10.0, 0.0)))

    def test_render_preview_returns_jpeg_bytes(self):
        path = self.write_tap("G0X0Y0\nG1Z0\nG1X20Y0\nY20\nX0\nY0\n")
        try:
            data = render_tap_preview_bytes(path)
        finally:
            os.unlink(path)

        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertGreater(len(data), 1000)

    def test_analyze_tap_file_returns_bounds_line_count_and_feeds(self):
        path = self.write_tap(
            "T1M6\n"
            "G0Z20.000\n"
            "G0X0.000Y0.000S15000M3\n"
            "G1Z0.000F780.0\n"
            "G1X1200.000Y0.000F2520.0\n"
            "Y670.000\n"
            "G0Z20.000\n"
            "M30\n"
        )
        try:
            meta = analyze_tap_file(path)
        finally:
            os.unlink(path)

        self.assertEqual(meta["line_count"], 8)
        self.assertEqual(meta["x_min"], 0.0)
        self.assertEqual(meta["x_max"], 1200.0)
        self.assertEqual(meta["y_max"], 670.0)
        self.assertEqual(meta["feed_min"], 780.0)
        self.assertEqual(meta["feed_max"], 2520.0)

    def test_parse_cnc_log_detects_cutting_done_and_advanced_progress(self):
        lines = [
            "M\t2026-07-13 13:50:32\tInitiate a machining task: 'D:\\CNC\\2026-07-13\\XXD_MICATRONG_Ngay11_Ngay12.tap', from beginning to end",
            "M\t2026-07-13 14:20:00\t文件'D:\\CNC\\2026-07-13\\XXD_MICATRONG_Ngay11_Ngay12.tap'正常完毕",
            "M\t2026-07-11 15:43:31\tInitiate a machining task (Advanced): 'D:\\CNC\\Luu\\5p ngang chuan dut vip1.tap', from <first line> to L194",
        ]

        events = parse_cnc_log_events(lines, {"5p ngang chuan dut vip1.tap": 195})

        self.assertEqual(events[0]["event_type"], "CUTTING")
        self.assertEqual(events[0]["event_time"], "2026-07-13 13:50:32")
        self.assertEqual(events[1]["event_type"], "DONE")
        self.assertEqual(events[1]["path"], r"D:\CNC\2026-07-13\XXD_MICATRONG_Ngay11_Ngay12.tap")
        self.assertEqual(events[2]["event_type"], "CUTTING")
        self.assertAlmostEqual(events[2]["machine_meta"]["progress_percent"], 99.5, places=1)

    def test_parse_cnc_log_ignores_simulation_done_before_real_machining(self):
        lines = [
            "M\t2026-07-13 14:28:29\tInitiate a simulation: 'D:\\CNC\\2026-07-13\\XXXD.tap', from beginning to end",
            "M\t2026-07-13 14:28:32\t文件'D:\\CNC\\2026-07-13\\XXXD.tap'正常完毕",
            "M\t2026-07-13 14:31:20\tInitiate a machining task: 'D:\\CNC\\2026-07-13\\XXXD.tap', from beginning to end",
        ]

        events = parse_cnc_log_events(lines)

        self.assertEqual([event["event_type"] for event in events], ["CUTTING"])


if __name__ == "__main__":
    unittest.main()


