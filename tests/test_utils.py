import os
import tempfile
import unittest

from utils import (
    convert_smi_file_to_temp_srt,
    convert_smi_to_srt_text,
    convert_subtitle_to_utf8,
    find_adjacent_media_in_folder,
    find_matching_image,
    find_matching_subtitle,
    find_next_media_in_folder,
    find_previous_media_in_folder,
    format_time,
    is_supported_audio,
    is_supported_media,
    is_supported_video,
    list_media_files_in_folder,
    natural_sort_key,
    normalize_recent_files,
)


class UtilsTest(unittest.TestCase):
    def test_format_time_handles_minutes_and_hours(self):
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3661), "01:01:01")

    def test_format_time_handles_non_finite_values(self):
        self.assertEqual(format_time(float("inf")), "00:00")
        self.assertEqual(format_time(float("nan")), "00:00")

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

    def test_find_matching_image_same_basename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = os.path.join(temp_dir, "song.mp3")
            image = os.path.join(temp_dir, "song.jpg")
            open(audio, "w", encoding="utf-8").close()
            open(image, "w", encoding="utf-8").close()
            self.assertEqual(find_matching_image(audio), image)

    def test_find_matching_image_cover_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = os.path.join(temp_dir, "track.mp3")
            cover = os.path.join(temp_dir, "cover.jpg")
            open(audio, "w", encoding="utf-8").close()
            open(cover, "w", encoding="utf-8").close()
            self.assertEqual(find_matching_image(audio), cover)

    def test_find_matching_image_same_basename_over_cover(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = os.path.join(temp_dir, "track.mp3")
            same = os.path.join(temp_dir, "track.png")
            cover = os.path.join(temp_dir, "cover.jpg")
            for f in (audio, same, cover):
                open(f, "w", encoding="utf-8").close()
            # 동일 파일명이 cover보다 우선
            self.assertEqual(find_matching_image(audio), same)

    def test_find_matching_image_returns_none_when_no_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = os.path.join(temp_dir, "track.mp3")
            open(audio, "w", encoding="utf-8").close()
            self.assertIsNone(find_matching_image(audio))

    def test_convert_malformed_smi_to_srt_text(self):
        smi = "<SAMI><BODY><SYNC Start=8100>히사짱...<SYNC Start=9130>&nbsp;<SYNC Start=9660>당신<br>강렬해</BODY></SAMI>"
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("00:00:08,100 --> 00:00:09,130", srt)
        self.assertIn("히사짱...", srt)
        self.assertIn("00:00:09,660 --> 00:00:12,660", srt)
        self.assertIn("당신\n강렬해", srt)

    def test_convert_multilingual_smi_prioritises_korean(self):
        smi = (
            "<SAMI><BODY>\n"
            "<SYNC Start=1000>\n"
            "  <P Class=KRCC>안녕하세요\n"
            "  <P Class=ENCC>Hello\n"
            "<SYNC Start=4000>\n"
            "  <P Class=ENCC>Bye\n"
            "  <P Class=KRCC>안녕히 가세요\n"
            "</BODY></SAMI>"
        )
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("안녕하세요", srt)
        self.assertNotIn("Hello", srt)
        self.assertIn("안녕히 가세요", srt)
        self.assertNotIn("Bye", srt)

    def test_convert_multilingual_smi_falls_back_to_first_class(self):
        smi = (
            "<SAMI><BODY>\n"
            "<SYNC Start=1000>\n"
            "  <P Class=ENCC>Hello\n"
            "  <P Class=JPCC>Konnichiwa\n"
            "</BODY></SAMI>"
        )
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("Hello", srt)
        self.assertNotIn("Konnichiwa", srt)

    def test_convert_multilingual_smi_handles_extra_attributes_after_class(self):
        # Real-world SMI files sometimes have extra attributes after Class=..., e.g.
        # <P Class=KRCC Style=xyz>. The Korean-priority match must not require '>'
        # immediately after the class value, or it silently falls back to the
        # wrong (first) language track.
        smi = (
            "<SAMI><BODY>\n"
            "<SYNC Start=1000>\n"
            "  <P Class=KRCC Style=xyz>안녕하세요\n"
            "  <P Class=ENCC>Hello\n"
            "</BODY></SAMI>"
        )
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("안녕하세요", srt)
        self.assertNotIn("Hello", srt)

    def test_convert_multilingual_smi_supports_quotes(self):
        smi = (
            "<SAMI><BODY>\n"
            "<SYNC Start=1000>\n"
            "  <P Class=\"KRCC\">안녕하세요\n"
            "  <P Class='ENCC'>Hello\n"
            "</BODY></SAMI>"
        )
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("안녕하세요", srt)
        self.assertNotIn("Hello", srt)

    def test_convert_smi_handles_descending_timestamps(self):
        smi = (
            "<SYNC Start=5000>first"
            "<SYNC Start=1000>second"
            "<SYNC Start=2000>third"
        )
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("00:00:05,000 --> 00:00:08,000", srt)
        self.assertIn("00:00:01,000 --> 00:00:02,000", srt)
        self.assertIn("00:00:02,000 --> 00:00:05,000", srt)

    def test_convert_smi_supports_quoted_start_and_extra_attributes(self):
        smi = '<SAMI><BODY><SYNC Start="1000" id=first>안녕</BODY></SAMI>'
        srt = convert_smi_to_srt_text(smi)
        self.assertIn("00:00:01,000 --> 00:00:04,000", srt)
        self.assertIn("안녕", srt)

    def test_convert_cp949_subtitle_does_not_misread_it_as_utf16(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = os.path.join(temp_dir, "clip.srt")
            expected = "안녕"
            with open(subtitle, "wb") as subtitle_file:
                subtitle_file.write(expected.encode("cp949"))

            converted = convert_subtitle_to_utf8(subtitle)
            self.assertIsNotNone(converted)
            try:
                with open(converted, encoding="utf-8") as converted_file:
                    self.assertEqual(converted_file.read(), expected)
            finally:
                if converted and os.path.exists(converted):
                    os.remove(converted)

    def test_convert_cp949_smi_preserves_markup_and_korean_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = os.path.join(temp_dir, "clip.smi")
            with open(subtitle, "wb") as subtitle_file:
                subtitle_file.write("<SYNC Start=1000>안녕a".encode("cp949"))

            converted = convert_smi_file_to_temp_srt(subtitle)
            self.assertIsNotNone(converted)
            try:
                with open(converted, encoding="utf-8") as converted_file:
                    self.assertIn("안녕a", converted_file.read())
            finally:
                if converted and os.path.exists(converted):
                    os.remove(converted)

    def test_convert_utf16_subtitle_still_uses_its_bom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = os.path.join(temp_dir, "clip.srt")
            expected = "안녕"
            with open(subtitle, "wb") as subtitle_file:
                subtitle_file.write(expected.encode("utf-16"))

            converted = convert_subtitle_to_utf8(subtitle)
            self.assertIsNotNone(converted)
            try:
                with open(converted, encoding="utf-8") as converted_file:
                    self.assertEqual(converted_file.read(), expected)
            finally:
                if converted and os.path.exists(converted):
                    os.remove(converted)


class NextMediaTest(unittest.TestCase):
    def _make(self, temp_dir, *names):
        for name in names:
            open(os.path.join(temp_dir, name), "w", encoding="utf-8").close()

    def test_natural_sort_key_orders_numbers_numerically(self):
        names = ["track10.mp3", "track2.mp3", "track1.mp3"]
        self.assertEqual(sorted(names, key=natural_sort_key), ["track1.mp3", "track2.mp3", "track10.mp3"])

    def test_natural_sort_key_is_case_insensitive(self):
        names = ["b.mp3", "A.mp3"]
        self.assertEqual(sorted(names, key=natural_sort_key), ["A.mp3", "b.mp3"])

    def test_list_media_files_skips_non_media(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "a.mp4", "notes.txt", "b.mp3", "cover.jpg", "sub.srt")
            self.assertEqual(
                [os.path.basename(p) for p in list_media_files_in_folder(temp_dir)],
                ["a.mp4", "b.mp3"],
            )

    def test_find_next_returns_following_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "02.mp4", "03.mp4")
            nxt = find_next_media_in_folder(os.path.join(temp_dir, "02.mp4"))
            self.assertEqual(nxt, os.path.join(temp_dir, "03.mp4"))

    def test_find_next_mixes_audio_and_video_in_name_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "a.mp4", "b.mp3", "c.mkv")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "a.mp4")),
                os.path.join(temp_dir, "b.mp3"),
            )

    def test_find_next_uses_natural_order_not_lexicographic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "ep2.mp4", "ep10.mp4")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "ep2.mp4")),
                os.path.join(temp_dir, "ep10.mp4"),
            )

    def test_find_next_returns_none_on_last_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "02.mp4")
            self.assertIsNone(find_next_media_in_folder(os.path.join(temp_dir, "02.mp4")))

    def test_find_next_returns_none_for_only_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "solo.mp4")
            self.assertIsNone(find_next_media_in_folder(os.path.join(temp_dir, "solo.mp4")))

    def test_find_next_ignores_subdirectories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "a.mp4")
            os.mkdir(os.path.join(temp_dir, "b.mp4"))  # 미디어 확장자를 가진 폴더
            self._make(temp_dir, "c.mp4")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "a.mp4")),
                os.path.join(temp_dir, "c.mp4"),
            )

    def test_find_next_when_current_file_is_gone(self):
        # 재생 중 파일이 삭제/이름 변경된 경우에도 이름 순으로 그 다음 파일을 찾아야 함
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "03.mp4")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "02.mp4")),
                os.path.join(temp_dir, "03.mp4"),
            )

    def test_find_next_skips_appledouble_and_hidden_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "._02.mp4", ".hidden.mp4", "03.mp4")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "01.mp4")),
                os.path.join(temp_dir, "03.mp4"),
            )

    def test_find_next_returns_none_for_missing_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = os.path.join(temp_dir, "nope", "clip.mp4")
            self.assertIsNone(find_next_media_in_folder(missing))

    def test_find_next_is_case_insensitive_on_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "a.MP4", "b.Mp3")
            self.assertEqual(
                find_next_media_in_folder(os.path.join(temp_dir, "a.MP4")),
                os.path.join(temp_dir, "b.Mp3"),
            )


