import os
import sys
import tempfile
import unittest
from unittest import mock

import mpv_setup
from constants import MPV_DLL_NAME


class MpvSetupTest(unittest.TestCase):
    def setUp(self):
        self._old_meipass = getattr(sys, "_MEIPASS", None)
        self._had_meipass = hasattr(sys, "_MEIPASS")
        mpv_setup._DLL_DIRECTORY_HANDLES.clear()

    def tearDown(self):
        if self._had_meipass:
            setattr(sys, "_MEIPASS", self._old_meipass)
        elif hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        mpv_setup._DLL_DIRECTORY_HANDLES.clear()

    @unittest.skipUnless(os.name == "nt", "Windows DLL loader behavior")
    def test_prepare_mpv_library_keeps_bundled_dll_directory_handle_alive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, MPV_DLL_NAME), "wb").close()
            setattr(sys, "_MEIPASS", temp_dir)
            handle = object()

            with mock.patch.dict(os.environ, {"PATH": "original"}, clear=False), \
                    mock.patch.object(mpv_setup.os, "add_dll_directory", return_value=handle) as add_dll_dir, \
                    mock.patch.object(mpv_setup, "check_and_download_mpv", side_effect=AssertionError("unexpected download")):
                mpv_setup.prepare_mpv_library()
                self.assertTrue(os.environ["PATH"].startswith(temp_dir + os.pathsep))

            add_dll_dir.assert_called_once_with(temp_dir)
            self.assertIn(handle, mpv_setup._DLL_DIRECTORY_HANDLES)


if __name__ == "__main__":
    unittest.main()
