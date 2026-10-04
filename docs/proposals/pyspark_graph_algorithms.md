# pyspark-graph-algorithms — project draft

Status: draft for discussion
Author: Semyon Sinchenko
Related projects (external, referenced as git projects, not vendored):

- GraphFrames (Scala, JVM): <https://github.com/graphframes/graphframes>
- graphframes-rs (Rust, DataFusion, single-node): <https://github.com/SemyonSinchenko/graphframes-rs>
- Sail (Spark Connect server on DataFusion): <https://github.com/querygraph/sail>

## 1. Motivation

The Spark Connect protocol is becoming a de-facto standard implemented by more than one engine:
Apache Spark (JVM), Sail (DataFusion, no JVM), Snowpark Connect, and likely others. Today the
algorithm code is locked to a specific server:

- **GraphFrames Connect** sends `GraphFramesAPI` extension messages that only the JVM plugin can
  execute. Any non-JVM engine would have to re-implement all algorithms server-side.
- **graphframes-rs** proves the algorithms work on DataFusion with a relational execution model,
  but it is a single-node library with its own CLI, not a Spark client experience.

The alternative is to invert the architecture: put **all graph logic into a pure PySpark client**
(ordinary `select/join/groupBy/agg/expr` operations) and require from any server only a small,
engine-specific "utils" pack. One client, many engines.

Pure PySpark alone is not enough, for two reasons:

1. **Staging ownership needs server-side filesystem access.** The execution model materializes
   every iteration to Parquet. Writing is a public DataFrame API, but *cleanup and listing are not*:
   the paths live in stores that only the server is configured to reach (credentials, Hadoop FS,
   object-store registry). A client cannot list or delete intermediate stage files — and unbounded
   staging is not acceptable for iterative algorithms. We need a small FS API executed on the server
   (`ls`, `rm`, `mkdir`, `exists`) scoped to configured roots. We deliberately do not use
   `cache()`/`persist()` (no-op or undesired on some engines) or the Spark `checkpoint()` API
   (engine-specific, session-bound ownership, no portable cleanup from the client).

2. **Hot-loop functions must be registered on the server.** Performance-critical functions
   (GF(2^64) affine hashing, HyperLogLog sketches, k-core merging, later: vector math and k-means)
   cannot be Python UDFs — row-at-a-time interpreter cost on billions of rows — and cannot be
   shipped portably at runtime: Scala functions are JVM artifacts, native functions are compiled
   per engine, and native *aggregates* have no runtime installation path on any engine. They must
   be deployed with the server under **known, stable names**.

Everything else — Pregel-style iteration, convergence checks, sanity checks between stages,
label restoration — is plain PySpark code in the client.

## 2. Design

### 2.1 Execution model (same as graphframes-rs)

- Graph state is always two tables (vertices with unique `id`, edges with `src`/`dst`); no CSR.
- An algorithm is a client-side loop of ordinary PySpark operations.
- **Every stage is materialized to Parquet.** Stage path:
  `<root>/<run-uuid>/stage-<k>/`. The client writes with a known partition count
  (`df.repartition(n)`), reads back with `spark.read.parquet`, and runs sanity checks between
  stages: expected file count (from `n`), optional row-count and non-empty checks.
- The client owns the lifecycle: allocates the run directory (UUID), keeps only the last
  generation(s) of intermediate stages, deletes old ones via the FS API, and writes the final
  result to a caller-provided output path.
- No `cache()`/`persist()`, no RDD APIs, no JVM-specific plan construction.

### 2.2 The utils extension (protobuf contract)

A single zero-input relation extension with receipt rows. This shape works on the Spark Connect
relation-plugin SPI and on Sail's relation extension without needing a "command" plugin on either
engine. The client collects the receipt eagerly.

Scope: the utils pack is deliberately a dumb, generic internal tool — paths and bytes in and out,
no graph semantics. Algorithm logic and all result schemas live in the PySpark client; the plugin
knows nothing about graph columns.

`gf/utils/v1/utils.proto` (sketch; single source of truth in its own repo):

```proto
syntax = "proto3";
package gf.utils.v1;

message Request {
  oneof verb {
    Ping ping = 1;     // capability probe
    Exists exists = 2;
    Ls ls = 3;         // bounded listing
    Rm rm = 4;         // delete a prefix
    Mkdir mkdir = 5;   // allocate <root>/<uuid> staging dir
  }
}

message Ping { string client_version = 1; }
message Exists { string path = 1; }
message Ls { string path = 1; uint32 limit = 2; }
message Rm { string path = 1; }
message Mkdir { string root = 1; }

message Receipt {
  oneof result {
    Pong pong = 1;
    BoolResult exists = 2;
    CountResult rm = 3;
    PathResult mkdir = 4;
  }
}

// `Ls` is row-per-entry: the receipt DataFrame carries one LsEntry row per file.
message LsEntry { string path = 1; uint64 size = 2; }

message Pong { string server_version = 1; string engine = 2; repeated string capabilities = 3; }
message BoolResult { bool value = 1; }
message CountResult { uint64 count = 1; }
message PathResult { string path = 1; }
```

