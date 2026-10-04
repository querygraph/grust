# B8 orchestration contract

These helpers prepare execution. Root owns staging and all Docker/engine runs.
Their offline controls launch no engines, containers, downloads, or live locks.

## Campaign and staging

`run_shapes_host.py` takes `--campaign <JSON>` on every invocation. The campaign
has `host_root` under `/Volumes/Apo/graph-tests/results/sem-review-20261001/`
with a unique `B8-...` basename, and the matching
`guest_root=/targets/sem-review-20261001/<basename>`. Root precreates the host
directory and prepares its `support/` payload. Guest staging refuses an existing
namespace. Campaign defaults are recorded in the host receipt:

| Field | Default | Scope |
| --- | ---: | --- |
| `archive_reserve_bytes` | 24 GiB | Actual free Apo space before every job |
| `guest_reserve_bytes` | 256 GiB | Actual free guest volume space before every job |
| `reference_timeout_seconds` | 7200 s | Reference container attach |
| `cell_timeout_seconds` | 3600 s | Whole cell container attach, including outside-timer work |
| `archive_copy_timeout_seconds` | 1800 s | Exact owned Docker artifact copy |

The disk reserves are declared admission thresholds, not observed peak storage.
Choose them before cells from the admitted input/reference/output and spill plan.
The frozen matrix's copy deadline is adapted only for the exact Docker context,
container, guest payload and host artifact destination. Other commands retain
their original deadlines. The adapter is removed even on interruption.

The payload uses A2's `payload.tar`, `payload-manifest.json`,
`support-manifest.json`, and `delta.bundle` protocol. Required support includes
`engine_shapes.py`, `supervise_shape.py`, `prepare_shapes.py`, `shape_reference.py`
and `shape_oracle.py`; list every staged helper in the support hash manifest.
The Sail controller, borrowed harness, runtime/native binaries and image remain
the recorded f3/6ae/561/ff/A1 pins. Staging verifies all payload bytes before
cloning and checking out the detached controller.

## Reference and cell commands

```text
run_shapes_host.py stage --campaign campaign.json --run-id stage01
run_shapes_host.py run --campaign campaign.json --run-id tiny-reference01 --kind reference --config tiny-reference.json
run_shapes_host.py run --campaign campaign.json --run-id tiny-adjacency-union01 --kind cell --config tiny-adjacency-union.json
```

A reference config is `shape_reference.InputConfig`: absolute `vertices`,
`edges`, `output`, and exact `vertices_sha256`/`edges_sha256`.
Its output must be `<guest_root>/references/<run-id>`. Original Parquet inputs
are borrowed; the reference phase never rewrites them.

A cell config is `supervise_shape.CellConfig`: `dataset` (evidence label),
`shape`, `variant`, absolute `repo`, `harness_repo`, `support`, `output`,
`vertices`, `edges`, `references`, `binary`, `reference_receipt_sha256`, and
`support_sha256`. `timeout_seconds` defaults to 1500; `minimum_free_bytes` must
explicitly match the campaign's guest reserve. Its output must be
`<guest_root>/cells/<run-id>`, and references must belong to this campaign.
The typed effective config, original config bytes and their hash are retained.

## Measurement, verification and retention

Each cell uses one fresh private 16 CPU, 32 GiB container with no swap. The
timed child gets a fresh `output/engine/` directory. Launch through completed
wait includes startup, input reads/snapshots, shared shape preparation, explain,
materialization/export and engine cleanup. Hashes, the full physical oracle,
parent emergency closure and archival are outside that timer.

The parent requires complete engine PSS samples, zero OOM events, exact input,
reference, helper, binary and source identities before/after, and no owned
survivors or emergency cleanup. Raw explain files, output schemas and oracle
progress remain available on failure. Cgroup peaks include prelaunch/cache work;
the final peak includes the oracle. These are not algorithm-only memory peaks.

The guest archive manifest covers every file, including raw Parquet, plans,
logs and receipts. The host compares every copied file and the complete file
set against that manifest on Apo. Only after passing producer checks and
certain container closure does a separate owned helper recheck the guest bytes
and remove that exact passed cell directory. Reference directories stay intact.
Failed/uncertain payloads and the shared lock remain for root review. There are
no retries or automatic admission changes.

Root owns the declared paired order and role ledger: warmup union/array-explode,
then `U A A U / U A A U`. Exclude warmups and retain every outcome. These are
isolated relational shapes; representative maps and the initial label update
do not qualify a complete WCC implementation.
