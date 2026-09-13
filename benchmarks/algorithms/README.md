# Generalized Grust algorithm receipts

These are local correctness and resource observations for the upstream Rust
kernels and ordinary registry-backed Cypher executor. They are separate from the
historical Docker experiment in `adversarial-graph-algorithms/publication`.
No timing from another provider or execution class is used here.

Build and run from the repository root on Linux:

```sh
cargo build --release --locked -p grust-algorithm-procedures --example full_path_receipt
python3 benchmarks/algorithms/full_path_receipt.py direct 1024 --output /tmp/direct-1024.json
python3 benchmarks/algorithms/full_path_receipt.py cypher 1024 --output /tmp/cypher-1024.json
```

Use 65536 for the full chain. Output files must not already exist. Failed runs
retain their exit code, stdout and stderr. Each run uses one algorithm thread,
affinity to two available logical CPUs, a 4 GiB virtual address-space limit, a
256 MiB application working-memory allowance and a one-hour cooperative deadline.
Affinity is not a CPU quota. RLIMIT_AS is not a cgroup resident-memory ceiling.
Input construction is outside the application allowance and measured separately;
process wall time and maximum RSS include it. These are not Docker protocol parity
measurements or statistical performance estimates.

The direct participant calls `grust_algorithms::shortest_paths` and visits every
node and cost in every reconstructed path. The Cypher participant registers
`grust_algorithm_procedures` and runs ordinary CALL/YIELD/UNWIND/index/aggregation.
It uses neither Icecat nor Grustcat. Both assert independent closed-form counts
and sums only **after** consumption. All 65,536 source-to-target paths include the
source. There are 2,147,516,416 entries in **each** path array; the numeric node
and cost sums are both 46,912,496,107,520. Small structural path tests also verify
interior edges and cumulative costs; a checksum alone is not a general path proof.

## Retained observations, 2026-09-13

One sample, zero warmups per case. See the JSON for unrounded values and machine
identity. The two 1024-node Cypher receipts document different implementation
stages and must not be pooled as repeated samples.

| Receipt | Status | Execution seconds | Process wall seconds | Maximum RSS KiB |
| --- | --- | ---: | ---: | ---: |
| `cypher-1024-initial.json` | pass | 1.315 | 1.322 | 9,840 |
| `cypher-1024-array-fusion.json` | pass | 0.209 | 0.215 | 9,676 |
| `direct-65536.json` | pass | 107.061 | 107.147 | 102,740 |
| `cypher-65536.json` | pass | 1008.484 | 1008.571 | 113,248 |

Receipts live under `evidence/2026-09-13/`. Direct execution includes projection,
shortest-path computation, reconstruction and consumption; projection has its own
nested timer. Cypher execution includes registry construction, parsing, policy
validation, projection, kernels and ordinary query consumption. Cypher does not
yet export separate preparation, compilation and kernel timers: those receipt
fields are null, not zero. Process wall includes startup and input construction.
Transport/serialization and prepared-plan timing are not measured independently.

The first three receipts predate source hashing in the harness. They are retained
as exploratory observations without retroactively invented source hashes. The
large Cypher receipt records binary SHA-256
`cae945ea129bfd9f67cf33cc0ed16a983c21ed65f75b194f0f0017cc7da98c20`
and the measured working-source digest. Its commit field predates uncommitted
implementation. Later catalog, projection-cache and traversal additions are not
part of that measured binary. A source digest records the listed Rust/manifests,
not a build attestation. Release qualification must identify the final source.

`stage_companion.py` verifies the companion's frozen context and adds separately
named `grust_upstream_direct` and `grust_upstream_cypher` participants in a new
staging directory. Historical sources, participants and official GDS calls remain
intact. The staged image runs `check_upstream.py` against the independent C++
participant before qualification. `participant_audit.py` retains process failures
and raw output separately from answer validation. Container receipts disclose
projection, query, verification and process boundaries; the earlier local receipts
do not establish container parity.

```sh
python3 benchmarks/algorithms/stage_companion.py \
  --frozen-context ../adversarial-graph-algorithms/.docker-context \
  --output /tmp/grust-upstream-context
```
