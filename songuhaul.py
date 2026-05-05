#!/usr/bin/env python3
"""Unpack Clone Hero song archives into a flat songs directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


SONG_METADATA_FILES = {"song.ini"}
SONG_NOTE_FILES = {"notes.chart", "notes.mid"}
SONG_AUDIO_EXTENSIONS = {".opus", ".ogg", ".mp3", ".wav", ".flac"}
ARCHIVE_EXTENSIONS = {".zip", ".7z"}


@dataclass(frozen=True)
class SongDiscovery:
    source: Path
    archive: Path | None
    deletable_archive: Path | None


@dataclass(frozen=True)
class MovePlan:
    source: Path
    destination: Path
    archive: Path | None
    deletable_archive: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unzip Clone Hero song archives and move song folders to one flat output directory."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=None,
        help="Directory to search recursively for zip files. Defaults to the current working directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Directory where song folders will be moved. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print what would be moved without writing changes. Use --no-dry-run to move files.",
    )
    parser.add_argument(
        "--delete-archives",
        action="store_true",
        help="Delete original input archives after their song folders are successfully moved.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> tuple[Path, Path]:
    cwd = Path.cwd().resolve()
    input_dir = (args.input or cwd).expanduser().resolve()
    output_dir = (args.output or cwd).expanduser().resolve()

    if input_dir == cwd and output_dir == cwd:
        raise ValueError(
            "input and output cannot both default to the current working directory; "
            "provide --input or --output."
        )

    if input_dir == output_dir:
        raise ValueError("input and output must be different directories.")

    if not input_dir.is_dir():
        raise ValueError(f"input is not a directory: {input_dir}")

    return input_dir, output_dir


def is_song_directory(path: Path) -> bool:
    if not path.is_dir():
        return False

    file_names = {child.name.lower() for child in path.iterdir() if child.is_file()}
    suffixes = {child.suffix.lower() for child in path.iterdir() if child.is_file()}

    return (
        SONG_METADATA_FILES.issubset(file_names)
        and bool(SONG_NOTE_FILES & file_names)
        and bool(SONG_AUDIO_EXTENSIONS & suffixes)
    )


def find_song_directories(root: Path) -> list[Path]:
    songs: list[Path] = []
    directories = [root, *sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda p: str(p))]
    for directory in directories:
        if is_song_directory(directory) and not any(parent in songs for parent in directory.parents):
            songs.append(directory)
    return songs


def find_archives(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS),
        key=lambda p: str(p),
    )


def ensure_safe_member(destination: Path, member_name: str, archive: Path) -> None:
    target = (destination / member_name).resolve()
    if not target.is_relative_to(destination.resolve()):
        raise ValueError(f"archive contains an unsafe path: {archive}")


def extract_archive(archive: Path, destination: Path) -> None:
    if archive.suffix.lower() == ".7z":
        extract_7z_archive(archive, destination)
        return

    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            ensure_safe_member(destination, member.filename, archive)
        zip_file.extractall(destination)


def extract_7z_archive(archive: Path, destination: Path) -> None:
    bsdtar = shutil.which("bsdtar")
    if bsdtar is None:
        raise RuntimeError("bsdtar is required to extract .7z archives")

    listing = subprocess.run(
        [bsdtar, "-tf", str(archive)],
        check=True,
        capture_output=True,
        text=True,
    )
    for member_name in listing.stdout.splitlines():
        ensure_safe_member(destination, member_name, archive)

    subprocess.run([bsdtar, "-xf", str(archive), "-C", str(destination)], check=True)


def collect_song_directories(input_dir: Path, work_dir: Path) -> list[SongDiscovery]:
    """Return song folders and the archives they came from."""
    discovered = [
        SongDiscovery(source=song_dir, archive=None, deletable_archive=None)
        for song_dir in find_song_directories(input_dir)
    ]
    seen_archives: set[Path] = set()
    pending_archives = [(archive, archive) for archive in find_archives(input_dir)]

    while pending_archives:
        archive, deletable_archive = pending_archives.pop(0)
        archive_key = archive.resolve() if archive.exists() else archive
        if archive_key in seen_archives:
            continue
        seen_archives.add(archive_key)

        extract_to = work_dir / f"archive-{len(seen_archives)}"
        extract_to.mkdir(parents=True, exist_ok=False)
        try:
            extract_archive(archive, extract_to)
        except zipfile.BadZipFile:
            print(f"warning: skipping invalid zip archive: {archive}", file=sys.stderr)
            continue
        except ValueError as error:
            print(f"warning: {error}", file=sys.stderr)
            continue
        except (RuntimeError, subprocess.CalledProcessError) as error:
            print(f"warning: could not extract archive {archive}: {error}", file=sys.stderr)
            continue

        for song_dir in find_song_directories(extract_to):
            discovered.append(
                SongDiscovery(
                    source=song_dir,
                    archive=archive,
                    deletable_archive=deletable_archive,
                )
            )

        pending_archives.extend(
            (nested_archive, deletable_archive) for nested_archive in find_archives(extract_to)
        )

    return discovered


def unique_destination(output_dir: Path, name: str, reserved: set[Path]) -> Path:
    candidate = output_dir / name
    if candidate not in reserved and not candidate.exists():
        reserved.add(candidate)
        return candidate

    counter = 2
    while True:
        candidate = output_dir / f"{name}-{counter}"
        if candidate not in reserved and not candidate.exists():
            reserved.add(candidate)
            return candidate
        counter += 1


def build_move_plan(song_dirs: list[SongDiscovery], output_dir: Path) -> list[MovePlan]:
    reserved: set[Path] = set()
    plan: list[MovePlan] = []

    for song_dir in song_dirs:
        destination = unique_destination(output_dir, song_dir.source.name, reserved)
        plan.append(
            MovePlan(
                source=song_dir.source,
                destination=destination,
                archive=song_dir.archive,
                deletable_archive=song_dir.deletable_archive,
            )
        )

    return plan


def archives_to_delete(plan: list[MovePlan]) -> list[Path]:
    archives = {
        item.deletable_archive for item in plan if item.deletable_archive is not None
    }
    return sorted(archives, key=lambda p: str(p))


def print_plan(plan: list[MovePlan], delete_archives: bool = False) -> None:
    if not plan:
        print("No Clone Hero song folders found in zip archives.")
        return

    print("Dry run: the following song folders would be moved:")
    for item in plan:
        source_description = f"from {item.archive}" if item.archive else "unarchived"
        print(f"- {item.source} -> {item.destination} ({source_description})")

    if delete_archives:
        archives = archives_to_delete(plan)
        if archives:
            print()
            print("Dry run: the following input archives would be deleted after successful moves:")
            for archive in archives:
                print(f"- {archive}")


def move_songs(plan: list[MovePlan], output_dir: Path, delete_archives: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in plan:
        shutil.move(str(item.source), str(item.destination))
        print(f"Moved {item.destination}")

    if delete_archives:
        for archive in archives_to_delete(plan):
            if archive.exists():
                archive.unlink()
                print(f"Deleted {archive}")


def main() -> int:
    args = parse_args()

    try:
        input_dir, output_dir = validate_args(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="songuhaul-") as temp_dir:
        song_dirs = collect_song_directories(input_dir, Path(temp_dir))
        plan = build_move_plan(song_dirs, output_dir)

        if args.dry_run:
            print_plan(plan, delete_archives=args.delete_archives)
        else:
            move_songs(plan, output_dir, delete_archives=args.delete_archives)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
