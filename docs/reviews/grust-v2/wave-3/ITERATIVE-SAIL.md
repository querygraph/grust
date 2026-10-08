# Wave 3: iterative Sail execution

This follow-up to PR #43 adds a native Sail execution adapter for one ranged
path segment. It remains in the standalone unpublished draft workspace;
production crates and the Sail fork are unchanged.

## Compiler and execution contract

`QueryResolver.resolve_iterative` explicitly admits iterative plans. The ordinary
resolver retains its finite SQL admission policy. `Op::Traverse` carries typed
seed and adjacency inputs, hop range, path mode, and whether WALK shortest-path
execution may prune previously reached endpoint pairs. The inputs normalize
identities to `{group, identity}`; the graph name belongs to the surrounding plan.

`SailSql.emit_program` returns a `SailProgram`: ordered `TraversalStep` values and
a final SQL query. `emit` refuses a program containing iterative steps, so an
ordinary SQL consumer cannot silently omit traversal. The optimizer treats the
traversal as a boundary while optimizing its relational inputs. Multiple steps
are executed in dependency order and integrated with the final relational query.

The Python adapter in `live/iterative.py` runs the program through native Sail's
Spark Connect interface in local mode on a shared local filesystem. Process-cluster
execution is not qualified by this adapter. Seed and adjacency queries are materialized once to
fresh Parquet files. Each subsequent frontier is a join against the adjacency,
with identity arrays recording its path. Writes are unsorted; no sort followed
by `checkpoint()` is used. The adapter collects only scalar state counts;
graph rows remain in Sail and Parquet. The caller supplies a stable graph
snapshot; seed and adjacency materializations are separate operations.

Evaluate the returned frame inside the `Execution` context. That context owns
its temporary views, query tag and scratch directory; it removes them after
success, cancellation or failure. The final result becomes available only after
all iterative steps have completed successfully.

## Path semantics

- Unbounded TRAIL, SIMPLE and ACYCLIC enumeration stops at an empty frontier.
  TRAIL excludes reused edges. ACYCLIC excludes repeated vertices. SIMPLE permits
  a closing cycle but does not expand it further and does not reuse an edge.
- SHORTEST and ALL SHORTEST under WALK use level-synchronous expansion. Once the
  minimum-hop threshold has been reached, pairs seen in earlier rounds are
  excluded. Same-round ties retain parallel-edge path multiplicity. Before that
  threshold, pairs remain eligible: a shorter inadmissible path cannot suppress
  the shortest admissible longer path.
- Other modes enumerate their admissible paths, then use the existing relational
  path-selection operator. This preserves their path-history constraints.
- ANY returns a minimum-hop choice; a one-path tie is unspecified. ALL SHORTEST
  retains every tie. Endpoint predicates run before relational path selection.
- Zero-hop paths, OPTIONAL nullability, multiple graph groups and incoming edges
  retain the existing draft path identity representation.

Unbounded ALL WALK is refused: cycles can produce infinitely many paths. The
adapter does not scan a graph to certify that it is acyclic. Multiple ranged
segments, weighted paths, endpoint-correlated edge predicates and non-immutable
predicates remain typed refusals. There is no hidden eight-hop bound on an
admitted iterative query.

## Resources and cancellation

`Limits` sets a state-row limit, scratch-byte limit and round limit. These are
execution limits, not query semantics: exceeding one raises `ResourceExceeded`,
never a successful truncated result. A `max_rows + 1` sentinel distinguishes a
complete state from overflow. Scratch size is checked after materialization;
a single write can transiently exceed that budget. This is not a filesystem
quota. Enumeration and shortest-path ties can still produce exponential output.

The native harness launches Sail with a 256 MiB fair memory pool. That constrains
DataFusion-managed query allocations, **not total process RSS**. An existing
Sail server must be configured by its owner; the adapter does not reset a shared
server's memory policy. A separate one-byte pool probe verifies the allocation
refusal and records the actual engine error.

`Cancellation.cancel` sets an event and calls Spark Connect `interruptTag` for
this execution's tag. The adapter checks cancellation at every action boundary,
raises `Cancelled`, and cleans its scratch state. The qualification controls
exercise cancellation before work and immediately after a materialized frontier.
They verify the live interruption RPC and cooperative stopping; they do not
claim a measured bound on interruption latency inside every Sail operator.

## Qualification and remaining work

Native fixtures include an eleven-hop chain, cycles, parallel edges, incoming
paths, minimum-hop and zero-hop constraints, all path modes, OPTIONAL unmatched
vertices and two iterative steps in one relational query. Every query runs before
and after optimization with bag multiplicity and output-type checks. An independent
Python DFS oracle uses immutable fixture tuples, not Sail plans, to cross-check
the cyclic-graph fixture expectations.

The source gate also re-runs the existing finite relational fixtures. Rust tests
check plain-SQL refusal, iterative program admission, infinite WALK refusal,
correlated and volatile predicate refusal. Live controls distinguish resource
errors from cancellation and verify scratch cleanup. Development receipts,
including the first memory-error classifier mismatch, are retained separately.

This is functional qualification, not a scaling or speed result. Next work is
parser integration, broader correlated/multi-segment operators, and LDBC cost and
physical-plan qualification before migration into production crates.

## Exact-source verdict

`PASSED iterative Sail native source gate 618f217a5999ff2f531224210b0da77b3bf5de62`

The detached checkout remained clean and its HEAD unchanged. Formatting, release
Clippy, Ruff and strict Mypy passed. All 30 Rust tests passed under default
features and again under all features. All 114 native Sail cells passed: 92
existing relational cells and 22 iterative cells. Seven controls passed,
including the managed-memory allocation refusal. The client was Python 3.12.6
with PySpark 4.0.1; the existing native release Sail host and its hash are recorded
in each receipt. No performance claim is made.

Evidence: [source gate](evidence/iterative-sail/source-gate.json),
[gate log](evidence/iterative-sail/native-gate.log),
[relational receipt](evidence/iterative-sail/relational-receipt.json),
[iterative receipt](evidence/iterative-sail/iterative-receipt.json),
[memory probe](evidence/iterative-sail/memory-receipt.json), and
[development index](evidence/iterative-sail/development-index.json).

The first detached source gate caught a fixture error: adding chain vertices to
the original catalog changed an existing ANY-label result. The chain now lives
in a separate named graph. Its failed source receipt is retained, and the original
query expectations were not loosened.

## Reproduce the native qualification

From the repository root, with Rust and the qualified Spark Connect dependencies:

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/absolute/scratch/target \
  cargo run --release --manifest-path docs/reviews/grust-v2/wave-3/sketch/Cargo.toml \
  -p grust-query-qualification -- --iterative > /absolute/scratch/queries.json
python docs/reviews/grust-v2/wave-3/live/qualify.py \
  --sail /absolute/path/to/release/sail \
  --manifest /absolute/scratch/queries.json \
  --output /absolute/scratch/qualification
```

Omit `--iterative` to generate the relational regression manifest. The live runner
launches its own local Sail server and terminates only that server when finished.

## Cypher source integration

The [Cypher frontend follow-up](CYPHER-FRONTEND.md) now supplies source text to this
program adapter through the existing typed AST parser.
