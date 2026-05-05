# songuhaul

`songuhaul` is a small Python CLI for unpacking Clone Hero song archives into one flat songs directory.

It recursively scans an input directory for supported archives, extracts them into a temporary workspace, discovers Clone Hero song folders, and moves each complete song folder to the output directory root. Song files such as `song.ini`, `notes.chart`, `song.opus`, and artwork stay together inside their song folder.

## Requirements

- Python 3.10 or newer
- `bsdtar` on `PATH` for `.7z` archive support

`.zip` files are handled with Python's standard library.

## How It Works

The CLI:

1. Reads `--input` and `--output` directory flags.
2. Defaults either missing directory flag to the current working directory.
3. Rejects runs where input and output resolve to the same directory.
4. Recursively finds `.zip` and `.7z` archives.
5. Extracts archives into a temporary workspace, including nested archives.
6. Finds Clone Hero song folders by looking for `song.ini`, a notes file such as `notes.chart` or `notes.mid`, and an audio file such as `.opus`, `.ogg`, `.mp3`, `.wav`, or `.flac`.
7. Moves discovered song folders directly under the output directory, keeping the output as flat as possible.

If two songs have the same folder name, the later destination is suffixed with `-2`, `-3`, and so on.

When `--delete-archives` is set with `--no-dry-run`, original input archives are deleted after their discovered song folders are successfully moved. For songs found inside nested archives, `songuhaul` deletes the top-level archive from the input directory, not temporary archives extracted during processing.

## Build

There is no package build step required. The CLI is a standalone Python script with no Python dependencies.

To prepare it for direct execution:

```bash
chmod +x songuhaul.py
```

To verify the script and tests:

```bash
python3 -m py_compile songuhaul.py
python3 -m unittest discover -s tests -v
```

## Run

Dry-run mode is enabled by default. It prints what would move and where, without creating output folders or moving songs:

```bash
./songuhaul.py --input /path/to/downloads --output /path/to/clone-hero/songs
```

Actually move the discovered song folders:

```bash
./songuhaul.py --input /path/to/downloads --output /path/to/clone-hero/songs --no-dry-run
```

Move songs and delete the original input archives after successful moves:

```bash
./songuhaul.py --input /path/to/downloads --output /path/to/clone-hero/songs --no-dry-run --delete-archives
```

Short flags are also available:

```bash
./songuhaul.py -i /path/to/downloads -o /path/to/clone-hero/songs --no-dry-run
```

If only one directory is specified, the other defaults to the current working directory:

```bash
./songuhaul.py --input /path/to/downloads
./songuhaul.py --output /path/to/clone-hero/songs
```

The command will fail if both input and output would be the current working directory, or if both point to the same directory.
