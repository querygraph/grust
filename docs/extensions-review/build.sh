#!/usr/bin/env bash
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
python3.12 -c 'import xml.etree.ElementTree as ET; ET.fromstring("<ok/>")'
repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
builder="${FIRSTPAIR_ROOT:-$HOME/src/firstpair}/publishing/scripts/build-library-book.sh"
if [[ ! -x "$builder" ]]; then
  echo "Missing central FirstPair builder: $builder" >&2
  exit 1
fi
case "${1:-}" in
  --main) shift; books=(extensions-review) ;;
  --host) shift; books=(extensions-host-review) ;;
  *) books=(extensions-review extensions-host-review) ;;
esac
for book in "${books[@]}"; do
  "$builder" --repo-root "$repo_root" --config "docs/$book/book.build.json" "$@"
done
