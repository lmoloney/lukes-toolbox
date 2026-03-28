# lukes-toolbox

A collection of reusable developer scripts and utilities.

## Setup

Add the toolbox to your PATH (one-time):

```bash
echo 'export PATH="$HOME/.local/bin:$HOME/Developer/lukes-toolbox/utils:$PATH"' >> ~/.zshrc
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
│   └── har-offload           # Move HARs to external storage
├── github-account-routing.zsh  # → symlink to utils/ (sourced by .zshrc)
├── eventhubs/                # Azure Event Hub reader
├── fabric-sqlendpoint-dotnet/# Fabric SQL endpoint sample
├── setup/                    # Machine bootstrap scripts
└── sql/                      # Reusable SQL snippets
```

See [`utils/README.md`](utils/README.md) for detailed usage of each script.

## Shell integration

### GitHub account routing

Dual-account GitHub routing (personal + work). Sourced by `.zshrc`:

```zsh
source "$HOME/Developer/lukes-toolbox/github-account-routing.zsh"
```

Key commands: `github-which-account`, `gh-personal`, `gh-work`, `copilot-personal`, `copilot-work`, `github-auto <command>`
