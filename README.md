# qbmanage

A command-line tool for auditing and cleaning up a qBittorrent instance. The core workflow is **iterative inspection before deletion**: run a command to see exactly what would be selected, refine your filters across multiple runs until the selection is precise, then pull the trigger to remove only what you actually want gone.

Deletion is always opt-in via `--delete` (with an interactive confirmation prompt) or `--delete --yes-do-as-i-say` for unattended runs.

## Assumption

This tool is build around the assumption that you have at least two separate directories in your setup that share files via hardlinks:
1. The qBittorrent "save path" where torrents are downloaded and tracked (e.g. `/data/qbittorrent/`).
2. A separate media/data directory where the actual files are hardlinked for use (e.g. `/data/content/`).

From this we infer:
- If a file in the `save path` is not in use by any active torrent, it's a leftover that can be safely removed. [`unusedfiles` command]
- If a torrent is still tracked but its files are missing from the `save path`, then it's effectively dead and can also be removed. [`unlinkedfiles` command]
- If a torrent has files in the `save path` but they are not hardlinked to somewhere else, then we assume the torrent and its data are both unused and can be removed. [`unlinkedfiles` command]

If your setup doesn't match this assumption (e.g. you don't use hardlinks, or you have more than two directories involved), the tool may still be useful but you'll need to adjust your filters accordingly and be extra careful when deleting.

If you are using a tool like Sonarr/Radarr/Lidarr that automatically imports but you have used copy in the past or you have issues with hardlinks, you can use my other script [find-duplicates](https://github.com/chrisb09/find-duplicates) to replace duplicate files with hardlinks before running `qbmanage` to clean up unlinked torrents.

## Features

| Command | Description |
|---|---|
| `status` | Connection check + torrent count and total size |
| `overview` | Aggregate stats: size, downloaded, uploaded, ratio |
| `listmessages` | Identify and remove torrents by tracker error messages (e.g. "not found", "deleted from tracker") |
| `unusedfiles` | Find and remove files on disk that belong to no active torrent |
| `unlinkedfiles` | Find and remove torrents whose hardlinked files have gone missing |

## Requirements

- Python 3.10+
- A running qBittorrent instance with Web UI enabled

Python dependencies (see `requirements.txt`):

```
qbittorrent-api>=7.0.0
PyYAML>=6.0
pandas>=1.5.0
```

## Installation

```bash
git clone <repo-url>
cd qbmanage
pip install -r requirements.txt
```

## Configuration

Copy and edit `config.yml`:

```yaml
qbit:
  host: localhost
  port: 8080
  username: admin
  password: adminadmin
```

## Usage

```bash
python qbmanage.py [--config config.yml] [--path-prefix /mnt/remote] <command> [options]
```

### `status`
```bash
python qbmanage.py status
```

### `overview`
```bash
python qbmanage.py overview
```

### `listmessages`
Groups all torrents by their tracker-reported message (e.g. "torrent not found", "torrent deleted", "unregistered"). Use the filter flags to narrow the selection down to exactly the torrents you want to remove, inspect the output, adjust, and re-run until satisfied — then add `--delete` to act on it.

```bash
# Inspect first
python qbmanage.py listmessages --message ".*unregistered.*" --tracker ".*debian.*"

# Remove when happy with selection
python qbmanage.py listmessages --message ".*unregistered.*" --tracker ".*debian.*" --delete
```

Options: `--tracker`, `--message`, `--hash`, `--torrent` (all regex), `--full`, `--no-progress`, `--delete`, `--yes-do-as-i-say`

### `unusedfiles`
Scans the qBittorrent save directory and lists every file not referenced by any active torrent — leftovers from removed torrents, partial downloads, etc. Safe to inspect repeatedly before committing to deletion.

```bash
# Inspect
python qbmanage.py unusedfiles --full

# Remove
python qbmanage.py unusedfiles --full --delete
```

Options: `--full`, `--no-progress`, `--delete`, `--yes-do-as-i-say`

### `unlinkedfiles`
Designed for setups where qBittorrent files are hardlinked into a separate media/data directory. Finds torrents that are partially or fully missing their hardlinks on disk — meaning the actual data is gone even though the torrent is still tracked. The rich include/exclude filter set lets you zero in on exactly what to clean up before removing anything.

```bash
# Inspect
python qbmanage.py unlinkedfiles --include-categories "movies" --exclude-trackers ".*private.*"

# Remove when happy with selection
python qbmanage.py unlinkedfiles --include-categories "movies" --exclude-trackers ".*private.*" --delete
```

Options: `--exclude-/include-{trackers,messages,hashes,categories,tags}` (all regex), `--no-progress`, `--delete`, `--yes-do-as-i-say`

### Global options

| Flag | Description |
|---|---|
| `--config` | Path to config file (default: `config.yml`) |
| `--path-prefix` | Prepend a prefix to all file paths (useful for remote mounts) |
