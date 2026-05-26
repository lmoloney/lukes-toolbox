# lukes-toolbox

A collection of reusable developer scripts and utilities.

## Setup

Add the toolbox to your PATH (one-time):

```bash
echo 'export PATH="$HOME/.local/bin:$HOME/Developer/personal/lukes-toolbox/utils:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**Prerequisites:** Python 3.10+, chezmoi, gh CLI.

## Structure

```
lukes-toolbox/
├── utils/                    # Executable scripts (on PATH)
│   ├── chezmoi-sync          # Sync chezmoi with live system state
│   ├── dev-cleanup           # Find stale node_modules/ and .venv/
│   ├── diary-commit          # → symlink to dev-diary/diary-commit.sh
│   ├── git-status-all        # Git status for all ~/Developer repos
│   ├── har-meta              # Extract metadata from HAR files
│   ├── har-offload           # Move HARs to external storage
│   └── repo-setup            # Apply standard labels + branch protection
├── tests/                    # Self-contained zsh test harness
│   └── github-account-routing.test.zsh
├── github-account-routing.zsh  # → symlink to utils/ (sourced by .zshrc)
├── eventhubs/                # Azure Event Hub reader
├── fabric-sqlendpoint-dotnet/# Fabric SQL endpoint sample
├── setup/                    # Machine bootstrap scripts
└── sql/                      # Reusable SQL snippets
```

### repo-setup

Apply standard GitHub issue labels and branch protection rulesets to any repo.

```bash
# Full setup — personal repo (you bypass branch protection)
repo-setup --repo lmoloney/my-repo --scenario personal

# Full setup — team repo (everyone needs approved PRs)
repo-setup --repo SteamedHamsAU/my-repo --scenario team

# Labels only
repo-setup --repo lmoloney/my-repo --labels-only

# Preview without making changes
repo-setup --repo lmoloney/my-repo --scenario personal --dry-run
```

**Labels (13):** `feature`, `bug`, `chore`, `test`, `question`, `duplicate`, `help wanted`, `P0`, `P1`, `P2`, `ready`, `copilot-ready`, `blocked`. Deletes GitHub defaults (`enhancement`, `documentation`, etc.).

**Rulesets:** Protects `main` branch — block force push, restrict deletions, require PRs. `personal` scenario lets `lmoloney` bypass; `team` scenario requires 1 approval from everyone.

See [`utils/README.md`](utils/README.md) for detailed usage of each script.

## Shell integration

### GitHub account routing

Dual-account GitHub routing (personal + work). Sourced by `.zshrc`:

```zsh
source "$HOME/Developer/personal/lukes-toolbox/github-account-routing.zsh"
```

**Resolution order:** `args → git remote → path → GITHUB_PERSONAL_USER`.

1. **Args** — explicit `-R OWNER/REPO`, `--repo OWNER/REPO`, `gh repo {clone,view,fork,...} OWNER/REPO`, GitHub URLs, and owner-bearing `gh api` endpoints (`repos/OWNER/REPO`, `orgs/OWNER`, `users/OWNER`). Bare repo names like `gh repo create foo` are **not** parsed as owners.
2. **Git remote** — `remote.origin.url` of the cwd. A personal repo cloned inside `~/Developer/msft/` still routes to personal because remote wins over path.
3. **Path** — directories listed in `GITHUB_WORK_PATHS` / `GITHUB_PERSONAL_PATHS` (defaults: `~/Developer/msft` → work). Last-resort hint when args + remote yield no known owner.
4. **Default** — `GITHUB_PERSONAL_USER`.

Setting `GH_TOKEN` in the environment short-circuits the wrapper and uses that token verbatim.

```zsh
github-which-account                        # diagnose routing for current dir
github-which-account repo clone gim-home/m  # diagnose as if running that cmd
github-which-account pr list -R lmoloney/x  # check -R routing
```

Key commands: `github-which-account`, `gh-personal`, `gh-work`, `copilot-personal`, `copilot-work`, `github-auto <command>`.

Run the test harness with `zsh tests/github-account-routing.test.zsh` after any change.
