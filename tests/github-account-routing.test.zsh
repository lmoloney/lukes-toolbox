#!/usr/bin/env zsh
# Test harness for utils/github-account-routing.zsh
#
# Self-contained — no bats/external deps. Run with:
#   zsh tests/github-account-routing.test.zsh
#
# Each case sources the routing module fresh in a subshell, builds the
# minimum context needed (fake git repos, fake PWD, owner lists), then
# checks the output of __github_route_explain (the canonical decision
# function — single line "<step> <user>").
#
# Exits 0 if all cases pass, 1 otherwise.

set -u
emulate -L zsh

SCRIPT_DIR="${0:A:h}"
MODULE="$SCRIPT_DIR/../utils/github-account-routing.zsh"
if [[ ! -f "$MODULE" ]]; then
  print -u2 -- "Cannot find $MODULE"
  exit 2
fi

# Sandbox for fake repos
SANDBOX="$(mktemp -d -t github-account-routing-test.XXXXXX)"
trap 'rm -rf "$SANDBOX"' EXIT INT TERM

pass=0
fail=0
failed_cases=()

# Usage: assert_eq "<label>" "<expected>" "<actual>"
assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    print -- "  PASS  $label"
    (( pass++ ))
  else
    print -- "  FAIL  $label"
    print -- "        expected: $expected"
    print -- "        actual:   $actual"
    (( fail++ ))
    failed_cases+=("$label")
  fi
}

# Run __github_route_explain in a fresh subshell. Arguments after the path
# are forwarded as gh args. The owner lists and path arrays are pinned for
# deterministic tests.
route() {
  local cwd="$1"; shift
  zsh -c '
    set -u
    cd "$1" || exit 99
    shift
    GITHUB_PERSONAL_USER=personaluser
    GITHUB_WORK_USER=workuser
    source "'"$MODULE"'"
    GITHUB_WORK_OWNERS=(workorg gim-home)
    GITHUB_PERSONAL_OWNERS=(personaluser personalorg lmoloney)
    GITHUB_WORK_PATHS=("'"$SANDBOX"'/workpath")
    GITHUB_PERSONAL_PATHS=("'"$SANDBOX"'/personalpath")
    __github_route_explain "$@"
  ' _ "$cwd" "$@"
}

# Build fixtures
mkdir -p "$SANDBOX/empty"            # not a git repo, not a known path
mkdir -p "$SANDBOX/workpath/subdir"  # under a configured work-path prefix
mkdir -p "$SANDBOX/personalpath"     # under a configured personal-path prefix

# Real git repo with personal-remote
mkdir -p "$SANDBOX/personal-repo"
command git -C "$SANDBOX/personal-repo" init -q
command git -C "$SANDBOX/personal-repo" remote add origin \
  "https://github.com/personalorg/foo.git"

# Real git repo with work-remote
mkdir -p "$SANDBOX/work-repo"
command git -C "$SANDBOX/work-repo" init -q
command git -C "$SANDBOX/work-repo" remote add origin \
  "git@github.com:workorg/bar.git"

# Personal-remote repo nested inside the work path prefix
mkdir -p "$SANDBOX/workpath/nested-personal"
command git -C "$SANDBOX/workpath/nested-personal" init -q
command git -C "$SANDBOX/workpath/nested-personal" remote add origin \
  "https://github.com/personalorg/leaf.git"

# Repo with an unrecognized owner — should fall through past remote step
mkdir -p "$SANDBOX/unknown-repo"
command git -C "$SANDBOX/unknown-repo" init -q
command git -C "$SANDBOX/unknown-repo" remote add origin \
  "https://github.com/some-random-org/x.git"

print -- "Running routing tests against $MODULE"
print -- ""

# ---------- args ----------

assert_eq "args: -R routes by explicit work owner" \
  "args workuser" \
  "$(route "$SANDBOX/empty" pr list -R workorg/bar)"

assert_eq "args: --repo=OWNER/REPO" \
  "args personaluser" \
  "$(route "$SANDBOX/empty" issue list --repo=personalorg/foo)"

assert_eq "args: repo clone OWNER/REPO" \
  "args workuser" \
  "$(route "$SANDBOX/empty" repo clone workorg/bar)"

assert_eq "args: URL form https" \
  "args workuser" \
  "$(route "$SANDBOX/empty" repo clone https://github.com/workorg/bar.git)"

assert_eq "args: URL form ssh" \
  "args workuser" \
  "$(route "$SANDBOX/empty" repo clone git@github.com:workorg/bar.git)"

assert_eq "args: api repos/OWNER/REPO" \
  "args personaluser" \
  "$(route "$SANDBOX/empty" api repos/personalorg/foo/issues)"

assert_eq "args: api with interleaved flag pairs" \
  "args workuser" \
  "$(route "$SANDBOX/empty" api -X POST -H Accept:foo repos/workorg/bar/issues)"

assert_eq "args: api with --jq flag pair" \
  "args workuser" \
  "$(route "$SANDBOX/empty" api --jq .login orgs/workorg)"

assert_eq "args: api graphql falls through" \
  "default personaluser" \
  "$(route "$SANDBOX/empty" api graphql -f query=xxx)"

assert_eq "args: api user falls through" \
  "default personaluser" \
  "$(route "$SANDBOX/empty" api user)"

assert_eq "args: bare repo name NOT parsed as owner" \
  "default personaluser" \
  "$(route "$SANDBOX/empty" repo create my-new-thing)"

assert_eq "args: unknown owner falls through" \
  "default personaluser" \
  "$(route "$SANDBOX/empty" pr list -R unknown-org/x)"

# ---------- args win over remote ----------

assert_eq "args win over remote: personal args inside work repo" \
  "args personaluser" \
  "$(route "$SANDBOX/work-repo" repo view personalorg/foo)"

# ---------- remote ----------

assert_eq "remote: personal" \
  "remote personaluser" \
  "$(route "$SANDBOX/personal-repo")"

assert_eq "remote: work" \
  "remote workuser" \
  "$(route "$SANDBOX/work-repo")"

assert_eq "remote wins over path (nested personal repo in work path)" \
  "remote personaluser" \
  "$(route "$SANDBOX/workpath/nested-personal")"

# ---------- path ----------

assert_eq "path: work-path no remote no args" \
  "path workuser" \
  "$(route "$SANDBOX/workpath/subdir")"

assert_eq "path: personal-path no remote no args" \
  "path personaluser" \
  "$(route "$SANDBOX/personalpath")"

# ---------- default ----------

assert_eq "default: no remote, no args, unknown path" \
  "default personaluser" \
  "$(route "$SANDBOX/empty")"

assert_eq "default: unknown remote, unknown path" \
  "default personaluser" \
  "$(route "$SANDBOX/unknown-repo")"

# ---------- summary ----------

print -- ""
print -- "Results: $pass passed, $fail failed"
if (( fail > 0 )); then
  print -u2 -- ""
  print -u2 -- "Failed cases:"
  for c in "${failed_cases[@]}"; do
    print -u2 -- "  - $c"
  done
  exit 1
fi
exit 0
