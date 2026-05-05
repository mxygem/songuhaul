from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import songuhaul


ROOT = Path(__file__).resolve().parents[1]
TESTDATA = ROOT / "testdata"


class TestSongFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("bsdtar") is None:
            raise unittest.SkipTest("bsdtar is required to extract .7z test fixtures")

        cls.temp_dir = tempfile.TemporaryDirectory()
        found = songuhaul.collect_song_directories(TESTDATA, Path(cls.temp_dir.name))
        cls.songs_by_name = {song_dir.name: (song_dir, archive) for song_dir, archive in found}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def assertSongFound(self, name: str) -> tuple[Path, Path | None]:
        self.assertIn(name, self.songs_by_name)
        song_dir, archive = self.songs_by_name[name]
        self.assertTrue(songuhaul.is_song_directory(song_dir))
        return song_dir, archive

    def test_unzipped_song_folder_at_root(self) -> None:
        _, archive = self.assertSongFound(
            "Billie Eilish - all the good girls go to hell [gem,mindlessbi]"
        )

        self.assertIsNone(archive)

    def test_zipped_song_folder_at_root(self) -> None:
        _, archive = self.assertSongFound("Our Last Night - Be Our Guest (OCBG0LD,gem)")

        self.assertIsNotNone(archive)
        self.assertEqual("Our Last Night - Be Our Guest (OCBG0LD,gem).7z", archive.name)

    def test_zipped_folder_containing_two_zipped_song_folders(self) -> None:
        expected = {
            "Alexisonfire - .44 Caliber Love Letter [gem]": "Alexisonfire - .44 Caliber Love Letter [gem].zip",
            "Alexisonfire - Pulmonary Archery [gem]": "Alexisonfire - Pulmonary Archery [gem].7z",
        }

        for song_name, archive_name in expected.items():
            _, archive = self.assertSongFound(song_name)
            self.assertIsNotNone(archive)
            self.assertEqual(archive_name, archive.name)

    def test_zipped_folder_containing_nested_folder_with_two_zipped_songs(self) -> None:
        expected = {
            "Coheed and Cambria - Crossing The Frame [gem]": "Coheed and Cambria - Crossing The Frame [gem].zip",
            "Coheed and Cambria - 2113 [gem]": "Coheed and Cambria - 2113 [gem].zip",
            "Coheed and Cambria - The Crowing [gem]": "Coheed and Cambria - The Crowing [gem].zip",
        }

        for song_name, archive_name in expected.items():
            _, archive = self.assertSongFound(song_name)
            self.assertIsNotNone(archive)
            self.assertEqual(archive_name, archive.name)

    def test_move_plan_keeps_output_flat(self) -> None:
        output_dir = Path(self.temp_dir.name) / "output"
        plan = songuhaul.build_move_plan(list(self.songs_by_name.values()), output_dir)

        self.assertEqual(len(self.songs_by_name), len(plan))
        self.assertEqual({output_dir}, {item.destination.parent for item in plan})
        self.assertEqual(
            set(self.songs_by_name),
            {item.destination.name for item in plan},
        )


if __name__ == "__main__":
    unittest.main()
