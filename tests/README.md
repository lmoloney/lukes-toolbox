# tests/

Self-contained zsh test harness for the routing module. No external dependencies — runs anywhere zsh and git are available.

## Run

```bash
zsh tests/github-account-routing.test.zsh
```

Exit code `0` = all pass, `1` = at least one failure (failed cases listed at the end).

Each test sources `utils/github-account-routing.zsh` in a fresh subshell with pinned owner lists and path arrays so cases are deterministic and free of host state.

## Coverage

| Category | Cases |
|---|---|
| Args parser | `-R`, `--repo=`, `repo SUB OWNER/REPO`, URL forms (https / ssh), `api repos/...`, `api orgs/...` with interleaved flag pairs, graphql / `api user` fall-through, bare-name rejection, unknown-owner fall-through |
| Args win over remote | personal-owner args inside a work-remote repo |
| Remote | personal remote, work remote, remote-wins-over-path (nested personal repo inside a work-path prefix) |
| Path | work-path hint, personal-path hint |
| Default | no signals, unknown remote owner |

If you add a new wrapper or change resolution order, extend this file before opening the PR.
