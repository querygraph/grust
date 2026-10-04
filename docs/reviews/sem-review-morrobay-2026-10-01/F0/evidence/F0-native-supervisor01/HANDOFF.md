# F0 native one-shot source preparation

## Scope

Governing instructions: `/Users/alexy/src/grust/AGENTS.md`. This preparation
changes no Rust or repository source. It admits the exact six borrowed Git
blobs from Grust `796b24be244f068554f885cfa33ff2d745c75682`.
`source-manifest.json` records their physical SHA-256, size and Git blob IDs.
The crate's Cargo.lock is committed in that source: blob
`2f48ca88e32771710e82f7087143296a7b52f1dd`, 20,599 bytes, SHA
`53211a0a5e2c1972ade3f97dab33e00f8cec249b142d5214676895d9a41c2136`.
Locked Arrow/Parquet is 59.3.0; the borrowed profile uses thin LTO and one
codegen unit. No dependencies were selected or downloaded by this author.

Root already completed the native build at
`/Volumes/Apo/graph-tests/results/sem-review-20261001/F0-native-build01`.
The actual root receipt reports Cargo/rustc **1.98.1**, LLVM 22.1.8,
Mach-O x86_64, release opt3/thin-LTO/codegen1/debug0/striptrue/incremental0,
eight build jobs, `--locked --release`, unchanged three crate files and
released locks. This compiler differs from the borrowed Capitola 1.97.1
results and the prior native engine build. No matched compiler/image or
cross-host ratio is qualified. The target was on Apo; private Cargo cache
selection is not explicit in the retained root environment, so this handoff
makes no private-cache provenance claim.

## Inputs and four cells

Timed input files reside under `/Users/alexy/src/grust-benchmark-data`.
Graph500 original Apo downloads were located through the retained B8
download receipt; root copied and fully hash-admitted their bytes onto the
internal SSD. `graph500-24/preservation.json` is separately pinned.
Cit source pins come from the retained A2 validation receipt.

| Order | Dataset | Form | V | E | Arcs | Logical CSR bytes |
|---|---|---|---:|---:|---:|---:|
| 1 | cit-Patents | directed | 3,774,768 | 16,518,947 | 16,518,947 | 126,472,084 |
| 2 | cit-Patents | undirected | 3,774,768 | 16,518,947 | 33,037,894 | 192,547,872 |
| 3 | graph500-24 | directed | 8,870,942 | 260,379,520 | 260,379,520 | 1,183,453,160 |
| 4 | graph500-24 | undirected | 8,870,942 | 260,379,520 | 520,759,040 | 2,224,971,240 |

Each is exactly one fresh process, four Rayon threads, default u32 dense
targets, automatic direct-table/identity mapping, no `--wide`, no
`--no-table`, no retry, no page-cache flush. Sources and inputs are assumed
valid as in the borrowed program. The source retains null/footer/count and
endpoint checks inside its own measured execution; this wrapper adds no
algorithm action or data validation inside that timer.

The CSR byte formula is `(V+1)*8 + V*8 + arcs*4`; it excludes original and
dense endpoint arrays, the mapping table, counts/cursors, decoder buffers,
allocator overhead and sort workspace. Original endpoints and dense mapped
endpoints can overlap during mapping. Thus CSR bytes are not peak memory.
Existing Capitola RSS is historical evidence only. Current peak RSS must be
observed by the actual one-shot run; no 32 GiB capacity conclusion follows
from this modeled array arithmetic. The host is shared, with no OS CPU,
memory or swap limit. The runner records actual platform/host-memory data,
not PSS/cgroup substitutes.

## Timer and result limits

The unchanged Rust program records read, map and build durations and its
total starting before the first Parquet read; printed values have millisecond
precision. Rayon pool creation precedes that internal timer. The target
vectors are branch-local and are dropped after their target-sum checksum,
before the final maximum-degree calculation and JSON print. Internal build
timing includes this target-array teardown. No usable CSR is exported.

The wrapper separately records Popen through waited `/usr/bin/time` exit,
including process startup and final teardown. Input/source/tool/helper and
binary hashing are outside that boundary. `time.txt` is retained unchanged;
macOS `maximum resident set size` is bytes. No time is subtracted or combined
into a new algorithm boundary.

Exit zero implies the original internal target-sum assertion did not fail.
The wrapper checks the raw single JSON result's exact V/E/arcs/form, four
threads, u32 target width, logical CSR formula, finite nonnegative timers and
millisecond rounding bounds. **A target sum is an internal guard, not a full
CSR topology oracle**: target ordering or a compensating wrong edge can evade
it. Every receipt keeps `full_topology_oracle=false`.

## Root execution

Copy the frozen helper directory unchanged to a durable Apo preparation
directory. `prepare_config.py` pins the actual helper directory, the completed
root build receipt/binary, the six borrowed source files, tool files, both
SSD pairs and their small provenance receipts. It hashes no large input;
the runner verifies full input bytes before and after all cells, outside the
process timers. Config generation is metadata-only and does not launch the
binary. Root reviews the generated config before launching.

Use the root native Python with Pydantic installed. With isolated Python,
insert the exact helper directory explicitly; direct `python -I script.py`
does not expose its sibling modules. Example bootstrap (replace the helper,
config and run-output paths with the final durable paths):

```sh
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -I -B -c 'import runpy,sys; sys.path.insert(0,sys.argv[1]); sys.argv=[sys.argv[1]+"/prepare_config.py","--output",sys.argv[2],"--run-output",sys.argv[3]]; runpy.run_path(sys.argv[0],run_name="__main__")' "$SUPPORT" "$CONFIG" "$RUN_OUTPUT"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -I -B -c 'import runpy,sys; sys.path.insert(0,sys.argv[1]); sys.argv=[sys.argv[1]+"/run_native.py","--config",sys.argv[2]]; runpy.run_path(sys.argv[0],run_name="__main__")' "$SUPPORT" "$CONFIG"
```

The runner requires native macOS, fresh output, absence of the declared
`gate.lock`, and exclusive ownership of `serial-queue.lock`. It refuses an
existing output/lock, admits at least 10 GiB free output-disk space, uses
600-second cell and 15-second owned closure deadlines, records durable PID,
command, timestamps and log hashes, and checks the private process group
after every waited exit. Unexpected descendants are terminated only inside
that owned group and make the cell fail; later cells are explicitly skipped.
Failures retain the lock and all evidence for root review; successful full
closure releases only this runner's lock. No force cleanup or resume exists.
Root independently audits owned groups, final retention and shared-host
activity after the run, as for other native diagnostic experiments.

## Source gate

Ruff and strict mypy pass on four typed modules. Ten bounded controls cover
all four count/byte contracts, false counts/width, raw type/NaN/thread refusal,
macOS RSS units/uniqueness, actual build contract, changed source/compiler or
flags, durable initial receipt serialization, input mutation and forced owned
cleanup failing the outcome. Children are mocked; no engine, native import,
build, probe, large payload scan, download or repository mutation was run by
this author. These are source/protocol controls, not native qualification.
