# GitHub dual-account routing helpers for interactive zsh sessions.

if [[ -n "${__GITHUB_ACCOUNT_ROUTING_LOADED:-}" ]]; then
  return 0
fi
__GITHUB_ACCOUNT_ROUTING_LOADED=1

export GITHUB_PERSONAL_USER="${GITHUB_PERSONAL_USER:-lmoloney}"
export GITHUB_WORK_USER="${GITHUB_WORK_USER:-lumolone_microsoft}"

typeset -ga GITHUB_WORK_OWNERS=(
  "lumolone_microsoft"
  "azure-data"
  "azure-data-intelligence-platform"
  "commercial-software-engineering"
  "gim-home"
  "ms-copilot"
)

typeset -ga GITHUB_PERSONAL_OWNERS=(
  "lmoloney"
  "microsoftdocs"
  "microsoftcopilot"
  "microsoft"
  "azure"
  "msft-emeads-demo"
)

# Path prefixes used as a last-resort routing hint when args + git remote
# yield no recognized owner. Extend in ~/.zshrc if needed, e.g.:
#   GITHUB_WORK_PATHS+=( "$HOME/Developer/work-extra" )
typeset -ga GITHUB_WORK_PATHS=(
  "$HOME/Developer/msft"
)
typeset -ga GITHUB_PERSONAL_PATHS=()

__github_owner_from_origin() {
  local origin owner
  origin="$(command git config --get remote.origin.url 2>/dev/null)" || return 1
  case "$origin" in
    https://github.com/*) owner="${origin#https://github.com/}" ;;
    git@github.com:*) owner="${origin#git@github.com:}" ;;
    ssh://git@github.com/*) owner="${origin#ssh://git@github.com/}" ;;
    *) return 1 ;;
  esac
  owner="${owner%%/*}"
  [[ -n "$owner" ]] || return 1
  print -r -- "${(L)owner}"
}

__github_owner_in() {
  local needle="${(L)1}"
  shift
  local candidate
  for candidate in "$@"; do
    [[ "${(L)candidate}" == "$needle" ]] && return 0
  done
  return 1
}

