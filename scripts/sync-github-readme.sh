#!/usr/bin/env bash
# Pull the generated GitHub profile READMEs from the site and commit them to the two repos.
# Run by a Jenkins job (docs/ops/github-readme-sync.md). Changes nothing unless a README differs.
#
# env:
#   README_SYNC_SSH_KEY_PERSONAL  private key (write deploy key) of farrar142/farrar142
#   README_SYNC_SSH_KEY_ORG       private key (write deploy key) of sandcorporation/.github
#   README_SYNC_BASE_URL          default https://sandcorp.co.kr
#   README_SYNC_REPO_PERSONAL     default git@github.com:farrar142/farrar142.git
#   README_SYNC_REPO_ORG          default git@github.com:sandcorporation/.github.git
# A key left unset means plain git (ssh-agent / local paths).
set -euo pipefail

BASE_URL="${README_SYNC_BASE_URL:-https://sandcorp.co.kr}"
REPO_PERSONAL="${README_SYNC_REPO_PERSONAL:-git@github.com:farrar142/farrar142.git}"
REPO_ORG="${README_SYNC_REPO_ORG:-git@github.com:sandcorporation/.github.git}"
MIN_BYTES=200
COMMIT_MESSAGE="chore: sync README from sandcorp.co.kr"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fetch() { # name -> $work/name.md ; fails on a non-200 answer or a body under MIN_BYTES
  local name="$1" url="$BASE_URL/github/readme/$1.md" code
  code="$(curl -sS -o "$work/$name.md" -w '%{http_code}' --max-time 60 "$url")" || {
    echo "error: cannot fetch $url" >&2
    return 1
  }
  if [ "$code" != "200" ]; then
    echo "error: $url answered HTTP $code" >&2
    return 1
  fi
  if [ "$(wc -c <"$work/$name.md")" -lt "$MIN_BYTES" ]; then
    echo "error: $url body is under $MIN_BYTES bytes" >&2
    return 1
  fi
}

push_one() { # name repo path-in-repo ssh-key
  local name="$1" repo="$2" path="$3" key="${4:-}" dir="$work/repo-$1"
  if [ -n "$key" ]; then
    export GIT_SSH_COMMAND="ssh -i $key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  else
    unset GIT_SSH_COMMAND || true
  fi
  git clone --quiet --depth 1 "$repo" "$dir"
  mkdir -p "$dir/$(dirname "$path")"
  cp "$work/$name.md" "$dir/$path"
  git -C "$dir" add -- "$path"
  if git -C "$dir" diff --cached --quiet; then
    echo "$name: unchanged"
    return 0
  fi
  git -C "$dir" -c user.name="sandcorp-readme-sync" -c user.email="noreply@sandcorp.co.kr" \
    commit --quiet -m "$COMMIT_MESSAGE"
  git -C "$dir" push --quiet origin HEAD
  echo "$name: pushed"
}

# Fetch both first: if either is bad, neither repo is touched.
fetch personal
fetch org
push_one personal "$REPO_PERSONAL" "README.md" "${README_SYNC_SSH_KEY_PERSONAL:-}"
push_one org "$REPO_ORG" "profile/README.md" "${README_SYNC_SSH_KEY_ORG:-}"
