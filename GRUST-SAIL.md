# Grust and Sail: every Sail-side change, and why

This document exists so that a Sail change made for Grust can be inspected
before it is proposed, by someone who did not write it. Every claim below names
a commit, a file, or a command, so that it can be checked rather than believed.
Where something is our convenience rather than a general improvement, it says
so; that distinction is the one a maintainer cares about most.

Read [the two integration paths](#the-two-integration-paths) first. Most
confusion about "what does Grust need from Sail" comes from not noticing that
there are two consumers with different needs, and that only one of them links
Sail at all.

Status as of 2026-09-21. Verify it rather than trust it:

```sh
cd ~/src/sail && git fetch origin
gh pr view 2374 --repo lakehq/sail --json state,title
gh pr view 2630 --repo lakehq/sail --json state,title,mergeCommit
gh pr view 2136 --repo lakehq/sail --json state,title,closedAt
```

## The two integration paths

Grust reaches Sail two ways, and they are not variations of one thing. They
share no code and they need different things from Sail.

**Path 1 — `grust-sail`, a Spark Connect client.** It links **no Sail crate**.
It speaks the Spark Connect gRPC protocol over `tonic`/`prost` and reads Arrow
IPC, exactly as PySpark does. Confirm with:

```sh
grep -c '^sail' crates/grust-sail/Cargo.toml      # 0
grep -rn 'sail_[a-z_]*::' crates/grust-sail/src/  # no sail crate paths
```

Crucially, **`grust-sail` compiles Cypher itself.** `grust-cypher` lowers a
Cypher statement to ordinary Spark SQL — `CREATE TABLE … USING delta`,
`MERGE INTO …`, `SELECT …` — and `grust-sail` sends that SQL. The `MATCH (…)`
strings in `crates/grust-sail/src/text_rows.rs` are *inputs* to our compiler,
not statements sent to Sail. Therefore this path needs **no graph or Cypher
feature in Sail**. What it needs is that Sail's ordinary SQL surface is correct,
which is why the one change it required was a Delta MERGE bug fix.

**Path 2 — Nutmeg, an embedder.** `nutmeg-sail` and `nutmeg-server` link Sail as
a library and run a Spark Connect server in-process with a Grust data source and
table functions registered in every session. This path needs Sail's session
extension point to be reachable, and nothing else.

**Nutmeg vendors no Sail code.** It imports only public items:
`sail_common_datafusion::datasource::{DataSource, DataSourceRegistry, …}`,
`sail_session::session_factory::{ServerSessionFactory, ServerSessionMutator, …}`,
`sail_common::config::AppConfig`, `sail_common::runtime::{RuntimeHandle, …}`,
`sail_telemetry`, and from `sail-spark-connect` exactly two items, both added by
the change in §2. Check with `grep -rn 'sail_' ~/src/nutmeg/crates/*/src/`.

## Status of every Sail change associated with Grust

| # | Change | Path | Sail PR | State | Size |
| --- | --- | --- | --- | --- | --- |
| 1 | Delta MERGE constraints by visible names | 1 (`grust-sail`) | [#2374](https://github.com/lakehq/sail/pull/2374) | **merged** | 2 files, +67/−4 |
| 2 | Embedder chooses the session factory | 2 (Nutmeg) | [#2630](https://github.com/lakehq/sail/pull/2630) | **merged** `e976c8b31` | 3 files, +60/−10 |
| 3 | Cypher graph query extension | neither | [#2136](https://github.com/lakehq/sail/pull/2136) | **closed by us** | 20 files, ~+5,600 |
| 4 | Table functions in Spark SQL | 2 (Nutmeg) | none | **not needed** | none |
| 5 | Object-store cache and Iceberg/SQL performance | neither | [#2400](https://github.com/lakehq/sail/pull/2400) | open | large |

**Only changes 1 and 2 were ever required by Grust, and both are merged.** As of
today, a Grust or Nutmeg user needs nothing out-of-tree in Sail. That is the
single most important fact in this document, and it is worth re-checking before
any new PR is written, because it sets the bar: the next Sail change must
justify itself from zero, not as one more in a series.

---

## 1. Delta MERGE constraints resolved by visible names — merged

**Sail PR:** [#2374](https://github.com/lakehq/sail/pull/2374), commit
`d97f7e595`. **Files:** `crates/sail-plan/src/resolver/command/delta.rs`
(+17/−4) and a new behaviour test,
`python/pysail/tests/spark/delta/features/check_constraints.feature` (+54).
Note where that test lives: it is a **Python-side** feature file, exercising the
fix through Sail's own PySpark suite rather than through a Rust unit test. That
is the shape Sail's maintainers prefer, and it is worth copying.

**What it does.** When resolving `MERGE INTO` against a Delta table, Sail built
the table's check constraints from `target_schema` directly. Inside a MERGE, the
target schema's fields carry **opaque internal field IDs**, not the names the
user wrote. Constraint source text and diagnostics therefore referred to opaque
identifiers. The fix resolves the field names first
(`Self::get_field_names(target_schema, state)?`), rebuilds the field list with
those user-facing names, and passes that to
`delta_constraints_from_schema_and_properties`.

```rust
// MERGE target schemas use opaque field IDs internally. Constraint source text and
// diagnostics must use the corresponding user-facing names; resolving that source text
// against `target_schema` maps it back to the opaque field safely.
let target_field_names = Self::get_field_names(target_schema, state)?;
let target_fields = target_schema
    .fields()
    .iter()
    .zip(target_field_names)
    .map(|(field, name)| field.as_ref().clone().with_name(name))
    .collect::<Vec<_>>();
```

**Why Grust needed it.** `grust-sail` writes every node and edge table through
`MERGE INTO` — see `crates/grust-sail/src/tests.rs` for the exact statements it
emits against `grust_node_*`, `grust_edge_*` and
`grust_cypher_constraint_registry`. A Delta table carrying a check constraint
could not be merged into correctly.

**Why it was a good PR to send.** It is a **bug fix in Sail's own SQL surface**,
reproducible without Grust, with a feature-file test that states the behaviour
independently of us. Nothing about it is Grust-shaped. This is the ideal form of
a Sail change made for Grust: we found it because of our workload, but the
defect and the fix belong to Sail. That framing is why it needed no advocacy.

---

## 2. The embedder chooses the session factory — merged

**Sail PR:** [#2630](https://github.com/lakehq/sail/pull/2630), our commit
`991d50ca1`, merged as `e976c8b31` on 2026-09-21T08:53Z and now in
`origin/main`. **Files:** `crates/sail-spark-connect/src/{lib.rs,
session_manager.rs, entrypoint.rs}`, +60/−10, no new dependencies.

**The problem it solved.** `sail-session` already had the extension point:
`ServerSessionMutator`, `ServerSessionFactory::new(config, runtime, mutator)`
and `create_session_manager(…, session_factory_fn, …)` were all public, and
`ServerSessionFactoryFn` was already a public type
(`crates/sail-session/src/session_manager/mod.rs:23`). What was missing was
**reach from `sail-spark-connect`**: `session_manager` was a private module, so
`SparkSessionMutator` could not be named from outside; it had no constructor; and
`entrypoint::serve` always installed Sail's own factory with no parameter for
another. An embedder therefore had to fork the crate, vendor `serve`, or
reimplement the Spark mutator.

**The four changes, exactly.**

1. `mod session_manager;` → `pub mod session_manager;` (`lib.rs`). This is the
   **only non-additive change in the whole diff**.
2. `SparkSessionMutator::new(config)` added, and the existing construction
   rewritten to use it.
3. `create_spark_session_factory` made `pub` — previously private — so an
   embedder composes with Sail's factory instead of reconstructing it.
4. Two new functions taking a `ServerSessionFactoryFn`:
   `session_manager::create_spark_session_manager_with_factory` and
   `entrypoint::serve_with_session_factory`.

**The compatibility argument, which is the part worth understanding.** `serve`
and `create_spark_session_manager` were kept and now **delegate** to the new
functions with `create_spark_session_factory` supplied:

```rust
pub async fn serve<F>(listener, signal, config, runtime) -> Result<…> {
    serve_with_session_factory(listener, signal, config, runtime,
                               create_spark_session_factory).await
}
```

So Sail's own binary takes the new code path with the default argument. The old
and new behaviour are identical **by construction**, not by inspection — there
is no second implementation that could drift. That property is what makes the
change reviewable in a few minutes, and it is worth preserving in any similar
PR.

**Note the real signature**, because an earlier draft of the PR description got
this wrong and it was caught in review:
`ServerSessionFactory::new(config, runtime, mutator)` takes **three** arguments.
The mutator trait's methods are `mutate_config`, `mutate_state` and
`mutate_runtime_env` — there is no `mutate_context`.

**How Nutmeg uses it** (`~/src/nutmeg/crates/nutmeg-server/src/main.rs:16-17`,
`~/src/nutmeg/crates/nutmeg-sail/src/lib.rs:219`): `NutmegSessionMutator` wraps
Sail's mutator rather than replacing it, so a session is a fully configured
Spark session first and gains our data source and table functions second. Nothing
Nutmeg registers is visible to a server that does not opt in.

**Evidence that shipped with it.** Sail's own Spark compatibility suite, run
against a release server built from the branch and one built from the base
commit `20f4de4f`: identical in every suite including *which* tests fail —
`test-connect` 106/896, `doctest-functions` 13/387, `doctest-dataframe` 14/83,
`doctest-catalog` 10/14, `doctest-column` 0/33. The methodology, including a
candid note that the first three runs were invalid because a leaked server
answered both suites, is in `~/src/nutmeg/docs/spark-suite/`.

### What the maintainer said, and what it means for the next PR

The maintainer merged this, and made two points that outlive it.

**On the description.** The PR body was ~6,400 characters for a 60-line refactor
— a problem statement, a worked embedder example, an alternatives section and a
motivation essay. His objection was not length for its own sake: *"I feel this
sets a bad example for the community. If this came from the community, I would
just reject it because this does not show thoughtfulness from the contributor,
but merely adds a burden for the maintainer."* The PR description is a permanent
public artifact that future contributors read to calibrate what a Sail PR should
look like. It was cut to ~1,300 characters: what changes, the compatibility
argument, the suite table, one sentence of motivation.

**On what Sail is.** *"Sail is not meant to be a Rust library that can be
consumed by others … we won't expect Sail to be a published crate so that they
can build Rust projects on top of it. Ideally all integration should happen on
the Python side."* He added that *"it's fine to have these small changes to
support your experiments."*

The line is precise and it is about **public framing, not permission**. Small,
individually justified hooks are acceptable. What is not acceptable is a PR that
argues the *general* embedding case and thereby advertises Sail as a crate to
build Rust projects on. The original description did exactly that — it said the
hook "is worth having independently of us — it is the general 'embed Sail's
Spark Connect server in my binary' case" — and that sentence was the one doing
the damage. It was removed.

**Practical rule for future PRs.** Justify each hook from the concrete need,
keep it small, and do not present it as the first of a pattern or as a general
extensibility story. Mention our use case in one sentence so the seam has a
recorded reason, and no more.

---

## 3. The Sail Cypher graph query extension — closed by us, not required

**Sail PR:** [#2136](https://github.com/lakehq/sail/pull/2136), closed
2026-06-26. **Size:** 20 files, ~5,600 insertions, adding `GRAPH`/Cypher syntax
to Sail's own parser, analyzer and planner —
`crates/sail-sql-parser/src/ast/graph.rs`,
`crates/sail-sql-analyzer/src/graph.rs`,
`crates/sail-plan/src/resolver/query/graph.rs`, new keywords, gold data, and
`python/pysail/tests/spark/test_graph.py`.

**It was closed by us, not rejected by a maintainer.** The closing comment is
ours: *"Closing — this work now lives on https://github.com/querygraph/sail
(branch `grust`), rebased onto current main."* Do not describe it as rejected.

**What review did surface** is still worth knowing: Codecov reported 16.46% patch
coverage with 137 uncovered lines, and overall project coverage −8.79%
(77.12% → 68.33%). `sail-sql-analyzer/src/graph.rs` was 0% covered. A change of
that size and that coverage is hard to land in anyone's repository.

**It is not required by anything Grust ships today.** Path 1 compiles Cypher to
SQL on our side; Path 2 calls registered procedures. This extension is a
*different design* — Cypher as a first-class Sail statement — not a dependency
of the current one. Treat it as a parked alternative.

**Where it lives, and a caution.** On `querygraph/sail` branch `grust`
(`c5309365`), which is 31 commits ahead of `origin/main` and **conflates two
unrelated programmes**: the graph extension (`21552e38 Add Sail Cypher graph
query extension` and its follow-ups) and the object-store/Iceberg performance
work (`9944bd3c` onward), joined by `72050f7c merge: align Grust Sail branch
with performance upstream`. If either is ever proposed upstream, it must be
separated first. Verify with:

```sh
cd ~/src/sail && git log --oneline origin/main..c53093654
```

---

## 4. Table functions in Spark SQL — investigated, not needed

Nutmeg registers one SQL table function per Grust algorithm
(`nutmeg_pagerank('g', '{"damping":0.85}')`, `nutmeg_graphs()`, …). These were
expected to need a Sail change. They do not: Sail's resolver already asks the
DataFusion session first — `self.ctx.table_function(&canonical_function_name)`
at `crates/sail-plan/src/resolver/query/read.rs:421` — so a function registered
through `mutate_state` resolves in Spark SQL with no Sail change at all.
Verified live; recorded in `~/src/nutmeg/docs/sail-prs.md` §B.

**This is the best outcome in the document**: a suspected requirement that
disappeared on inspection. Before drafting any Sail PR, spend the hour that this
one took.

---

## 5. Performance work — not a Grust requirement

`agent/grust-performance-alignment` (31 commits) and the related branches touch
`sail-object-store` (a Foyer-backed read-through cache, Sail issue #1015),
`sail-iceberg` metadata and delete-file paths, and single-statement SQL parsing.
Despite the branch name, **none of this is required by `grust-sail` or Nutmeg**.
It is Sail performance work that shares our branches for historical reasons. It
is listed here only so that nobody reads the branch name as a Grust dependency.
Its upstream vehicle is [#2400](https://github.com/lakehq/sail/pull/2400).

---

## 6. CSV `inferSchema` timestamps — a finding, not a Grust requirement

The Citi Bike showcase found that Sail's CSV `inferSchema` fails on timestamps
without four to six fractional digits. An open external PR, #2522, fixes most of
it. Nothing is required of Grust, and nothing has been filed. The full briefing,
with the verification table and draft comment, is
[`SAIL-2522-CSV-TIMESTAMPS.md`](SAIL-2522-CSV-TIMESTAMPS.md).

---

## 7. Cluster mode — why no Sail change is proposed

Nutmeg does not work in Sail's cluster modes. In `local-cluster`, staging fails
with `unsupported data sink node` and reads fail with `unsupported physical plan
node` or `no graph named ...`. Investigated at Sail main `51b57bc2`, 2026-09-22.
**The conclusion is to propose nothing to Sail.**

**Why a codec hook is the wrong fix.** Cluster mode serialises every stage through
`RemoteExecutionCodec`, which is hard-wired
(`sail-execution/src/driver/job_scheduler/mod.rs:37`), and places stages on workers
except for a hard-coded driver list (`job_graph/planner.rs:460-472`). Nutmeg's
staged graphs live in one process (`static STORE` in `nutmeg-graph`). On Kubernetes,
worker pods run the stock `sail worker` binary, which has no Nutmeg code and no
graph (`worker_manager/kubernetes.rs:380`). Letting an embedder serialise its nodes
would only move the failure from the codec to the worker. A correct Sail change
needs two seams: driver placement for an embedder's node, and a driver-side codec
for it. Sail pins its own commit nodes to the driver (#2192), but only from a fixed
list.

**The maintainer's stated direction.** Discussion
[#2001](https://github.com/lakehq/sail/discussions/2001), "Extension API for
third-party DataFusion integrations", is open with no design decided. From it:
"since DataFusion has an FFI, we won't use Rust trait as the API", and "The session
mutator is something not very stable and I'd consider it a deep implementation
detail." From #1991: "There is no plan to publish it as Rust crates for use in other
Rust projects." **#2630, which Nutmeg is built on, is therefore a hook the
maintainer regards as unstable.** Nutmeg's long-term path is the FFI extension API,
if and when it exists. Its requirements (driver placement, re-resolving on remote
workers) belong in #2001, not in a `feat:` PR.

**What works without Sail.** A Nutmeg-only change stages on the driver while the
write is planned (`create_physical_plan`, then `execute_stream`, then return an
empty plan). With it, staging, joined staging, listing and reads all succeed in
`local-cluster` on unmodified Sail, identical to local mode. Its trade-offs, in
cluster mode only: the write's input is computed on the driver, not distributed;
an `EXPLAIN` of such a write would execute it (inferred, not tested); materialised
read results travel inside the plan, so results above Sail's 128 MiB message limit
may fail (`sail-common/src/config/mod.rs:8`, inferred, not tested); and streaming
reads fall back to materialised ones.

---

## Checklist before proposing a new Sail change

Derived from what actually happened above, in the order that catches the most.

1. **Can it be avoided entirely?** §4 is the precedent: the requirement
   evaporated on inspection. Read the resolver before writing the hook.
2. **Which path needs it — client or embedder?** If Path 1, it is almost
   certainly an ordinary Sail bug or SQL gap, and should be filed as one, with a
   reproduction that never mentions Grust (§1).
3. **Is it a bug fix or a seam?** A bug fix carries itself. A seam needs to be
   small, additive, and default-preserving *by construction* (§2).
4. **Does the default path stay identical by construction?** If the old entry
   point does not delegate to the new one, rewrite it until it does.
5. **Is every new public item load-bearing today?** Nutmeg uses exactly two
   items from `sail-spark-connect`. Do not export a third in case.
6. **Write the description at the size of the change.** One paragraph, the
   compatibility argument, evidence. No alternatives essay, no worked tutorial,
   no general-case advocacy (§2).
7. **Bring before/after evidence from Sail's own suite**, with identical failure
   *sets*, not just identical counts — and make sure the harness is not talking
   to a leaked server.
8. **Do not frame Sail as a library for downstream Rust consumption**, in the
   PR, the commit message, or the docs that link to it.

## Keeping this document honest

It goes stale the moment Sail moves. Re-verify with the commands at the top, and
with:

```sh
cd ~/src/sail && git fetch origin
git merge-base --is-ancestor e976c8b31 origin/main && echo "hook is upstream"
git show origin/main:crates/sail-spark-connect/src/lib.rs | grep session_manager
grep -rn 'sail_' ~/src/nutmeg/crates/*/src/ | grep -v '^.*://'   # what we import
```

`~/src/nutmeg/SAIL_COMMIT` pins `20f4de4f…`, the base the compatibility suite was
run against. Now that #2630 is merged, Nutmeg can build against upstream `main`
and that pin exists only to identify the tested tree.
`~/src/nutmeg/docs/sail-pr-a-description.md` still says "(not sent)" and is
stale.
