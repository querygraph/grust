#!/usr/bin/env bash
# Full semantics + SNB qualification. Run in a clean detached checkout.
set -euo pipefail
: "${GATE_SNB_CHECKOUT:?set a clean checkout of the pinned SNB v1 implementation}"
source_commit=$(git rev-parse HEAD)
"$GATE_PYTHON" -m ruff check docs/reviews/grust-v2/wave-3/live
"$GATE_PYTHON" -m ruff format --check docs/reviews/grust-v2/wave-3/live
"$GATE_PYTHON" -m mypy --strict --follow-imports=silent docs/reviews/grust-v2/wave-3/live
bash docs/reviews/grust-v2/wave-3/live/gate-cypher.sh
"$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/prepare_snb.py --checkout "$GATE_SNB_CHECKOUT" --output "$GATE_OUTPUT/snb-request.json"
cargo run --locked --release --manifest-path docs/reviews/grust-v2/wave-3/sketch/Cargo.toml -p grust-query-qualification --bin ldbc -- "$GATE_OUTPUT/snb-request.json" > "$GATE_OUTPUT/snb-queries.json"
"$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/qualify.py --sail "$SAIL_BINARY" --manifest "$GATE_OUTPUT/snb-queries.json" --dataset-checkout "$GATE_SNB_CHECKOUT" --paired --output "$GATE_OUTPUT/snb"
test "$(git rev-parse HEAD)" = "$source_commit"
test -z "$(git status --porcelain)"
printf 'PASSED Cypher semantics and LDBC source %s: Rust default/all-features/release; native relational/iterative/frontend/semantics; exact SNB oracle and ABBA twice\n' "$source_commit"
