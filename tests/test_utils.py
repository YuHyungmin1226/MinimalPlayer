import os
import tempfile
import unittest

from utils import convert_smi_to_srt_text, find_matching_subtitle, format_time, is_supported_video, normalize_recent_files


class UtilsTest(unittest.TestCase):
    def test_format_time_handles_minutes_and_hours(self):
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3661), "01:01:01")

    def test_is_supported_video_is_case_insensitive(self):
        self.assertTrue(is_supported_video("movie.MP4"))
        self.assertFalse(is_supported_video("notes.txt"))

    def test_find_matching_subtitle_prefers_supported_same_basename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "clip.mp4")
            subtitle = os.path.join(temp_dir, "clip.srt")
            open(video, "w", encoding="utf-8").close()
            open(subtitle, "w", encoding="utf-8").close()
            self.assertEqual(find_matching_subtitle(video), subtitle)

    def test_normalize_recent_files_deduplicates_existing_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = os.path.join(temp_dir, "first.mp4")
            second = os.path.join(temp_dir, "second.mp4")
            open(first, "w", encoding="utf-8").close()
            open(second, "w", encoding="utf-8").close()
            self.assertEqual(normalize_recent_files([first, second, first], second, 2), [second, first])

    def test_convert_malformed_smi_to_srt_text(self):
        smi = "<SAMI><BODY><SYNC Start=8100>히사짱...<SYNC Start=9130>&nbsp;<SYNC Start=9660>당신<br>강렬해</BODY></SAMI>"
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("00:00:08,100 --> 00:00:09,130", srt)
        self.assertIn("히사짱...", srt)
        self.assertIn("00:00:09,660 --> 00:00:12,660", srt)
        self.assertIn("당신\n강렬해", srt)


if __name__ == "__main__":
    unittest.main()
