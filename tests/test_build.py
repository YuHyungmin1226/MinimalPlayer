import hashlib
import os
import tempfile
import unittest
from unittest import mock

import build


class BuildTest(unittest.TestCase):
    def test_build_accepts_isolated_output_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch.object(build, "IS_WINDOWS", False), \
                mock.patch.object(build, "IS_MAC", False), \
                mock.patch.object(build.PyInstaller.__main__, "run") as run:
            dist_dir = os.path.join(temp_dir, "dist")
            work_dir = os.path.join(temp_dir, "work")
            spec_dir = os.path.join(temp_dir, "spec")

            build.build(dist_dir=dist_dir, work_dir=work_dir, spec_dir=spec_dir)

            params = run.call_args.args[0]
            self.assertIn(f"--distpath={dist_dir}", params)
            self.assertIn(f"--workpath={work_dir}", params)
            self.assertIn(f"--specpath={spec_dir}", params)

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
