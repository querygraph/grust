#!/usr/bin/env bash
# File the ten reports as issues, in order. Run by a person, from this directory:
#
#     bash file_issues.sh                 # files into lakehq/sail
#     REPO=owner/name bash file_issues.sh # or into another repository
#
# Resumable: a report whose URL is already in filed.txt is skipped. The fifth
# report refers to the first by number, so the first must be filed before it.
set -euo pipefail
cd "$(dirname "$0")"
repo=${REPO:-lakehq/sail}
touch filed.txt
for title in [0-9][0-9]-title.txt; do
    number=${title%%-*}
    if grep -q "^$number " filed.txt; then
        echo "$number already filed: $(grep "^$number " filed.txt | cut -d' ' -f2)"
        continue
    fi
    body=$(mktemp)
    first=$(grep '^01 ' filed.txt | cut -d' ' -f2 || true)
    if grep -q CHECKPOINT_ISSUE "$number-body.md"; then
        [[ -n $first ]] || { echo "$number needs report 01 filed first" >&2; exit 1; }
        sed "s|CHECKPOINT_ISSUE|#${first##*/}|" "$number-body.md" > "$body"
    else
        cp "$number-body.md" "$body"
    fi
    url=$(gh issue create --repo "$repo" --title "$(cat "$title")" --body-file "$body" | tail -n 1)
    rm -f "$body"
    echo "$number $url" | tee -a filed.txt
done
