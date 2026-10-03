#!/usr/bin/env bash
# Fetch the pinned LSQB source into upstream/lsqb, which is not checked in. The
# offline tests read its example dataset, Cypher sources and expected output.
# The commit, size and digest are the ones README.md and run-upstream.sh pin.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly commit=242cb2fd31340ca688954cb94794d74c0d5b6f92
readonly url="https://codeload.github.com/ldbc/lsqb/tar.gz/${commit}"
readonly sha256=db17ee8b0a8559d6cb7c06e1388e6d89cee2ac924779473ac847965c0c0d37bb
readonly bytes=2861380
readonly target="${root}/upstream/lsqb"

if [[ -d "${target}/data/social-network-sfexample-projected-fk" ]]; then
    echo "fetch-upstream.sh: ${target} is already present"
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
curl --fail --silent --show-error --location --retry 3 --output "${work}/lsqb.tar.gz" "$url"

actual_bytes=$(wc -c < "${work}/lsqb.tar.gz" | tr -d ' ')
if command -v sha256sum >/dev/null; then
    actual_sha256=$(sha256sum "${work}/lsqb.tar.gz" | cut -d' ' -f1)
else
    actual_sha256=$(shasum -a 256 "${work}/lsqb.tar.gz" | cut -d' ' -f1)
fi
if [[ "$actual_bytes" != "$bytes" || "$actual_sha256" != "$sha256" ]]; then
    echo "fetch-upstream.sh: archive is ${actual_bytes} bytes, ${actual_sha256};" \
        "expected ${bytes} bytes, ${sha256}" >&2
    exit 1
fi

tar -xzf "${work}/lsqb.tar.gz" -C "$work"
mkdir -p -- "${root}/upstream"
mv -- "${work}/lsqb-${commit}" "$target"
echo "fetch-upstream.sh: ${target} is LSQB ${commit}"
