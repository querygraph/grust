#!/bin/zsh
# usage: land.sh COMMIT NATIVE_LOG FROZEN_DIR PIPELINES_DIR. Refuses unless all three passed on this exact commit.
set -e -o pipefail
R=/Users/alexy/src/sail-pipelines-proposal; C=$1; L=$2; F=$3; T=$4
[[ -n $T ]] || { print "REFUSED: no pipelines run given"; exit 1; }
[[ $(tail -1 $T/pytest.log) != *[0-9]\ failed* && $(tail -1 $T/pytest.log) != *[0-9]\ error* && $(tail -1 $T/pytest.log) == *passed* ]] || { print "REFUSED: pipelines $(tail -1 $T/pytest.log)"; exit 1; }
[[ $(tail -1 $L) == GATE=0 ]] || { print "REFUSED: native gate $(tail -1 $L)"; exit 1; }
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python - $F $C <<'P'
import json,sys
r=json.load(open(sys.argv[1]+'/receipt.json'))
assert r.get('pytest')==dict(tests=300,failures=0,errors=0,skipped=0), r.get('pytest')
assert sys.argv[2] in json.dumps(r), 'frozen receipt is for another commit'
P
cd $R; git add -A crates python Cargo.lock
[[ $(git write-tree) == $(git rev-parse $C^{tree}) ]] || { print "REFUSED: tree differs"; exit 1; }
[[ $(git rev-parse HEAD) == $(git rev-parse $C^) ]] || { print "REFUSED: parent differs"; exit 1; }
git reset -q --soft $C; git rev-parse --short HEAD; git status --porcelain | wc -l
