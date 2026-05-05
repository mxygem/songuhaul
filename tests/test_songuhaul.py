from __future__ import annotations

import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import songuhaul


ROOT = Path(__file__).resolve().parents[1]
TESTDATA = ROOT / "testdata"


def write_song_files(song_dir: Path) -> None:
    song_dir.mkdir(parents=True)
    (song_dir / "song.ini").write_text("[song]\nname = Test Song\n")
    (song_dir / "notes.chart").write_text("chart")
    (song_dir / "song.opus").write_text("audio")


class TestSongFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("bsdtar") is None:
            raise unittest.SkipTest("bsdtar is required to extract .7z test fixtures")

        cls.temp_dir = tempfile.TemporaryDirectory()
        found = songuhaul.collect_song_directories(TESTDATA, Path(cls.temp_dir.name))
        cls.songs_by_name = {song.source.name: song for song in found}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def assertSongFound(self, name: str) -> songuhaul.SongDiscovery:
        self.assertIn(name, self.songs_by_name)
        song = self.songs_by_name[name]
        self.assertTrue(songuhaul.is_song_directory(song.source))
        return song

    def test_unzipped_song_folder_at_root(self) -> None:
        song = self.assertSongFound(
            "Billie Eilish - all the good girls go to hell [gem,mindlessbi]"
        )

        self.assertIsNone(song.archive)
        self.assertIsNone(song.deletable_archive)

    def test_zipped_song_folder_at_root(self) -> None:
        song = self.assertSongFound("Our Last Night - Be Our Guest (OCBG0LD,gem)")

        self.assertIsNotNone(song.archive)
        self.assertEqual(
            "Our Last Night - Be Our Guest (OCBG0LD,gem).7z", song.archive.name
        )
        self.assertEqual(song.archive, song.deletable_archive)

    def test_zipped_folder_containing_two_zipped_song_folders(self) -> None:
        expected = {
            "Alexisonfire - .44 Caliber Love Letter [gem]": "Alexisonfire - .44 Caliber Love Letter [gem].zip",
            "Alexisonfire - Pulmonary Archery [gem]": "Alexisonfire - Pulmonary Archery [gem].7z",
        }

        for song_name, archive_name in expected.items():
            song = self.assertSongFound(song_name)
            self.assertIsNotNone(song.archive)
            self.assertEqual(archive_name, song.archive.name)
            self.assertIsNotNone(song.deletable_archive)
            self.assertEqual("Alexisonfire.zip", song.deletable_archive.name)

    def test_zipped_folder_containing_nested_folder_with_two_zipped_songs(self) -> None:
        expected = {
            "Coheed and Cambria - Crossing The Frame [gem]": "Coheed and Cambria - Crossing The Frame [gem].zip",
            "Coheed and Cambria - 2113 [gem]": "Coheed and Cambria - 2113 [gem].zip",
            "Coheed and Cambria - The Crowing [gem]": "Coheed and Cambria - The Crowing [gem].zip",
        }

        for song_name, archive_name in expected.items():
            song = self.assertSongFound(song_name)
            self.assertIsNotNone(song.archive)
            self.assertEqual(archive_name, song.archive.name)
            self.assertIsNotNone(song.deletable_archive)
            self.assertEqual("Coheed and Cambria.zip", song.deletable_archive.name)

    def test_move_plan_keeps_output_flat(self) -> None:
        output_dir = Path(self.temp_dir.name) / "output"
        plan = songuhaul.build_move_plan(list(self.songs_by_name.values()), output_dir)

        self.assertEqual(len(self.songs_by_name), len(plan))
        self.assertEqual({output_dir}, {item.destination.parent for item in plan})
        self.assertEqual(
            set(self.songs_by_name),
            {item.destination.name for item in plan},
        )

    def test_move_songs_deletes_original_archive_after_successful_move(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            build_dir = root / "build" / "Delete Me"
            work_dir = root / "work"
            archive = input_dir / "delete-me.zip"

            input_dir.mkdir()
            write_song_files(build_dir)

            with zipfile.ZipFile(archive, "w") as zip_file:
                for file in build_dir.iterdir():
                    zip_file.write(file, Path("Delete Me") / file.name)

            discoveries = songuhaul.collect_song_directories(input_dir, work_dir)
            plan = songuhaul.build_move_plan(discoveries, output_dir)

            with redirect_stdout(StringIO()):
                songuhaul.move_songs(plan, output_dir, delete_archives=True)

            self.assertFalse(archive.exists())
            self.assertTrue((output_dir / "Delete Me").is_dir())
            self.assertTrue((output_dir / "Delete Me" / "song.ini").is_file())


if __name__ == "__main__":
    unittest.main()