Security: the single allowed root is `spark.checkpoint.dir`. Every path is resolved against it,
and `rm`/`mkdir` refuse anything outside. If the config is not set, the plugin fast-fails with a
clear error at registration/Ping time — never lazily on the first FS verb. Both engines honor the
same config key, which keeps the client identical on Spark and Sail.

Capabilities: `Pong.capabilities` carries feature flags (`fs`, `axpb`, `hll`, `vector`, ...).
The client probes once per session and degrades gracefully where a capability is missing
(see fallbacks below) — this is where "JVM supports something Rust does not yet" is handled.

### 2.3 UDF / UDAF contract (known names)

Reference semantics: graphframes-rs implementations. All varying parameters are ordinary
arguments (never baked into a function instance), so names are static and deployable.

v0 set:

| Name | Kind | Signature | Notes |
|---|---|---|---|
| `gf_version()` | scalar | → string | pack version; presence means the pack is installed |
| `gf_axpb(a, x, b)` | scalar | BIGINT ×3 → BIGINT | GF(2^64) affine hash `a⊗x⊕b`, reduction poly `x^64+x^4+x^3+x+1` (IRRPOLY `0x1b`); bit-exact with graphframes-rs `finite_axpb` |
| HLL sketch ops | scalar + agg | binary sketches, `lgK` as argument | on engines that ship Spark's DataSketches builtins (`hll_sketch_agg`, `hll_union`, `hll_sketch_estimate`) the client uses those names directly; `gf_*` wrappers exist for the rest |

Later tiers: `gf_most_common`, `gf_kcore_merge` (label propagation / k-core), vector and k-means
pack (`gf_l2_norm`, `gf_l2_distance`, `gf_cosine_distance`, `gf_vec_sum` UDAF, `gf_fastrp_init`,
`gf_kmeans_assign` / `gf_kmeans_step`) — same rule: dimensions, centers and other parameters are
arguments.

Fallbacks (used when a capability is absent, so the client still works everywhere):
`gf_axpb` → prime-field SQL `(a * x + b) % p` with `p` chosen client-side;
HLL → engine builtins when available.

Deployment:
- **Spark**: one JAR on the Connect server. Relation plugin registered via
  `spark.connect.extensions.relation.classes`; UDF/UDAF pack registered via
  `spark.sql.extensions` (Hadoop FS API for the verbs).
- **Sail**: one native wheel (entry point `pysail.extensions`, relation handler + scalar
  functions; aggregates via the Sail-side extension API as it matures) or, later, a compiled-in
  crate. ObjectStore access through the engine's own object-store registry.

### 2.4 What the client relies on

Common PySpark APIs for all graph logic; the extension only for FS verbs, capabilities and
function registration. Nothing else. In particular the client does not depend on
`spark.sparkContext`, Hadoop classes, or any engine-specific plan construction.

## 3. Comparison vs alternatives

### 3.1 vs local graph toolkits (Nutmeg / Grust / NetworkIt and similar)

Tools like NetworkIt — and engine-embedded native libraries in the Nutmeg/Grust style — share one
architecture: bring the graph into a local, in-process representation (CSR adjacency, Arrow
arrays), run a specialized kernel in one process, and convert results back to tables. That is the
price of the "multi-backend" flexibility of such toolkits:

- **heavy conversion on every use**: tables → local graph → tables is a full extra copy of the
  dataset, often the dominant cost, and it caps the graph at the size of one process;
- **single-process algorithms**: kernels run locally (in engine-integrated variants — on the
  driver, with inputs gathered to it), so there is no horizontal scaling for the algorithm itself;
- **split memory**: the graph exists twice — engine tables plus a local representation — with a
  separate memory budget instead of the engine's pool, spill and disk management.

graphframes-rs sits in this family too (single-node, out-of-core): this project reuses its
algorithm semantics but not its execution model.

The proposal instead runs the work **inside the engine** — Spark, Sail, Snowflake, or any Spark
Connect implementation — as pure relational operations issued by the client:

- horizontal scalability comes from the engine's distributed execution (stages, shuffles, spill);
- one copy of the data and one memory domain: everything stays engine tables end-to-end;
- no conversions: each iteration's output tables are the next iteration's input;
- one client implementation for all engines; only the thin utils pack is per-engine.

Trade-off acknowledged: specialized local kernels can beat shuffle-per-iteration execution on
graphs that fit one machine. This project accepts that price in exchange for scalability, engine
portability and no duplicated data model. This is an architectural comparison, not a benchmark
(see Non-goals).

### 3.2 vs Spark GraphFrames

- **Engine lock-in**: SGF is Spark-only, and its Connect client requires the JVM GraphFrames
  plugin on the server — it cannot run on Sail, Snowpark Connect, or any future Spark Connect
  implementation. The same algorithm logic does not actually require Spark: expressed as plain
  relational iterations it runs on any engine, which is exactly what this project does.
