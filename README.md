# qbmanage

A command-line tool for auditing and cleaning up a qBittorrent instance. The core workflow is **iterative inspection before deletion**: run a command to see exactly what would be selected, refine your filters across multiple runs until the selection is precise, then pull the trigger to remove only what you actually want gone.

Deletion is always opt-in via `--delete` (with an interactive confirmation prompt) or `--delete --yes-do-as-i-say` for unattended runs.

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
python qbmanage.py listmessages --message ".*unregistered.*" --tracker ".*blutopia.*"

# Remove when happy with selection
python qbmanage.py listmessages --message ".*unregistered.*" --tracker ".*blutopia.*" --delete
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
