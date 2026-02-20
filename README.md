# helpful-resources

A collection of reusable tools and scripts.

## Tools

### har-offload.sh

Move large files (HAR traces by default) to an external drive, leaving symlinks behind so repos still work transparently. Generates companion metadata files and a searchable manifest.

```bash
# Dry run — see what would be moved
./har-offload.sh --dry-run

# Move all .har files from ~/Developer to JetDrive
./har-offload.sh

# Custom source, destination, and file pattern
./har-offload.sh --source ~/Projects --dest /Volumes/External/archive --pattern "*.pcap"

# Restore — move files back from the archive
./har-offload.sh --restore
```

**What it does:**
1. Finds all files matching `--pattern` (default: `*.har`) under `--source`
2. Moves them to `--dest` preserving directory structure
3. Creates symlinks at the original locations
4. Generates `.har.md` companion files with metadata (domains, request counts, how to recapture)
5. Maintains a `manifest.json` on the destination drive for searching

### har-meta.py

Extract metadata from HAR files — domains captured, request counts, methods, status codes, and time range.

```bash
# JSON output
python3 har-meta.py trace.har

# Markdown companion file
python3 har-meta.py trace.har --format markdown --archive-path /Volumes/JetDrive/archive/trace.har -o trace.har.md
```