# Closed-cell collection audit

This helper reads local collected artifacts only. It neither contacts Morrobay
nor starts a container, engine, query or subprocess. The four pinned profiles
cover logging01, the compact561 smoke, and the pending logging02/03 pair using
the original 3a controller and ffcf native package. They are not a general
benchmark classifier.

Run after collection finishes, with a new output filename outside the cell:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 closed-cell-audit/audit_cell.py \
  --case logging02 --cell-dir logging02 \
  --output closed-cell-audit/logging02-verification.json
```

Run from the experiment directory. Replace both case and cell path for
`logging01`, `compact561-smoke` or `logging03`; the compact smoke cell directory
is `worker-smoke-compact561-cpu16-23`. Output creation is exclusive: an existing
receipt is never overwritten. Diagnostics archives are inspected without
extracting members. Archive and local file hashing use bounded read blocks.

`integrity_status` describes collected bytes and agreement between pinned
configuration/evidence and recorded identities, arguments, data manifests and
resource limits. It does **not** assert algorithm correctness:

- `integrity_verified` / exit 0: these integrity checks passed, even if the
  retained workload outcome is OOM or error.
- `inconclusive` / exit 2: required collection/receipt/result/closure evidence
  is missing, with no detected integrity contradiction.
- `integrity_error` / exit 1: corrupt, malformed, changed or contradictory
  evidence was detected; missing evidence is also retained separately.

Runner outcome, producer outcome, Docker state, OOM counters, outer timeout,
transport errors, cleanup errors and recorded correctness are reported
separately. This helper does not derive a new benchmark outcome, reinterpret an
observation timeout as an engine timeout, infer a first cause, or validate a
certificate. A producer's `passed` string is never the helper's correctness
verdict. `correctness_verification` is always `not_performed`.

The dataset comparison covers the producer-embedded manifest and its recorded
file hashes, not the underlying Parquet bytes. Profiles pin the retained
Graph500 manifest from logging01 and the weighted16k/native inventory from the
original local baseline receipt. Runtime289/561 binary hashes come from their
completed build receipts; logging01's original binary hash is a retained
producer claim. No result or dataset is downloaded or recomputed, and the
helper does not prove which binary a worker actually mapped at runtime.

The original logging01 host snapshot was redacted before publication. Its
`redaction.original_sha256` refers to privately retained original bytes and is
not required to equal the published file. The host snapshot is separate from
`diagnostics.tar`; all four current archive members match extracted bytes.
The helper retains this distinction without a blanket archive exception.

The profiles assume this campaign's two-worker process-cluster protocol and
pinned 120-second keepalive. Cgroup limits and OOM counters remain distinct
from sampled process memory. A zero guest swap/steal observation does not rule
out host paging. This audit gives no performance qualification or comparison.

`test_audit_cell.py` exercises both completed outcomes and corruption/missing
artifact controls in temporary copies, preserving all original evidence.
