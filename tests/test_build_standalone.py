from __future__ import annotations

import os
import stat
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_standalone import copy_executable_file, write_zip_tree


class StandaloneBuildTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Windows filesystems do not expose Unix execute bits")
    def test_copy_executable_file_adds_execute_bits(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "setup_uinput_permissions.sh"
            destination = root / "bundle" / "setup_uinput_permissions.sh"
            source.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            source.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

            copy_executable_file(source, destination)

            mode = destination.stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)

    def test_write_zip_tree_preserves_executable_bits(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stage_root = root / "stage"
            script = stage_root / "axidev-osk" / "setup_uinput_permissions.sh"
            archive_path = root / "bundle.zip"
            script.parent.mkdir(parents=True)
            script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            script.chmod(
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IXGRP
                | stat.S_IROTH
                | stat.S_IXOTH
            )

            write_zip_tree(archive_path, stage_root)

            with zipfile.ZipFile(archive_path) as archive:
                info = archive.getinfo("axidev-osk/setup_uinput_permissions.sh")
                mode = info.external_attr >> 16

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertTrue(mode & stat.S_IXGRP)
        self.assertTrue(mode & stat.S_IXOTH)


if __name__ == "__main__":
    unittest.main()
