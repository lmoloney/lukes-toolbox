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

__github_route_user() {
  local owner
  owner="$(__github_owner_from_origin 2>/dev/null)" || {
    print -r -- "$GITHUB_PERSONAL_USER"
    return 0
  }
  if __github_owner_in "$owner" "${GITHUB_WORK_OWNERS[@]}"; then
    print -r -- "$GITHUB_WORK_USER"
    return 0
  fi
  if __github_owner_in "$owner" "${GITHUB_PERSONAL_OWNERS[@]}"; then
    print -r -- "$GITHUB_PERSONAL_USER"
    return 0
  fi
  print -r -- "$GITHUB_PERSONAL_USER"
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

github-which-account() {
  local owner user
  owner="$(__github_owner_from_origin 2>/dev/null || true)"
  user="$(__github_route_user)"
  if [[ -n "$owner" ]]; then
    printf 'repo-owner=%s account=%s\n' "$owner" "$user"
  else
    printf 'repo-owner=none account=%s\n' "$user"
  fi
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
  user="$(__github_route_user)"
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
  user="$(__github_route_user)"
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
  user="$(__github_route_user)"
  token="$(__github_token_for_user "$user")" || {
    echo "Unable to get GH token for $user." >&2
    return 1
  }
  GH_TOKEN="$token" GITHUB_TOKEN="$token" GITHUB_ACCESS_TOKEN="$token" "$@"
}
