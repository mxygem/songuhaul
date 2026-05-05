from __future__ import annotations

import shutil
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
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

    def test_move_plan_skips_song_already_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            source = root / "input" / "Duplicate Song"
            write_song_files(source)
            write_song_files(output_dir / "Duplicate Song")

            stderr = StringIO()
            with redirect_stderr(stderr):
                plan = songuhaul.build_move_plan(
                    [
                        songuhaul.SongDiscovery(
                            source=source,
                            archive=None,
                            deletable_archive=None,
                        )
                    ],
                    output_dir,
                )

            self.assertEqual([], plan)
            self.assertIn("warning: skipping duplicate song already in output", stderr.getvalue())

    def test_move_plan_collects_duplicate_already_in_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            source = root / "input" / "Duplicate Song"
            destination = output_dir / "Duplicate Song"
            write_song_files(source)
            write_song_files(destination)

            duplicates: list[str] = []
            stderr = StringIO()
            with redirect_stderr(stderr):
                plan = songuhaul.build_move_plan(
                    [
                        songuhaul.SongDiscovery(
                            source=source,
                            archive=None,
                            deletable_archive=None,
                        )
                    ],
                    output_dir,
                    duplicates=duplicates,
                )

            self.assertEqual([], plan)
            self.assertEqual("", stderr.getvalue())
            self.assertEqual([f"{source} -> {destination}"], duplicates)

    def test_move_plan_suffixes_duplicate_names_from_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            first = root / "input-a" / "Duplicate Song"
            second = root / "input-b" / "Duplicate Song"
            write_song_files(first)
            write_song_files(second)

            plan = songuhaul.build_move_plan(
                [
                    songuhaul.SongDiscovery(
                        source=first,
                        archive=None,
                        deletable_archive=None,
                    ),
                    songuhaul.SongDiscovery(
                        source=second,
                        archive=None,
                        deletable_archive=None,
                    ),
                ],
                output_dir,
            )

            self.assertEqual(
                [output_dir / "Duplicate Song", output_dir / "Duplicate Song-2"],
                [item.destination for item in plan],
            )

    def test_collect_song_directories_collects_invalid_archive_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            work_dir = root / "work"
            input_dir.mkdir()
            (input_dir / "broken.zip").write_text("not a real zip")

            failures: list[str] = []
            stderr = StringIO()
            with redirect_stderr(stderr):
                discoveries = songuhaul.collect_song_directories(
                    input_dir,
                    work_dir,
                    failures=failures,
                )

            self.assertEqual([], discoveries)
            self.assertEqual("", stderr.getvalue())
            self.assertEqual(1, len(failures))
            self.assertIn("skipping invalid zip archive", failures[0])

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

    def test_move_songs_makes_read_only_extracted_tree_writable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "input" / "Locked Song"
            output_dir = root / "output"
            write_song_files(source)
            extra_dir = source / "album"
            extra_dir.mkdir()
            extra_file = extra_dir / "cover.txt"
            extra_file.write_text("cover")

            (source / "song.ini").chmod(0o400)
            extra_file.chmod(0o400)
            extra_dir.chmod(0o500)
            source.chmod(0o500)

            plan = [
                songuhaul.MovePlan(
                    source=source,
                    destination=output_dir / source.name,
                    archive=None,
                    deletable_archive=None,
                )
            ]

            with redirect_stdout(StringIO()):
                songuhaul.move_songs(plan, output_dir)

            destination = output_dir / "Locked Song"
            self.assertTrue(destination.is_dir())
            self.assertTrue(destination.stat().st_mode & stat.S_IWUSR)
            self.assertTrue((destination / "album").stat().st_mode & stat.S_IWUSR)
            self.assertTrue((destination / "song.ini").stat().st_mode & stat.S_IWUSR)
            self.assertTrue((destination / "album" / "cover.txt").stat().st_mode & stat.S_IWUSR)

    def test_move_songs_skips_duplicate_destination_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            duplicate_source = root / "input" / "Duplicate Song"
            next_source = root / "input" / "Next Song"
            duplicate_destination = output_dir / "Duplicate Song"
            next_destination = output_dir / "Next Song"
            write_song_files(duplicate_source)
            write_song_files(next_source)
            write_song_files(duplicate_destination)

            plan = [
                songuhaul.MovePlan(
                    source=duplicate_source,
                    destination=duplicate_destination,
                    archive=None,
                    deletable_archive=None,
                ),
                songuhaul.MovePlan(
                    source=next_source,
                    destination=next_destination,
                    archive=None,
                    deletable_archive=None,
                ),
            ]

            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                songuhaul.move_songs(plan, output_dir)

            self.assertIn("warning: skipping duplicate song already in output", stderr.getvalue())
            self.assertTrue(duplicate_source.is_dir())
            self.assertTrue(duplicate_destination.is_dir())
            self.assertFalse(next_source.exists())
            self.assertTrue(next_destination.is_dir())

    def test_move_songs_collects_duplicate_destination_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            duplicate_source = root / "input" / "Duplicate Song"
            next_source = root / "input" / "Next Song"
            duplicate_destination = output_dir / "Duplicate Song"
            next_destination = output_dir / "Next Song"
            write_song_files(duplicate_source)
            write_song_files(next_source)
            write_song_files(duplicate_destination)

            plan = [
                songuhaul.MovePlan(
                    source=duplicate_source,
                    destination=duplicate_destination,
                    archive=None,
                    deletable_archive=None,
                ),
                songuhaul.MovePlan(
                    source=next_source,
                    destination=next_destination,
                    archive=None,
                    deletable_archive=None,
                ),
            ]

            duplicates: list[str] = []
            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                songuhaul.move_songs(plan, output_dir, duplicates=duplicates)

            self.assertEqual("", stderr.getvalue())
            self.assertEqual([f"{duplicate_source} -> {duplicate_destination}"], duplicates)
            self.assertTrue(duplicate_source.is_dir())
            self.assertTrue(duplicate_destination.is_dir())
            self.assertFalse(next_source.exists())
            self.assertTrue(next_destination.is_dir())

    def test_move_songs_collects_failure_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "output"
            missing_source = root / "input" / "Missing Song"
            next_source = root / "input" / "Next Song"
            next_destination = output_dir / "Next Song"
            write_song_files(next_source)

            plan = [
                songuhaul.MovePlan(
                    source=missing_source,
                    destination=output_dir / missing_source.name,
                    archive=None,
                    deletable_archive=None,
                ),
                songuhaul.MovePlan(
                    source=next_source,
                    destination=next_destination,
                    archive=None,
                    deletable_archive=None,
                ),
            ]

            failures: list[str] = []
            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                songuhaul.move_songs(plan, output_dir, failures=failures)

            self.assertEqual("", stderr.getvalue())
            self.assertEqual(1, len(failures))
            self.assertIn("could not move", failures[0])
            self.assertIn("Missing Song", failures[0])
            self.assertFalse(next_source.exists())
            self.assertTrue(next_destination.is_dir())

    def test_failure_summary_reports_all_failures(self) -> None:
        failures = ["first failure", "second failure"]

        stderr = StringIO()
        with redirect_stderr(stderr):
            songuhaul.print_failure_summary(failures)

        self.assertIn("Failures encountered:", stderr.getvalue())
        self.assertIn("- first failure", stderr.getvalue())
        self.assertIn("- second failure", stderr.getvalue())

    def test_duplicate_summary_reports_all_duplicates(self) -> None:
        duplicates = [
            "/input/First Song -> /output/First Song",
            "/input/Second Song -> /output/Second Song",
        ]

        stderr = StringIO()
        with redirect_stderr(stderr):
            songuhaul.print_duplicate_summary(duplicates)

        self.assertIn("Duplicates skipped:", stderr.getvalue())
        self.assertIn("- /input/First Song -> /output/First Song", stderr.getvalue())
        self.assertIn("- /input/Second Song -> /output/Second Song", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
