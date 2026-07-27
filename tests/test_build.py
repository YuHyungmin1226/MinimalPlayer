import hashlib
import os
import tempfile
import unittest
from unittest import mock

import build


class BuildTest(unittest.TestCase):
    def test_verify_mpv_dll_rejects_hash_mismatch(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"not the expected dll")
            temp_path = temp_file.name
        try:
            self.assertFalse(build._verify_mpv_dll(temp_path))
        finally:
            os.remove(temp_path)

    def test_verify_mpv_dll_accepts_expected_hash(self):
        payload = b"known mpv dll bytes"
        expected_hash = hashlib.sha256(payload).hexdigest().upper()
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(payload)
            temp_path = temp_file.name
        try:
            with mock.patch.object(build, "MPV_DLL_SHA256", expected_hash):
                self.assertTrue(build._verify_mpv_dll(temp_path))
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
