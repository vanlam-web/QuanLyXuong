import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_ROOT = os.path.join(PROJECT_ROOT, "app")
for path in (PROJECT_ROOT, APP_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from PIL import Image
from io import BytesIO

from tap_preview import (
    analyze_tap_file,
    estimate_tap_path_progress,
    cnc_unc_candidates,
    parse_tap_segments,
    parse_tap_segments_with_lines,
    render_tap_preview_bytes,
    render_tap_progress_preview_bytes,
)
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

    def test_render_preview_uses_tap_aspect_ratio(self):
        path = self.write_tap("G0X0Y0\nG1Z0\nG1X1200Y0\nY500\nX0\nY0\n")
        try:
            data = render_tap_preview_bytes(path)
        finally:
            os.unlink(path)

        image = Image.open(BytesIO(data))
        self.assertGreater(image.width, image.height)
        self.assertGreater(image.width / image.height, 1.7)

    def test_parse_tap_segments_with_lines_tracks_source_line(self):
        path = self.write_tap("G0Z5\nG0X0Y0\nG1Z0\nG1X10Y0\nG1X10Y10\n")
        try:
            segments = parse_tap_segments_with_lines(path)
        finally:
            os.unlink(path)

        self.assertEqual([item["line_no"] for item in segments], [4, 5])

    def test_render_tap_progress_preview_marks_cut_and_uncut_segments(self):
        path = self.write_tap(
            "G0Z5\n"
            "G0X0Y0\n"
            "G1Z0\n"
            "G1X100Y0\n"
            "G1X100Y100\n"
            "G1X0Y100\n"
            "G1X0Y0\n"
        )
        try:
            data = render_tap_progress_preview_bytes(path, current_line=5, size=500)
        finally:
            os.unlink(path)

        image = Image.open(BytesIO(data)).convert("RGB")
        pixels = list(image.getdata())
        red_pixels = sum(1 for r, g, b in pixels if r > 140 and g < 100 and b < 100)
        green_pixels = sum(1 for r, g, b in pixels if g > 120 and r < 120 and b < 140)
        dark_pixels = sum(1 for r, g, b in pixels if r < 90 and g < 90 and b < 90)

        self.assertEqual(red_pixels, 0)
        self.assertGreater(green_pixels, 20)
        self.assertGreater(dark_pixels, 20)

    def test_render_tap_progress_preview_keeps_uncut_segments_after_20k_cap(self):
        lines = ["G0Z5", "G0X0Y0", "G1Z0"]
        for index in range(30000):
            lines.append(f"G1X{index % 2}Y{index}")
        path = self.write_tap("\n".join(lines) + "\n")
        try:
            data = render_tap_progress_preview_bytes(path, current_line=25003, size=700)
        finally:
            os.unlink(path)

        image = Image.open(BytesIO(data)).convert("RGB")
        pixels = list(image.getdata())
        green_pixels = sum(1 for r, g, b in pixels if g > 120 and r < 120 and b < 140)
        dark_pixels = sum(1 for r, g, b in pixels if r < 90 and g < 90 and b < 90)

        self.assertGreater(green_pixels, 20)
        self.assertGreater(dark_pixels, 20)

    def test_default_tap_preview_parser_reads_more_than_20k_segments(self):
        lines = ["G0Z5", "G0X0Y0", "G1Z0"]
        for index in range(1, 30001):
            lines.append(f"G1X{index % 2}Y{index}")
        path = self.write_tap("\n".join(lines) + "\n")
        try:
            segments = parse_tap_segments(path)
        finally:
            os.unlink(path)

        self.assertEqual(len(segments), 30000)

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

    def test_estimate_tap_path_progress_uses_cut_distance_not_line_count(self):
        path = self.write_tap(
            "G0Z5\n"
            "G0X0Y0\n"
            "G1Z0\n"
            "G1X100Y0\n"
            "G1X1000Y0\n"
        )
        try:
            progress = estimate_tap_path_progress(path, current_line=4)
        finally:
            os.unlink(path)

        self.assertEqual(progress["current_path_length"], 100.0)
        self.assertEqual(progress["total_path_length"], 1000.0)
        self.assertAlmostEqual(progress["progress_percent"], 10.0, places=2)
        self.assertEqual(progress["progress_source"], "cnc_tap_path")

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

    def test_parse_cnc_log_treats_interruption_as_pause_not_delete(self):
        lines = [
            "M\t2026-07-14 11:09:00\tInitiate a machining task: 'D:\\CNC\\2026-07-14\\nsss_120x120.tap', from beginning to end",
            "M\t2026-07-14 11:09:04\t文件'D:\\CNC\\2026-07-14\\nsss_120x120.tap'中断终止",
            "M\t2026-07-14 11:09:14\tInitiate a machining task: 'D:\\CNC\\2026-07-14\\nsss_120x120.tap', from beginning to end",
        ]

        events = parse_cnc_log_events(lines)

        self.assertEqual([event["event_type"] for event in events], ["CUTTING", "PAUSE", "CUTTING"])
        self.assertEqual(events[1]["path"], r"D:\CNC\2026-07-14\nsss_120x120.tap")

    def test_parse_cnc_dyn_progress_extracts_current_line_percent(self):
        from cnc_log_parser import parse_cnc_dyn_progress

        progress = parse_cnc_dyn_progress(b"\x00#m\x03\x00L12732\x00", 31557)

        self.assertEqual(progress["current_line"], 12732)
        self.assertEqual(progress["line_count"], 31557)
        self.assertAlmostEqual(progress["progress_percent"], 40.35, places=2)


    def test_cnc_unc_candidates_include_new_folder_for_existing_unc_day_path(self):
        candidates = cnc_unc_candidates(r"\\CNC\CNC\CNC\2026-07-14\lh333_f5.tap")

        self.assertIn(r"\\CNC\CNC\CNC\2026-07-14\lh333_f5.tap", candidates)
        self.assertIn(r"\\CNC\CNC\CNC\2026-07-14\New Folder\lh333_f5.tap", candidates)

if __name__ == "__main__":
    unittest.main()


