import os
import tempfile
import unittest

from utils import convert_smi_to_srt_text, find_matching_subtitle, format_time, is_supported_audio, is_supported_media, is_supported_video, normalize_recent_files


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

    def test_find_matching_subtitle_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "Clip.mp4")
            subtitle = os.path.join(temp_dir, "clip.SRT")
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

    def test_is_supported_audio_recognises_wav_and_common_formats(self):
        self.assertTrue(is_supported_audio("track.WAV"))
        self.assertTrue(is_supported_audio("song.mp3"))
        self.assertTrue(is_supported_audio("lossless.FLAC"))
        self.assertFalse(is_supported_audio("movie.mp4"))
        self.assertFalse(is_supported_audio("notes.txt"))

    def test_is_supported_media_accepts_both_video_and_audio(self):
        self.assertTrue(is_supported_media("clip.mkv"))
        self.assertTrue(is_supported_media("track.wav"))
        self.assertFalse(is_supported_media("readme.txt"))

    def test_find_matching_subtitle_prefers_srt_over_vtt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "clip.mp4")
            srt = os.path.join(temp_dir, "clip.srt")
            vtt = os.path.join(temp_dir, "clip.vtt")
            for f in (video, srt, vtt):
                open(f, "w", encoding="utf-8").close()
            # SUBTITLE_EXTENSIONS 순서(.srt 우선)대로 반환해야 함
            self.assertEqual(find_matching_subtitle(video), srt)

    def test_convert_malformed_smi_to_srt_text(self):
        smi = "<SAMI><BODY><SYNC Start=8100>히사짱...<SYNC Start=9130>&nbsp;<SYNC Start=9660>당신<br>강렬해</BODY></SAMI>"
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("00:00:08,100 --> 00:00:09,130", srt)
        self.assertIn("히사짱...", srt)
        self.assertIn("00:00:09,660 --> 00:00:12,660", srt)
        self.assertIn("당신\n강렬해", srt)


if __name__ == "__main__":
    unittest.main()
