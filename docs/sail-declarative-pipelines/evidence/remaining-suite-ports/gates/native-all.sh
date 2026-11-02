#!/bin/zsh
set -o pipefail
R=/Users/alexy/src/sail-pipelines-proposal; cd /Users/alexy/src/sail-sdp-gate
export CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0 PYO3_PYTHON=$R/.venv/bin/python PYTHONPATH=$R/.venv/lib/python3.12/site-packages VIRTUAL_ENV=$R/.venv SAIL_IGGY_SERVER_BINARY=/Users/alexy/src/iggy-fable-pin-target/release/iggy-server
P="-p sail-plan -p sail-spark-connect -p sail-session -p sail-sdp-control -p sail-delta-lake -p sail-execution -p sail-common -p sail-common-datafusion -p sail-sql-analyzer -p sail-sql-parser -p sail-catalog -p sail-data-source -p sail-object-store -p sail-catalog-memory"
for c in crates/sail-iggy*; do [[ -d $c ]] && P="$P -p ${c:t}"; done
eval cargo +nightly fmt $P -- --check && eval cargo +1.98.1 clippy $P --all-targets --all-features --locked -- -D warnings && eval cargo +1.98.1 test $P --lib --locked --all-features
echo GATE=$?
