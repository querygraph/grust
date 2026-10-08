#!/usr/bin/env bash
# Full semantics + SNB qualification. Run in a clean detached checkout.
set -euo pipefail
: "${GATE_SNB_CHECKOUT:?set a clean checkout of the pinned SNB v1 implementation}"
source_commit=$(git rev-parse HEAD)
"$GATE_PYTHON" -m ruff check docs/reviews/grust-v2/wave-3/live
"$GATE_PYTHON" -m ruff format --check docs/reviews/grust-v2/wave-3/live
"$GATE_PYTHON" -m mypy --strict --follow-imports=silent docs/reviews/grust-v2/wave-3/live
bash docs/reviews/grust-v2/wave-3/live/gate-cypher.sh
"$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/scale_tests.py
for track in short complex; do
  "$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/prepare_snb.py --checkout "$GATE_SNB_CHECKOUT" --track "$track" --output "$GATE_OUTPUT/snb-$track-request.json"
  cargo run --locked --release --manifest-path docs/reviews/grust-v2/wave-3/sketch/Cargo.toml -p grust-query-qualification --bin ldbc -- "$GATE_OUTPUT/snb-$track-request.json" > "$GATE_OUTPUT/snb-$track-queries.json"
  "$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/qualify.py --sail "$SAIL_BINARY" --manifest "$GATE_OUTPUT/snb-$track-queries.json" --dataset-checkout "$GATE_SNB_CHECKOUT" --paired --output "$GATE_OUTPUT/snb-$track"
done
for replicas in ${GATE_SYNTHETIC_REPLICAS:-}; do
  "$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/prepare_snb.py --checkout "$GATE_SNB_CHECKOUT" --track complex --replicas "$replicas" --output "$GATE_OUTPUT/snb-replicas-$replicas-request.json"
  cargo run --locked --release --manifest-path docs/reviews/grust-v2/wave-3/sketch/Cargo.toml -p grust-query-qualification --bin ldbc -- "$GATE_OUTPUT/snb-replicas-$replicas-request.json" > "$GATE_OUTPUT/snb-replicas-$replicas-queries.json"
  "$GATE_PYTHON" docs/reviews/grust-v2/wave-3/live/qualify.py --sail "$SAIL_BINARY" --manifest "$GATE_OUTPUT/snb-replicas-$replicas-queries.json" --dataset-checkout "$GATE_SNB_CHECKOUT" --replicas "$replicas" --paired --output "$GATE_OUTPUT/snb-replicas-$replicas"
done
test "$(git rev-parse HEAD)" = "$source_commit"
test -z "$(git status --porcelain)"
printf 'PASSED Cypher semantics and LDBC source %s: Rust default/all-features/release; native relational/iterative/frontend/semantics; exact short/complex SNB oracle and ABBA twice; requested synthetic scales\n' "$source_commit"
