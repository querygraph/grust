# Generalized Grust algorithm receipts

These are local correctness and resource observations for the upstream Rust
kernels and ordinary registry-backed Cypher executor. They are separate from the
historical Docker experiment in `adversarial-graph-algorithms/publication`.
Each timing stays attributed to its provider and execution class.

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

## Upstream Docker qualification

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
docker build --target benchmark -t grust-upstream-algorithms:local \
  /tmp/grust-upstream-context
```

Prepare the frozen context with the companion's default `docker/prepare.py` first.
Its Compose Neo4j service must be healthy on `graph-algorithm-bench_bench`; retain
the pinned official server/plugin versions. Run the staged image directly so the
companion's `docker/run.sh` cannot replace the staged sources:

```sh
mkdir -p /tmp/grust-upstream-results
docker run --rm --user "$(id -u):$(id -g)" \
  --network graph-algorithm-bench_bench --cpus 2 --memory 4g \
  -e NEO4J_URI=bolt://neo4j:7687 \
  -e BENCH_NEO4J_HEAP=2G -e BENCH_NEO4J_PAGE_CACHE=512M \
  -v /tmp/grust-upstream-results:/work grust-upstream-algorithms:local \
  --full-path --sizes 128 --warmups 1 --repeats 1 --label upstream-smoke
```

For actual full-chain completion, use `--full-path --algorithms dijkstra
--families path --sizes 16384 65536 --warmups 0 --repeats 1` and a new label/output
directory. This can run for many minutes. Keep the generated environment, results,
process audit and Markdown report together. A completed process is not yet a
correctness pass; the comparison must finish successfully. Single repetitions are
completion evidence, not statistical performance qualification.

The upstream 256 MiB allowance accounts for algorithm/query working storage.
Caller-owned input, final legacy tables after query return, and protocol output
conversion buffers remain outside that logical allowance. The 4 GiB container
limit covers the whole benchmark process tree and file cache. Container memory
samples are not per-participant maximum RSS. Neo4j has its own separate 4 GiB
container; neither participant group borrows the other's memory envelope.


Acorn 0.14.0 qualification is retained under `evidence/2026-09-13/`:

- `grust-acorn-upstream-image-validation.json`: 72 checks, all pass.
- `grust-acorn-upstream-smoke.json` and `grust-acorn-upstream-medium.json`: 30 cases
  each at 128 and 1,024 nodes, one warmup and one measured repetition, all pass.
- `grust-acorn-upstream-completion.json`: actual weighted full paths at 16,384 and
  65,536 nodes, no warmups and one measured repetition, all comparisons pass.
- `grust-acorn-upstream-container.json`: image/source identity and resource/report
  boundaries; companion environment files retain per-file source hashes.

The weighted 65,536-node run consumes 2,147,516,416 entries in each array, with
node checksum 46,912,496,107,520 and cost checksum 750,516,181,958,851. Its raw
upstream distance-output hashes agree with the retained reference implementations.
The upstream direct kernel/consumption timer is 54.834 seconds; ordinary Cypher's
query timer is 817.917 seconds. These are different consumption/timer boundaries,
not a measurement of dispatch overhead alone. Whole-container peak memory sampled
during completion is 216,145,920 bytes; no per-participant RSS is inferred.

Historical frozen smoke/completion receipts remain separate. Original image reports
are retained as `*-image-report.md`; the main Markdown reports are regenerated
from unchanged JSON to clarify historical Arrow timing and caller-owned memory.
Runtime source is pinned in the container receipt; later changes only clarify
rustdoc links, documentation and reporting. Statistical performance qualification,
prepared-query phase measurements and isolated per-participant RSS remain unclaimed.