class PreviousMediaTest(unittest.TestCase):
    def _make(self, temp_dir, *names):
        for name in names:
            open(os.path.join(temp_dir, name), "w", encoding="utf-8").close()

    def test_find_previous_returns_preceding_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "02.mp4", "03.mp4")
            self.assertEqual(
                find_previous_media_in_folder(os.path.join(temp_dir, "02.mp4")),
                os.path.join(temp_dir, "01.mp4"),
            )

    def test_find_previous_returns_none_on_first_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "02.mp4")
            self.assertIsNone(find_previous_media_in_folder(os.path.join(temp_dir, "01.mp4")))

    def test_find_previous_uses_natural_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "ep2.mp4", "ep10.mp4")
            self.assertEqual(
                find_previous_media_in_folder(os.path.join(temp_dir, "ep10.mp4")),
                os.path.join(temp_dir, "ep2.mp4"),
            )

    def test_find_previous_when_current_file_is_gone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "03.mp4")
            self.assertEqual(
                find_previous_media_in_folder(os.path.join(temp_dir, "02.mp4")),
                os.path.join(temp_dir, "01.mp4"),
            )

    def test_adjacent_returns_both_neighbours(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "01.mp4", "02.mp3", "03.mkv")
            self.assertEqual(
                find_adjacent_media_in_folder(os.path.join(temp_dir, "02.mp3")),
                (os.path.join(temp_dir, "01.mp4"), os.path.join(temp_dir, "03.mkv")),
            )

    def test_adjacent_returns_none_pair_for_only_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "solo.mp4")
            self.assertEqual(
                find_adjacent_media_in_folder(os.path.join(temp_dir, "solo.mp4")),
                (None, None),
            )

    def test_adjacent_returns_none_pair_for_empty_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(
                find_adjacent_media_in_folder(os.path.join(temp_dir, "gone.mp4")),
                (None, None),
            )

    def test_walk_whole_folder_forward_then_backward(self):
        # 실제 앨범 폴더처럼 자막·커버·비미디어가 섞인 상태에서, 첫 파일부터
        # 끝까지 이동한 뒤 되돌아오면 모든 미디어를 정확히 한 번씩 지나야 함
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(
                temp_dir,
                "10 - Outro.mp3", "2 - Verse.mp3", "1 - Intro.mp3", "clip.mkv",
                "cover.jpg", "1 - Intro.srt", "notes.txt",
            )
            expected = ["1 - Intro.mp3", "2 - Verse.mp3", "10 - Outro.mp3", "clip.mkv"]

            visited = [expected[0]]
            current = os.path.join(temp_dir, expected[0])
            while True:
                nxt = find_next_media_in_folder(current)
                if nxt is None:
                    break
                visited.append(os.path.basename(nxt))
                current = nxt
                self.assertLessEqual(len(visited), 10, "무한 순환")
            self.assertEqual(visited, expected)

            backward = [os.path.basename(current)]
            while True:
                prev = find_previous_media_in_folder(current)
                if prev is None:
                    break
                backward.append(os.path.basename(prev))
                current = prev
                self.assertLessEqual(len(backward), 10, "무한 순환")
            self.assertEqual(backward, list(reversed(expected)))

    def test_adjacent_round_trip_is_symmetric(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._make(temp_dir, "a.mp4", "b.mp4", "c.mp4")
            middle = os.path.join(temp_dir, "b.mp4")
            nxt = find_next_media_in_folder(middle)
            self.assertEqual(find_previous_media_in_folder(nxt), middle)


if __name__ == "__main__":
    unittest.main()