# Inspect gh CLI arguments and return a lowercase owner if one can be
# unambiguously inferred. Recognizes:
#   - -R OWNER/REPO  /  --repo OWNER/REPO  /  --repo=OWNER/REPO
#   - GitHub URLs: https://github.com/OWNER/REPO[.git],
#     git@github.com:OWNER/REPO[.git], ssh://git@github.com/OWNER/REPO[.git]
#   - 'gh repo {clone,view,fork,delete,rename,edit,sync,set-default,
#     deploy-key,archive,unarchive} OWNER/REPO' (requires slash form)
#   - 'gh api [flags] {repos/OWNER/REPO,orgs/OWNER,users/OWNER}[/...]'
# Returns non-zero if no owner found. Bare repo names (e.g. 'gh repo create
# my-new-repo') are intentionally NOT parsed as owners.
__github_owner_from_gh_args() {
  (( $# == 0 )) && return 1
  local -a args=("$@")
  local arg next owner stripped

  # 1) Highest priority: -R / --repo
  local i
  for (( i = 1; i <= $#args; i++ )); do
    arg="${args[i]}"
    if [[ "$arg" == "--repo="* ]]; then
      next="${arg#--repo=}"
      if [[ "$next" == */* ]]; then
        owner="${next%%/*}"
        [[ -n "$owner" ]] && { print -r -- "${(L)owner}"; return 0; }
      fi
    elif [[ "$arg" == "-R" || "$arg" == "--repo" ]]; then
      next="${args[i+1]:-}"
      if [[ "$next" == */* && "$next" != -* ]]; then
        owner="${next%%/*}"
        [[ -n "$owner" ]] && { print -r -- "${(L)owner}"; return 0; }
      fi
    fi
  done

  # 2) URL forms anywhere in args
  for arg in "${args[@]}"; do
    case "$arg" in
      https://github.com/*/*|git@github.com:*/*|ssh://git@github.com/*/*)
        stripped="$arg"
        stripped="${stripped#https://github.com/}"
        stripped="${stripped#git@github.com:}"
        stripped="${stripped#ssh://git@github.com/}"
        stripped="${stripped%.git}"
        if [[ "$stripped" == */* ]]; then
          owner="${stripped%%/*}"
          [[ -n "$owner" ]] && { print -r -- "${(L)owner}"; return 0; }
        fi
        ;;
    esac
  done

  local sub="${args[1]:-}"

  # 3) gh api — skip flag pairs, parse owner-bearing REST endpoints only
  if [[ "$sub" == "api" ]]; then
    # gh api flags that consume a value (we skip both the flag and its arg)
    local -a api_value_flags=(
      "-X" "--method" "-H" "--header" "-F" "--field" "-f" "--raw-field"
      "--input" "-q" "--jq" "--template" "--hostname" "--cache"
    )
    i=2
    while (( i <= $#args )); do
      arg="${args[i]}"
      if (( ${api_value_flags[(I)$arg]} )); then
        (( i += 2 )); continue
      fi
      if [[ "$arg" == -* ]]; then
        (( i++ )); continue   # bare flag (no value) or --flag=value
      fi
      # First non-flag = endpoint
      local endpoint="${arg#/}"
      case "$endpoint" in
        repos/*/*|orgs/*|users/*)
          local rest="${endpoint#*/}"
          owner="${rest%%/*}"
          [[ -n "$owner" ]] && { print -r -- "${(L)owner}"; return 0; }
          ;;
      esac
      return 1   # endpoint resolved but not owner-bearing (graphql, /user, /search, etc.)
    done
    return 1
  fi

  # 4) gh repo SUBCMD OWNER/REPO  (slash form only; bare names rejected)
  if [[ "$sub" == "repo" ]]; then
    local repo_sub="${args[2]:-}"
    case "$repo_sub" in
      clone|view|fork|delete|rename|edit|sync|set-default|deploy-key|archive|unarchive)
        i=3
        while (( i <= $#args )); do
          next="${args[i]}"
          if [[ "$next" == -* ]]; then
            (( i++ )); continue
          fi
          # First non-flag positional. Only treat OWNER/REPO (slash form)
          # as authoritative — bare names are too ambiguous.
          if [[ "$next" == */* ]]; then
            owner="${next%%/*}"
            [[ -n "$owner" ]] && { print -r -- "${(L)owner}"; return 0; }
          fi
          return 1
        done
        ;;
    esac
  fi

  return 1
}

# Match the given path (default: $PWD) against GITHUB_WORK_PATHS and
# GITHUB_PERSONAL_PATHS prefix lists. Returns a user on match, non-zero otherwise.
__github_user_from_path() {
  local target="${1:-$PWD}"
  local p
  for p in "${GITHUB_WORK_PATHS[@]}"; do
    [[ -z "$p" ]] && continue
    if [[ "$target" == "$p" || "$target" == "$p"/* ]]; then
      print -r -- "$GITHUB_WORK_USER"
      return 0
    fi
  done
  for p in "${GITHUB_PERSONAL_PATHS[@]}"; do
    [[ -z "$p" ]] && continue
    if [[ "$target" == "$p" || "$target" == "$p"/* ]]; then
      print -r -- "$GITHUB_PERSONAL_USER"
      return 0
    fi
  done
  return 1
}

# Resolve routing and report it. Output format: "<step> <user>" on one line,
# where <step> is one of: args | remote | path | default.
# This is the canonical decision function. __github_route_user is a shim
# that drops the step prefix for callers that only need the user.
__github_route_explain() {
  local args_owner="" remote_owner="" path_user=""
  local step="default" account="$GITHUB_PERSONAL_USER"

  if (( $# > 0 )); then
    args_owner="$(__github_owner_from_gh_args "$@" 2>/dev/null)"
  fi
  remote_owner="$(__github_owner_from_origin 2>/dev/null)"
  path_user="$(__github_user_from_path 2>/dev/null)"

  # 1) Args — only if owner is recognized; unknown owners fall through.
  if [[ -n "$args_owner" ]]; then
    if __github_owner_in "$args_owner" "${GITHUB_WORK_OWNERS[@]}"; then
      step=args; account="$GITHUB_WORK_USER"
    elif __github_owner_in "$args_owner" "${GITHUB_PERSONAL_OWNERS[@]}"; then
      step=args; account="$GITHUB_PERSONAL_USER"
    fi
  fi

  # 2) Git remote (nested-repo safe: remote wins over path)
  if [[ "$step" == "default" && -n "$remote_owner" ]]; then
    if __github_owner_in "$remote_owner" "${GITHUB_WORK_OWNERS[@]}"; then
      step=remote; account="$GITHUB_WORK_USER"
    elif __github_owner_in "$remote_owner" "${GITHUB_PERSONAL_OWNERS[@]}"; then
      step=remote; account="$GITHUB_PERSONAL_USER"
    fi
  fi

  # 3) Path-prefix hint
  if [[ "$step" == "default" && -n "$path_user" ]]; then
    step=path; account="$path_user"
  fi

  print -r -- "$step $account"
}

# Resolve which GitHub user to use for a gh/copilot invocation.
# Resolution order: args → git remote → path → GITHUB_PERSONAL_USER.
__github_route_user() {
  local result
  result="$(__github_route_explain "$@")"
  print -r -- "${result#* }"
}

__github_token_for_user() {
  local user="$1"
  command gh auth token --user "$user" 2>/dev/null
}

__copilot_startup_tip() {
  [[ -t 1 ]] || return 0
  if [[ -z "${COPILOT_UI_REMINDER_SHOWN:-}" ]]; then
    export COPILOT_UI_REMINDER_SHOWN=1
    echo "[copilot tip] Ctrl+E expands all timeline entries, Ctrl+O expands the latest, Ctrl+T toggles reasoning display." >&2
  fi
}

# Show how the wrapper would route a gh command.
#   github-which-account                       # routes for the current dir
#   github-which-account repo clone gim-home/m # routes as if running that cmd
github-which-account() {
  local result step user args_owner remote_owner
  result="$(__github_route_explain "$@")"
  step="${result%% *}"
  user="${result#* }"
  if (( $# > 0 )); then
    args_owner="$(__github_owner_from_gh_args "$@" 2>/dev/null || true)"
  fi
  remote_owner="$(__github_owner_from_origin 2>/dev/null || true)"
  printf 'step=%s account=%s args-owner=%s remote-owner=%s\n' \
    "$step" "$user" "${args_owner:-none}" "${remote_owner:-none}"
}

gh-personal() {
  local token
  token="$(__github_token_for_user "$GITHUB_PERSONAL_USER")" || {
    echo "Unable to get GH token for $GITHUB_PERSONAL_USER." >&2
    return 1
  }
  GH_TOKEN="$token" command gh "$@"
}

gh-work() {
  local token
  token="$(__github_token_for_user "$GITHUB_WORK_USER")" || {
    echo "Unable to get GH token for $GITHUB_WORK_USER." >&2
    return 1
  }
  GH_TOKEN="$token" command gh "$@"
}

gh() {
  if [[ "$1" == "auth" || -n "${GH_TOKEN:-}" ]]; then
    command gh "$@"
    return $?
  fi
  local user token
  user="$(__github_route_user "$@")"
  token="$(__github_token_for_user "$user")" || {
    echo "Unable to get GH token for $user." >&2
    return 1
  }
  GH_TOKEN="$token" command gh "$@"
}

copilot-personal() {
  local token
  token="$(__github_token_for_user "$GITHUB_PERSONAL_USER")" || {
    echo "Unable to get GH token for $GITHUB_PERSONAL_USER." >&2
    return 1
  }
  __copilot_startup_tip
  GH_TOKEN="$token" command copilot "$@"
}

copilot-work() {
  local token
  token="$(__github_token_for_user "$GITHUB_WORK_USER")" || {
    echo "Unable to get GH token for $GITHUB_WORK_USER." >&2
    return 1
  }
  __copilot_startup_tip
  GH_TOKEN="$token" command copilot "$@"
}

# Backward-compatible alias.
copilot-ms() {
  copilot-work "$@"
}

copilot() {
  if [[ -n "${GH_TOKEN:-}" ]]; then
    __copilot_startup_tip
    command copilot "$@"
    return $?
  fi
  local user token
  user="$(__github_route_user "$@")"
  token="$(__github_token_for_user "$user")" || {
    echo "Unable to get GH token for $user." >&2
    return 1
  }
  __copilot_startup_tip
  GH_TOKEN="$token" command copilot "$@"
}

github-auto() {
  if [[ "$#" -eq 0 ]]; then
    echo "Usage: github-auto <command> [args...]" >&2
    return 1
  fi
  local user token
  user="$(__github_route_user "$@")"
  token="$(__github_token_for_user "$user")" || {
    echo "Unable to get GH token for $user." >&2
    return 1
  }
  GH_TOKEN="$token" GITHUB_TOKEN="$token" GITHUB_ACCESS_TOKEN="$token" "$@"
}