- **Execution model**: SGF executes algorithms eagerly *inside* the server plugin — one opaque
  operation per algorithm call. Here the loop is visible to the user: every iteration is an
  ordinary, observable, cancellable Spark Connect request, and intermediate state is explicit
  Parquet in a run directory the user owns.
- **Resource profile**: the classic SGF stack (GraphX-style Pregel over RDD lineage, in-memory
  caching plus checkpointing to truncate it) is known to be shuffle- and memory-heavy. The same
  algorithms can be written as lean relational iterations — graphframes-rs demonstrates this on
  DataFusion (e.g. WCC via randomized contraction with GF(2^64) hashing) — and that logic is what
  this client ports.
- **API**: the client targets a GraphFrames-compatible surface (vertex/edge frame conventions,
  `id`/`src`/`dst`, algorithm names and options), so migration is mechanical — but the result is
  engine-agnostic and observable, which SGF cannot offer by construction.

## 4. Proposed repo structure

Four git projects. `gf-proto` is language-neutral and is the contract; the two `gf-utils-*`
projects and the client depend on it. GraphFrames and graphframes-rs are referenced as external
git projects (links above) — as semantic references, not submodules or subfolders.

```
gf-proto/                          # contracts only, no implementation
  proto/gf/utils/v1/utils.proto    # the extension wire contract
  FUNCTIONS.md                     # UDF/UDAF names, signatures, semantics, fallbacks
  buf.yaml / buf.gen.yaml          # codegen for the python and rust consumers
  README.md

gf-utils-sail/                     # Rust implementation for Sail / DataFusion
  Cargo.toml, Cargo.lock
  gf-utils/                        # crate: proto verbs over ObjectStore + UDF/UDAF pack
    src/fs.rs
    src/functions/                 # gf_axpb, (later) vector & k-means, aggregates
  py/                              # PyO3 wrapper: wheel, pysail.extensions entry point,
    pyproject.toml                 #   manifest, bind(), plan_relation -> receipt provider
  tests/                           # integration tests against a Sail server (local + cluster)
  justfile

gf-utils-spark/                    # Scala implementation for Apache Spark Connect
  build.sbt, project/
  src/main/protobuf/               # generated from gf-proto via an sbt plugin
  src/main/scala/org/graphframes/utils/
    UtilsRelationPlugin.scala      # relation plugin: verb dispatch, receipt DataFrame
    fs/HadoopFs.scala              # verbs via Hadoop FileSystem API
    functions/                     # Scala UDF/UDAF pack registered via spark.sql.extensions
  src/test/                        # integration tests against Spark Connect (local + cluster)

pyspark-graph-algorithms/          # the client library (the center of the project)
  pyproject.toml                   # uv-managed
  src/pyspark_graph_algorithms/
    client.py                      # session probe: engine detection, capabilities
    fs.py                          # FS verbs via the extension
    staging.py                     # run dirs (uuid), stage write/read, sanity checks
    functions.py                   # gf_* wrappers + portable fallbacks
    pregel.py                      # generic iteration loop
    algorithms/                    # pagerank.py, wcc.py, hyperanf.py, ...
  tests/                           # unit + engine matrix (spark local, sail local, cluster)
  examples/
  README.md
```

Dependency direction: `pyspark-graph-algorithms` → `gf-proto` (generated messages);
`gf-utils-sail` / `gf-utils-spark` → `gf-proto`. No cycles, no shared code between the two
server implementations.

## 5. Roadmap (draft)

- **M0**: `gf-proto` v0 (`Ping/Exists/Ls/Rm/Mkdir` + `FUNCTIONS.md` v0: `gf_version`, `gf_axpb`,
  fallback contract).
- **M1**: `gf-utils-sail` wheel; client runs PageRank + WCC (randomized contraction) on Sail with
  staging and sanity checks end-to-end.
- **M2**: `gf-utils-spark`; the same client tests pass against Spark Connect — the
  "same API, two engines" milestone.
- **M3**: cluster modes on both engines; HLL via engine builtins; cleanup/GC policies; docs.
- **Later**: vector/k-means pack; k-core and label-propagation UDFs; HyperANF.

## 6. Non-goals

- No server-side algorithm execution: the loop lives in the client.
- No drop-in compatibility with the GraphFrames Connect wire protocol (this is a new client API).
- No performance claims until M2/M3 benchmarks exist.

## 7. Resolved decisions

1. **FS root policy**: everything inside `spark.checkpoint.dir` is allowed; paths outside are
   refused. Without `spark.checkpoint.dir` configured, the plugin fast-fails.
2. **`Ls` receipt shape**: row-per-entry (one `LsEntry` row per file).
3. **Client baseline**: Spark Connect protocol 4.x only.
4. **Result schemas**: not part of `gf-proto`. Column names and types of algorithm outputs are
   owned by the PySpark client loop; the plugin knows nothing about them.
5. **Codegen**: `buf` for the Python and Rust consumers; an sbt plugin for the JVM side.

Overall: the utils pack stays a dumb, generic internal tool — FS verbs, a capability probe and
function deployment. No graph semantics.
