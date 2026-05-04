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

Key commands: `github-which-account`, `gh-personal`, `gh-work`, `copilot-personal`, `copilot-work`, `github-auto <command>`
