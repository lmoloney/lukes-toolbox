# utils/

Developer workflow scripts, all on `$PATH` via `~/Developer/lukes-toolbox/utils`.

| Script | Description |
|--------|-------------|
| `chezmoi-sync` | Sync chezmoi with live system state. Re-adds files owned by external tools, diffs, confirms, applies. |
| `dev-cleanup` | Find stale `node_modules/` and `.venv/` in repos with no recent commits. Reports reclaimable space. |
| `diary-commit` | _(symlink → dev-diary)_ Commit and push the dev-diary repo, with status view. |
| `git-status-all` | Git status summary for every repo in `~/Developer`. |
| `har-meta` | Extract metadata (domains, methods, status codes) from HAR files without loading bodies. |
| `har-offload` | Move large HAR files to external storage, leaving symlinks + metadata behind. |

## Quick reference

```bash
chezmoi-sync                  # interactive: re-add → diff → confirm → apply
chezmoi-sync --status         # just show drift
chezmoi-sync --commit         # also commit+push dotfiles

dev-cleanup                   # dry-run: show stale dirs
dev-cleanup --delete          # actually remove them
dev-cleanup --age-days 60     # custom staleness threshold

diary-commit                  # show dev-diary status
diary-commit --commit 'msg'   # commit and push

git-status-all                # show dirty repos
git-status-all --all          # include clean repos
git-status-all --fetch        # fetch remotes first (slower)

har-meta file.har             # JSON metadata summary
har-meta --format markdown    # markdown output

har-offload                   # dry-run: show what would move
har-offload --dest /Volumes/X # move HARs to external drive
har-offload --restore         # reverse: pull HARs back
```
