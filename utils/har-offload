#!/usr/bin/env bash
set -euo pipefail

# har-offload.sh — Move large files to an external drive and leave symlinks behind.
# Generates companion metadata (.har.md) files and a global manifest.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAR_META="$SCRIPT_DIR/har-meta.py"

# Defaults
SOURCE="${HOME}/Developer"
DEST="/Volumes/JetDrive/har-archive"
PATTERN="*.har"
DRY_RUN=false
RESTORE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Move files matching a pattern to an external drive and create symlinks back.
Generates metadata companion files and a searchable manifest.

Options:
  --source DIR     Source directory to scan (default: ~/Developer)
  --dest DIR       Destination archive root (default: /Volumes/JetDrive/har-archive)
  --pattern GLOB   File pattern to match (default: *.har)
  --dry-run        Show what would be done without making changes
  --restore        Reverse: move files back from dest, remove symlinks
  -h, --help       Show this help
EOF
}

log()  { printf "\033[1;34m→\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m⚠\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$*"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --source)   SOURCE="$2"; shift 2 ;;
        --dest)     DEST="$2"; shift 2 ;;
        --pattern)  PATTERN="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        --restore)  RESTORE=true; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) err "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# Validate
if [[ ! -d "$SOURCE" ]]; then
    err "Source directory does not exist: $SOURCE"
    exit 1
fi

DEST_PARENT="$(dirname "$DEST")"
if [[ ! -d "$DEST_PARENT" ]]; then
    err "Destination parent does not exist: $DEST_PARENT (is the drive mounted?)"
    exit 1
fi

MANIFEST="$DEST/manifest.json"

init_manifest() {
    if [[ ! -f "$MANIFEST" ]]; then
        if $DRY_RUN; then
            log "[dry-run] Would create manifest at $MANIFEST"
        else
            mkdir -p "$DEST"
            echo '{"files":[]}' > "$MANIFEST"
        fi
    fi
}

add_to_manifest() {
    local rel_path="$1" archive_path="$2" size="$3" domains="$4" requests="$5"
    local now
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    python3 -c "
import json, sys
m = json.load(open('$MANIFEST'))
# Remove existing entry for same rel_path if re-running
m['files'] = [f for f in m['files'] if f.get('original_path') != '$rel_path']
m['files'].append({
    'original_path': '$rel_path',
    'archive_path': '$archive_path',
    'size_bytes': $size,
    'moved_at': '$now',
    'domains': $domains,
    'request_count': $requests
})
json.dump(m, open('$MANIFEST', 'w'), indent=2)
"
}

offload() {
    log "Scanning $SOURCE for '$PATTERN' ..."

    local count=0 total_bytes=0

    while IFS= read -r -d '' file; do
        # Skip files that are already symlinks
        if [[ -L "$file" ]]; then
            warn "Already a symlink, skipping: $file"
            continue
        fi

        local rel_path="${file#"$SOURCE"/}"
        local dest_file="$DEST/$rel_path"
        local dest_dir
        dest_dir="$(dirname "$dest_file")"
        local size
        size="$(stat -f%z "$file" 2>/dev/null || stat --printf="%s" "$file" 2>/dev/null)"
        local human_size
        human_size="$(python3 -c "
s=$size
for u in ('B','KB','MB','GB'):
    if s < 1024: print(f'{s:.0f} {u}'); break
    s /= 1024
")"

        if $DRY_RUN; then
            log "[dry-run] Would move: $file ($human_size)"
            log "          → $dest_file"
            log "          ← symlink back"
            log "          + generate ${file}.md"
        else
            # Create destination directory
            mkdir -p "$dest_dir"

            # Generate metadata companion file before moving
            if [[ "$PATTERN" == "*.har" ]] && [[ -f "$HAR_META" ]]; then
                log "Generating metadata for $(basename "$file") ..."
                python3 "$HAR_META" "$file" \
                    --format markdown \
                    --archive-path "$dest_file" \
                    --output "${file}.md" 2>&1 || warn "Metadata generation failed for $file"

                # Get JSON metadata for manifest
                local meta_json
                meta_json="$(python3 "$HAR_META" "$file" --format json 2>/dev/null)" || meta_json="{}"
                local domains requests
                domains="$(echo "$meta_json" | python3 -c "import json,sys; d=json.load(sys.stdin).get('domains',{}); print(json.dumps(list(d.keys())[:5]))" 2>/dev/null)" || domains="[]"
                requests="$(echo "$meta_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('total_requests',0))" 2>/dev/null)" || requests="0"
            fi

            # Move file to archive
            log "Moving $(basename "$file") ($human_size) → $dest_file"
            mv "$file" "$dest_file"

            # Create symlink at original location
            ln -s "$dest_file" "$file"
            ok "Symlinked: $file → $dest_file"

            # Update manifest
            if [[ "$PATTERN" == "*.har" ]]; then
                add_to_manifest "$rel_path" "$dest_file" "$size" "${domains:-[]}" "${requests:-0}"
            fi
        fi

        count=$((count + 1))
        total_bytes=$((total_bytes + size))
    done < <(find "$SOURCE" -name "$PATTERN" -type f -print0 2>/dev/null)

    local total_human
    total_human="$(python3 -c "
s=$total_bytes
for u in ('B','KB','MB','GB'):
    if s < 1024: print(f'{s:.0f} {u}'); break
    s /= 1024
")"

    echo ""
    if $DRY_RUN; then
        log "Dry run complete: $count files ($total_human) would be moved"
    else
        ok "Done: $count files ($total_human) moved to $DEST"
    fi
}

restore() {
    log "Restoring files from $DEST back to $SOURCE ..."

    if [[ ! -d "$DEST" ]]; then
        err "Archive directory does not exist: $DEST"
        exit 1
    fi

    local count=0

    while IFS= read -r -d '' file; do
        local rel_path="${file#"$DEST"/}"
        local orig_file="$SOURCE/$rel_path"

        if $DRY_RUN; then
            log "[dry-run] Would restore: $file → $orig_file"
            if [[ -L "$orig_file" ]]; then
                log "          Would remove symlink at $orig_file"
            fi
            if [[ -f "${orig_file}.md" ]]; then
                log "          Would remove companion ${orig_file}.md"
            fi
        else
            # Remove symlink if it exists
            if [[ -L "$orig_file" ]]; then
                rm "$orig_file"
            fi

            # Move file back
            local orig_dir
            orig_dir="$(dirname "$orig_file")"
            mkdir -p "$orig_dir"
            mv "$file" "$orig_file"
            ok "Restored: $orig_file"

            # Optionally remove companion metadata
            if [[ -f "${orig_file}.md" ]]; then
                rm "${orig_file}.md"
                log "Removed companion: ${orig_file}.md"
            fi

            count=$((count + 1))
        fi
    done < <(find "$DEST" -name "$PATTERN" -type f -print0 2>/dev/null)

    echo ""
    if $DRY_RUN; then
        log "Dry run complete: $count files would be restored"
    else
        ok "Done: $count files restored to $SOURCE"
    fi
}

# Main
init_manifest

if $RESTORE; then
    restore
else
    offload
fi
