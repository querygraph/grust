# A Sail extension API, tested against SedonaDB and Nutmeg

A design proposal for [lakehq/sail discussion #2001](https://github.com/lakehq/sail/discussions/2001).
Draft; not yet posted. Fifth revision, and the one that changes the load-bearing
structure rather than adding to it. The fourth revision was built on DataFusion FFI
objects reached through Sail's name resolver, with Spark Connect plugins deferred to a
late section as something "neither reference extension needs". Two research notes
written after it show that ordering was backwards: Spark Connect already defines the
extension seam, Delta and GraphFrames ship real products through it, and one of this
proposal's two reference extensions needs exactly that seam and nothing else. The FFI
question does not disappear — it moves. **The protocol decides how a request arrives;
the FFI decides what a native handler returns.** The fourth revision conflated them.

## 0. How to read the citations

Two research notes are the sources of record, cited rather than re-derived:
**[SCX]** `spark-connect-extensions.md` (2026-09-25) for the JVM mechanism, at Spark tag
`v4.0.0` (`fa33ea00`), Delta `master` `9856e968`, GraphFrames `main` `e4bf8ba7`, protobuf
`v32.0`; **[SCI]** `sail-connect-internals.md` (2026-09-25) for Sail, at `main`
`a3761b2e3ca7eb1d84db8adc479098e2a276e28b`, every claim with `file:line`.

Sail citations are at `a3761b2e` where [SCI] verified them, and its drift table is applied
throughout (`codec.rs:2889`→`2960`, `2517`→`2566`, `3690-3691`→`3756-3757`,
`2899-2921`→`2969-2990`, `1748-1767`→`1797-1849`,
`job_graph/planner.rs:460-472`/`606-617`→`:639-650` and `:370-385`,
`worker.rs:15-54`→`:34-53`, `server.rs:31`→`:33-38`, `planner.rs:540`→`:542`). Sail
citations neither note revisited are carried from the fourth revision at `main` `51b57bc2`
(2026-09-22) and marked **[51b]**. Non-Sail pins are unchanged: `datafusion-ffi` and
`datafusion-physical-plan` at the published 55.1.0 crates, SedonaDB `main` `a115fc3f`,
Apache Sedona `master` `86fbb82b`, Nutmeg `work/streaming-reads` `96816e5`,
datafusion-python `main` `516d20d`. Reasoning rather than something read says **inferred**.

## 1. The thesis, in one paragraph

Spark Connect carries three `google.protobuf.Any` extension fields — `Relation.extension`
(998), `Expression.extension` (999), `Command.extension` (999) — dispatched on the JVM
to plugins registered by class name ([SCX] §1, §2). Delta Lake and GraphFrames both
ship substantial functionality through that seam without patching Spark ([SCX] §3).
Sail rejects all three today, at `crates/sail-spark-connect/src/proto/plan.rs:1339`,
`crates/sail-spark-connect/src/server.rs:113` and
`crates/sail-spark-connect/src/proto/expression.rs:265` ([SCI] §1.1). Those three lines
are where a protocol-level extension dies; opening them is necessary and, on its own,
not close to sufficient ([SCI] §8 lists five more edits for local mode and four for
cluster mode, and §13 and §15 below take them). The organising insight is that **a
Connect extension carries new verbs, not functions**: a Connect client sends function
*names* in `UnresolvedFunction`, never an `Any` ([SCI] §8(c)), so scalar functions are
a name-resolution problem that can never be a Connect-extension feature, while "stage
this DataFrame as a graph" and "run this algorithm" are exactly what a relation
extension is for. That split runs through the whole document: **§2** is the
name-resolution path, which for scalars costs nothing; **§3–§9** are the protocol path;
**§10–§11** are what each reference extension actually needs; **§12–§15** are loading,
prerequisites, execution contracts and cluster mode; **§17** the increments.

## 2. Start here: a native scalar function needs no Sail change at all

The fourth revision opened with a resolver patch. It was reading the resolver one
lookup too shallow. [SCI] §4.3 and §5.2 establish the order:

1. Qualified names are refused before any lookup: `PlanError::unsupported("qualified
   function name")` at `crates/sail-plan/src/resolver/expression/function.rs:47-49`.
2. The name is lowercased (`function.rs:76`).
3. **`CatalogManager::get_function` is consulted first** —
   `crates/sail-catalog/src/manager/function.rs:24-28`, called from
   `resolver/expression/function.rs:116-119` — and a non-PySpark hit becomes
   `Expr::ScalarFunction(ScalarFunction { func: Arc::new(udf), args })`
   (`function.rs:151-154`).
4. Only then Sail's static built-in tables (`function.rs:159, 176`;
   `crates/sail-plan/src/function/mod.rs:27-44`).

`CatalogManager::register_function` takes a `ScalarUDF`
(`crates/sail-catalog/src/manager/function.rs:17-22`). So **a native `ScalarUDF`
registered into `CatalogManager` resolves by name, in SQL and in DataFrame
expressions, with zero changes to Sail** ([SCI] §8(c)). The fourth revision's
increment A proposed adding a *second* lookup into the DataFusion session `udf`
registry; that lookup is not needed for the scalar case, and increment A shrinks to a
registration plus a test.

Three honest qualifications, because "zero changes" is load-bearing and easy to
overstate:

- **It is an embedder path, not yet a package path.** The only way to hold
  `Arc<CatalogManager>` today is `ServerSessionMutator::mutate_config`
  (`crates/sail-session/src/session_factory/server.rs:40-45`, applied at `:133`) —
  which is exactly what C2 calls "a deep implementation detail". Reaching it from a
  *discovered package* rather than from compiled-in embedder code is what §12 is for.
- **Local mode only.** In cluster mode a UDF matching no `try_encode_udf` arm encodes
  as an empty buffer (`crates/sail-execution/src/proto/codec.rs:3756-3757`) and is then
  resolved by name from the *worker's* registry, which is `with_default_features()`
  only (`crates/sail-session/src/session_factory/worker.rs:45-50`), so decode fails with
  `could not find scalar function: …` (`codec.rs:3437`) ([SCI] §8(c)). §15.
- **Scalars only, unqualified only, no modifiers.** `DISTINCT`, `FILTER`, `IGNORE
  NULLS` and `ORDER BY` are refused for a catalog function (`function.rs:120-122`) and
  `is_distinct` is dropped (`:151-154`); aggregates and window functions have **no**
  native-UDF route (`:176`, and `resolver/expression/window.rs` admits only PySpark
  window UDFs) ([SCI] §5.3). Namespacing is impossible (`function.rs:47-49`).

So the resolver work this proposal still asks for is narrower than the fourth
revision's: **aggregate and window construction**, not scalar lookup. An
`Expr::AggregateFunction` built with the `AggFunctionInput { distinct, ignore_nulls,
filter, order_by, .. }` modifiers the aggregate path carries **[51b]**
(`resolver/expression/function.rs:177, 212-229`), and a
`WindowFunctionDefinition::WindowUDF` construction in `resolver/expression/window.rs`
**[51b]** (`:31-148`, PySpark-only admission at `:106-119`). The precedence matrix
in §2.1 governs all three paths.

### 2.1 Precedence, unchanged from the fourth revision

Enforced at registration and at resolution: Spark built-ins first; then Spark
user-defined functions registered through the catalog, so their existing precedence is
unchanged; then extension functions, in extension load order. An extension shadows a
built-in only under a session opt-in (`sail.extensions.override`), and the built-in
stays reachable under a qualified name — which requires lifting `function.rs:47-49`,
so in v1 the opt-in shadows without an escape hatch and says so. Two extensions
registering one name is a load error. Names are matched after Spark's case
normalisation; aliases register as names. Workers reconstruct the implementation the
driver chose, identified by the task descriptor of §14.3, not merely one with the
same name.

## 3. The protocol seam, and the three lines that close it

### 3.1 What the protocol offers

From [SCX] §1, at Spark `v4.0.0`:

| Message | Spark's file | Field | Sail's vendored line ([SCI] §1.1) |
| --- | --- | --- | --- |
| `Relation` | `sql/connect/common/.../relations.proto:107` | `Any extension = 998` | `relations.proto:110` |
| `Expression` | `.../expressions.proto:59` | `Any extension = 999` | `expressions.proto:60` |
| `Command` | `.../commands.proto:57` | `Any extension = 999` | `commands.proto:59` |

Spark's own comment, `relations.proto:105-107`: "This field is used to mark extensions
to the protocol. When plugins generate arbitrary relations they can add them here.
During the planning the correct resolution is done." `Relation` uses 998 because 999 is
taken by the `Unknown` placeholder ([SCX] §1). `Plan` itself carries no extension
field, so extending the protocol always means extending a `Relation`, an `Expression`
or a `Command` ([SCX] §1, `base.proto:38-43`).

The type-URL contract is protobuf's, not Spark's: `Any.pack` yields
`type.googleapis.com/<proto package>.<Message>` ([SCX] §1, `google/protobuf/any.proto:129-158`).

### 3.2 That this is a real product surface, not a hook nobody uses

**Delta Lake** ships `delta-connect-common`, `-client` and `-server`
(`build.sbt:182,209,267`), a `DeltaRelation` `oneof` envelope with ten operations
(`relations.proto:29-43`) and a `DeltaCommand` envelope with seven (`commands.proto:27-38`),
and two plugin classes named in static server conf ([SCX] §3.1). **GraphFrames** ships one
25-line `RelationPlugin` over a single `GraphFramesAPI` envelope with 25 methods
(`graphframes.proto:11-46`) and a PySpark client that switches implementation on
`is_remote()` (`graphframes/graphframe.py:175-178`), so `from graphframes import GraphFrame`
works in both worlds ([SCX] §3.2). Both return a Catalyst `LogicalPlan` and let the rest of
the pipeline treat it as an ordinary relation, including `plan_id` tagging so the result
composes with client-side DataFrame operations (`SparkConnectPlanner.scala:236-240`).

### 3.3 Where Sail closes it

| Carrier | Rejection site | Verbatim ([SCI] §1.1) |
| --- | --- | --- |
| `Relation.extension` | `sail-spark-connect/src/proto/plan.rs:1339` | `RelType::Extension(_) => Err(SparkError::unsupported("extension relation")),` |
| `Command.extension` | `sail-spark-connect/src/server.rs:113` | `CommandType::Extension(_) => Err(SparkError::todo("command extension")),` |
| `Expression.extension` | `sail-spark-connect/src/proto/expression.rs:265` | `ExprType::Extension(_) => Err(SparkError::todo("extension expression")),` |

The relation rejection happens in proto→spec conversion, before a `spec::Plan` exists
and before any session is in scope: `server.rs:123` → `:143-145` → `:146-148` →
`plan_executor.rs:144,149` → `proto/plan.rs:100,107,174` → `:1339` ([SCI] §1.2). The
AnalyzePlan path dies at the same line ([SCI] §1.2). The client sees gRPC
`Code::Internal` with `reason = "java.lang.UnsupportedOperationException"` and the bare
message `extension relation` ([SCI] §1.3).

Two adjacent facts worth naming because they will surprise an extension author:

- **`UserContext.extensions` (`base.proto:76`) and `ExecutePlanRequest.RequestOption.extension`
  (`base.proto:356`) are silently discarded, not rejected** — every handler does
  `request.user_context.map(|u| u.user_id)` (`server.rs:130,171,254,…`) and
  `is_reattachable` matches only `ReattachOptions` (`server.rs:37-48`) ([SCI] §1.4). A
  handler must not expect per-request options to arrive there. The fourth revision
  omitted this.
- **Sail already generates the example plugin types and uses none of them**:
  `ExamplePluginRelation`/`Expression`/`Command` (`example_plugins.proto:30,35,40`,
  compiled at `build.rs:32`) are the only "plugin" artifacts in Sail's Rust sources
  today ([SCI] §1.4). `pipelines.proto`'s six `Any` fields are irrelevant — that file
  is not compiled (`build.rs:28-38`).

Also: `AddArtifacts`, Spark's own mechanism for shipping user code to a Connect server,
is a stub (`service/artifact_manager.rs:16,23`), so it is not an alternative
distribution route ([SCI] §9).

## 4. The constraints

All from the maintainers, quoted verbatim.

| | Constraint | Source |
| --- | --- | --- |
| C1 | "since DataFusion has an FFI, we won't use Rust trait as the API, but we'll have an extension FFI built on top of DataFusion so that we won't need to recompile the extension on every Sail version or Rust version change. This allows Sail and the extension to release under different schedule." | linhr, [#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083578) |
| C2 | "The session mutator is something not very stable and I'd consider it a deep implementation detail, so we need to think more around the best way to alter session config." | same |
| C3 | "Using Python package for distribution and the discovery mechanism make sense to me." | same |
| C4 | "I would love to see end-to-end proof of concept around FFI." | same |
| C5 | Open questions: "1. How do we handle breaking changes to the extension API? 2. How does this fit into Spark Connect's existing plugin mechanism? 3. How to specify optimizer and planner orders? (This is mentioned in the proposal already.)" | same |
| C6 | "The FFI extension would shine the most for *transformation* of existing query plans. For connecting with external data systems, since the query plan is the leaf node without input, I feel the Python data source is powerful and performant already, and it avoids the complexity of working with FFI. But the FFI extension can definitely be used to support data source if there are reasons for particular use cases." | linhr, [#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3573403774) |
| C7 | "There is no plan to publish it as Rust crates for use in other Rust projects." | linhr, [#1991](https://github.com/lakehq/sail/discussions/1991#discussioncomment-17062283) |
| C8 | Shared-library loading "does not seem mature. (I'm sure we'll need to deal with a lot of `unsafe` code.)"; a Python library "looks promising ... It allows sharing functionalities between native modules using `PyCapsule` as the bridge." | linhr, [#1062](https://github.com/lakehq/sail/issues/1062#issuecomment-3561587467) |

C5.2 is no longer answered by a deferral. This revision's answer is §3 through §9: the
Connect plugin mechanism is where an extension *arrives*, and the FFI is where its
handler's *result* comes from. §16 checks the design against every row, with the
strongest case that it fails. linhr's own placement of the work is where §7 puts it:
"I guess the extension would fit into this process, and the core logic to mimic
GraphFrames would be in the second step (plan resolver)"
([#2002](https://github.com/lakehq/sail/discussions/2002#discussioncomment-17083597)).

## 5. Decision 1: route on the type URL

**The JVM does not.** `transformRelationPlugin` hands every registered plugin the whole
serialized `Any` as `byte[]`, in configuration order, lazily, and takes the first
plugin returning a present `Optional`; the type-URL comparison happens *inside* each
plugin, as `Any.is(classOf[MyMessage])` in generated protobuf code
(`SparkConnectPlanner.scala:245-254`, and the same shape at `:1667-1675` and
`:2859-2867`) ([SCX] §2.4). Dispatch is therefore decentralised and O(number of
plugins), and an unclaimed message produces
`throw InvalidPlanInput("No handler found for extension")` — the same string for all
three kinds, **with no type URL in it**. That is Sem Sinchenko's chief complaint,
verbatim ([SCX] §4): "you might get something like `org.apache.spark.sql.connect.common.InvalidPlanInput:
No handler found for extension` and it is not at all obvious what the reason is and on
which message it happened. Is the problem in the Java plugin implementation? Or maybe
there is a problem in the Python serialization? Or is it just a missing plugin class in
CP?"

**Proposed for Sail:** a `type_url → handler` map, one entry per claimed URL, held in a
`ConnectExtensionRegistry` session extension ([SCI] §8(a).1). Registration of a URL
already claimed is a load error, not a silent shadow. An unclaimed URL produces a
structured error naming the URL that arrived and the URLs that are registered.

**Why this is better.** Dispatch is O(1) and order-independent, so two extensions cannot
become order-dependent on each other; the "must return `Optional.empty()` only when the
message is not mine" contract — which Sinchenko has to state in capitals because Spark's
javadoc does not ([SCX] §4) — disappears, because a handler is never offered a message it
did not claim, and cannot claim another's by parsing loosely; and the registry is
introspectable, which is what makes the error message possible. This is [SCX]'s own
recommendation for a fresh implementation.

**What it costs.** Three things, and they are real:

1. A handler cannot claim a *family* of URLs, so a library versioning its envelope by
   proto package (`mylib.v1.Api`, `mylib.v2.Api`) registers each. Prefix claims are not in
   v1 because they reintroduce ordering.
2. A JVM plugin's freedom to inspect the `Any` and decline for reasons other than its type
   — Delta's recursion-limit and `checkLastTagWas(0)` hardening when parsing
   (`DeltaRelationPlugin.scala:297-333`, [SCX] §3.1) — becomes Sail's job for the envelope
   and the handler's for its payload. Sail must apply its own recursion and size limits;
   the JVM's equivalent is an internal static conf (`Connect.scala:79-87`).
3. It is a behavioural divergence, so a client cannot rely on first-claimant-wins
   semantics. Nobody should want to, but it belongs in the docs.

## 6. Decision 2: a Sail envelope that makes nested plans first-class

### 6.1 The problem the JVM solves by convention

A real extension takes DataFrames as parameters, and every real extension solves that the
same way: **it carries its inputs as serialized `spark.connect.Plan` bytes inside its own
message and makes the server re-enter the host planner.** GraphFrames' `GraphFramesAPI` has
`bytes vertices = 1; bytes edges = 2;` (`graphframes.proto:11-46`); the client does
`plan.to_proto(client).SerializeToString()` (`python/graphframes/connect/utils.py:19-23`);
the server does `planner.transformRelation(Plan.parseFrom(data.toByteArray).getRoot)`
(`GraphFramesConnectUtils.scala:109-120`), and columns cross the same way,
`planner.transformExpression(Expression.parseFrom(...))` (`:63-75`) ([SCX] §3.2).
Sinchenko's Deequ port does the identical thing with `optional bytes data = 1`, for a
shading reason rather than an aesthetic one: Spark's protos are relocated to
`org.sparkproject.proto`, so importing them into a plugin's proto produces uncompilable
generated code ([SCX] §4). [SCX] calls re-entrant planner access "load-bearing in both real
examples … Without it, extensions cannot take DataFrames or Columns as parameters — and
every real library does."

Two defects of the convention: every extension reinvents it, and the host cannot see the
inputs. For Sail the second is not cosmetic. The resolver returns `PlanResult<LogicalPlan>`
and carries a `&mut PlanResolverState` through every node ([SCI] §2.1), while the
proto→spec conversion at `proto/plan.rs:174` has **no session in scope** ([SCI] §8(a).3).
Nested plan bytes only a handler understands cannot be resolved by Sail, so the field-name
contract of §8, placement, and everything in §14 would apply to inputs Sail never saw.

### 6.2 The envelope

Sail defines one message, in Sail's own proto package, carried in the `Any`:

```protobuf
message SailExtensionRequest {
  // The type URL of the payload, used for handler dispatch (§5).
  string payload_type_url = 1;
  bytes payload = 2;
  // Inputs the host resolves before the handler runs.
  repeated spark.connect.Plan inputs = 3;
  // Expressions the host resolves before the handler runs, in the same spirit.
  repeated spark.connect.Expression input_expressions = 4;
  uint32 envelope_version = 5;
}
```

The resolver arm ([SCI] §8(a).4) resolves each `inputs[i]` through the ordinary
`resolve_query_plan` path with the live `PlanResolverState`, then calls the handler with
the payload and the already-resolved children. Sail therefore knows the inputs' schemas
and registered field names before the handler runs, and every contract in §14 applies
to them as it does to any Sail plan. `spec::QueryNode::Extension { payload_type_url,
payload, inputs: Vec<QueryPlan>, .. }` stays plain `Serialize + Deserialize + Clone +
PartialEq` data, as every sibling variant must be
(`crates/sail-common/src/spec/plan.rs:31-32`) ([SCI] §8(a).2).

**The trade, stated honestly.** This departs from the JVM's convention. An extension
written for Sail's envelope is **not byte-compatible with a JVM plugin**: the client
must build the envelope, and the same proto payload sent to a JVM Connect server would
arrive as an unclaimed `Any` whose type URL is Sail's. That is a fork in the ecosystem
at the client layer, and the only honest mitigation is that a library's thin client
layer — Delta's `plan.py`, GraphFrames' `graphframes_client.py` ([SCX] §4) — is already
where the packing lives, so the divergence is one method in the library, not in user
code. It is still a divergence.

### 6.3 Should a bare `Any` also be accepted?

**Yes, for handlers that declare no plan inputs, and only for those.** Dispatch becomes:
if the `Any`'s type URL is `SailExtensionRequest`, unwrap it, resolve the inputs, and
dispatch on `payload_type_url`; otherwise dispatch on the `Any`'s own type URL with no
inputs. This keeps a Delta-shaped extension whose parameters are paths, names and
scalars byte-compatible with its JVM counterpart at the message level.

**Why the bare path cannot carry plan inputs.** The GraphFrames trick needs a
re-entrant planner *inside the handler*. On the JVM that is free: the plugin is
driver-side JVM code holding a `SparkConnectPlanner`. For Sail, a native handler behind
the FFI would need `PlanResolver` and `&mut PlanResolverState` exported across the FFI
boundary. `PlanResolver` is `{ ctx: &'a SessionContext, config: Arc<PlanConfig> }`
(`crates/sail-plan/src/resolver/mod.rs:20-23`) ([SCI] §2.1) and is not a
`datafusion-ffi` object; exporting it would make Sail's plan resolver a public,
versioned C ABI, which is a much larger commitment than anything in §7 and squarely
against C7. So: bare `Any` for input-free verbs; the envelope when a verb takes a
DataFrame. A handler declares which mode it accepts at registration (§12), and a bare
`Any` sent to an envelope-only handler is refused by name.

A handler written in Python rather than Rust could hold the re-entrant planner, since
Python already crosses that boundary — but Sail has no Python plan-resolver surface
today and this proposal does not invent one.

## 7. Decision 3: what a handler returns across the FFI boundary

### 7.1 The type Sail needs

[SCI] §2.2 settles it: "the exact Rust type a plugin's relation handler would have to
return is `datafusion::logical_expr::LogicalPlan`", and in practice either
`LogicalPlan::Extension(Extension { node: Arc<dyn UserDefinedLogicalNode> })` or a
`LogicalPlan::TableScan` over an `Arc<dyn TableProvider>`. The model to copy is
`RangeNode` (`crates/sail-plan/src/resolver/query/misc.rs:30-53`), the closest thing
Sail has to a plugin-shaped leaf relation.

And `LogicalPlan` does not cross `datafusion-ffi`: neither `LogicalPlan::Extension`
nodes nor logical optimizer/analyzer rules are carried
(`datafusion-ffi` 55.1.0 `src/proto/logical_extension_codec.rs:382,386`) **[51b]**, and
there is no `LogicalExtensionCodec` anywhere in Sail (grep: zero hits, [SCI] §7.1).

### 7.2 The ABI that follows

**A native relation handler returns an `FFI_TableProvider`, and Sail builds the
`TableScan`.** Inputs the envelope declared are handed to the provider as
already-planned children — `FFI_ExecutionPlan`s, or record-batch streams — so the
handler never re-enters Sail's planner. Nothing else in the v1 relation ABI.

This is the route [SCI] §2.2 identifies as "the only route that works today without
touching `sail-session`", because it needs no `ExtensionPlanner`; it is the shape Sail's
own `DataSource`/`DataSourceRegistry` path already uses
(`crates/sail-plan/src/resolver/query/read.rs:139,487`). §13 is what it costs to *also*
allow the `LogicalPlan::Extension` route, and the answer is: more than the fourth
revision said.

### 7.3 Is that sufficient for the two use cases?

**Nutmeg: yes, for its v1 verbs.** "Stage this DataFrame as a graph" is an envelope with
one input and a provider whose `insert_into(session, input, InsertOp)` performs the
staging (`datafusion-ffi` 55.1.0 `src/table_provider.rs:131-135`) **[51b]**. "Run
pagerank on graph g" is an input-free provider whose `scan` streams the kernel's output.
Both are leaf-shaped in Sail's plan.

**SedonaDB: no, and that is the point.** A spatial join is a *transformation* of a join
Sail planned. It is not leaf-shaped, it has two inputs Sail must keep placing and
shuffling, and no `TableScan` can express it. That is precisely why it goes through
§11's join hook rather than the protocol, and why the two mechanisms partition cleanly
by shape: **the Connect envelope admits new leaf-shaped verbs; the join hook admits one
named plan transformation.** C6 says the FFI "would shine the most for *transformation*
of existing query plans" — §11 is that case; §7 is the case C6 is sceptical of, and §16
says so.

### 7.4 What the `FFI_TableProvider` ABI cannot express

Named rather than discovered later:

- **Any verb with several inputs whose shape Sail must see.** A join-, union- or
  set-shaped extension collapses into an opaque leaf, so Sail's optimizer, its
  stage-boundary cut (`job_graph/planner.rs:370-385`) and its placement walk see one
  scan. Sedona's spatial join is the example, and §11 exists because of it.
- **Driver placement.** The scan exec a provider produces is not one of the six types
  in `is_driver_stage_plan` (`crates/sail-execution/src/job_graph/planner.rs:639-650`:
  `SystemTableExec | CatalogCommandExec | FileDeleteExec | DeltaCommitExec |
  IcebergCommitExec | RemoteCheckpointCommitExec`) ([SCI] §7.4), so **a plugin node
  cannot opt into driver placement**, and Nutmeg's residency needs that list opened
  whatever the handler returns. §15.
- **Cluster mode at all**, until §15: the exec hits `codec.rs:2960` on encode.
- **Sail's sink semantics.** `datafusion-ffi` carries no `DataSink` **[51b]**, and
  `DataSinkExec` requires a single input partition and executes only partition 0
  (`datafusion-datasource-55.1.0/src/sink.rs:277-287, 344-348`) **[51b]** — a
  requirement that is invisible across the FFI, so Sail must coalesce before any foreign
  `insert_into` (§14.4).
- **Input requirements and ordering.** `ForeignExecutionPlan` does not forward
  `required_input_distribution`, `required_input_ordering` or
  `input_distribution_requirements()` (`datafusion-ffi` `src/execution_plan.rs:451-556`
  against `datafusion-physical-plan` 55.1.0 `src/execution_plan.rs:194-221`) **[51b]**,
  and `FFI_PlanProperties` carries output properties only, rebuilding equivalences from
  orderings (`src/plan_properties.rs:160-190`) **[51b]**. §14.4.
- **Anything a Sail logical rule must see.** Two logical rewriters run before physical
  planning, hardcoded (`crates/sail-session/src/planner.rs:92-95`,
  `DeltaMetadataAggregateRewriter`, `IcebergMetadataAggregateRewriter`) ([SCI] §2.2(e));
  a foreign logical node cannot participate because logical nodes do not cross.
- **Multiple outputs.** A relation returns one relation. GraphFrames' PageRank returns
  only vertices and the client rebuilds weighted edges with plain joins
  (`graphframes_client.py:921-938`) ([SCX] §3.2, §5.5). Any Nutmeg algorithm returning
  both vertex and edge results must split into two calls or stitch client-side; this is
  a protocol property, not a Sail limitation.
- **Panics.** No `catch_unwind` anywhere in `datafusion-ffi`; a panic across
  `extern "C"` aborts the process **[51b]**. Extensions catch their own.

## 8. Decision 4: the output-field-names contract

The fourth revision missed this entirely, and [SCI] §2.2(c) calls it out as "a hard
contract our proposal does not mention anywhere". It is part of the handler contract,
not a footnote.

Sail renames every output column to an opaque internal id during resolution and
recovers the user-facing names at the end:

- `PlanResolverState` — `crates/sail-plan/src/resolver/state.rs`, `FieldInfo { plan_ids,
  name, hidden }` at `:14-24`;
- `register_field_name` (`state.rs:141-143`), `register_field` (`:159-161`),
  `register_fields` (`:164-172`), `register_field_names` (`:175-181`),
  `register_hidden_field_name` (`:148`);
- the user-facing schema comes from `Self::get_field_names(plan.schema(), &state)?` in
  `resolve_named_plan` (`crates/sail-plan/src/resolver/plan.rs:24`), which is what
  `fields: Some(..)` in `NamedPlan` carries and what `rename_physical_plan` applies at
  the end (`crates/sail-plan/src/lib.rs:56-58`).

**A handler that skips registration produces a plan whose names are wrong or whose
`get_field_names` lookup fails.** So the contract is:

1. A handler declares its output schema *before* returning a provider, as field names
   in declaration order.
2. The Sail-side resolver arm registers them with `register_fields`/`register_field_names`,
   exactly as `resolve_query_range` does (`crates/sail-plan/src/resolver/query/misc.rs:49-52`),
   and builds the `TableScan` against the renamed schema.
3. Sail validates that the provider's actual schema has the same arity and types as the
   declared names, and refuses the plan by name if it does not. Doing this in Sail
   rather than trusting the handler is the whole point: a foreign handler has no way to
   learn Sail's internal id scheme, and should not.
4. Hidden fields are registrable (`state.rs:148`) but not in v1: a v1 handler declares
   only visible outputs.

This also settles a smaller question: the handler is called from the resolver arm, which
has `&mut PlanResolverState`, not from the proto conversion, which has no session ([SCI]
§8(a).3). Field registration is why the seam has to be there and not earlier.

## 9. Decision 5: commands — Sail is not constrained the way the JVM is

On the JVM, `CommandPlugin.process` returns `boolean`, `handleCommandPlugin` returns
`Unit` and only posts `postFinished()`, and the planner never populates
`ExecutePlanResponse.extension` (no `setExtension` occurrences in
`SparkConnectPlanner.scala`) ([SCX] §2.4, §5.4). **A JVM command plugin cannot return
data at all.** That is why Delta's protos carry the same comment five times, verbatim
(`delta/connect/relations.proto:84-86, 106-108, 118-121, 135-137, 207-211`):
`// Needs to be a Relation, as it returns a row containing the execution metrics.`

**Sail is not constrained this way, and this proposal should say so loudly.** From
[SCI] §3:

- Commands in Sail are logical plans, not side-effecting callbacks: each handler builds
  `spec::Plan::Command(CommandPlan::new(CommandNode::X))` and calls the same
  `handle_execute_plan` as a query (`plan_executor.rs:113-142`) with
  `ExecutorMode::command()` (`crates/sail-spark-connect/src/executor.rs:141-160`);
  `resolve_command_plan` returns `LogicalPlan` (`resolver/plan.rs:26-30`), as
  `CatalogCommandNode` → `CatalogCommandExec` shows
  (`crates/sail-session/src/planner.rs:526-528`).
- **`handle_execute_sql_command` already returns relations**
  (`plan_executor.rs:211,238-249`): for a command plan it installs a completion handler
  (`ExecutorMode::command_with_completion`, `executor.rs:158`) that concatenates the
  output batches and wraps them as a `Relation` with `RelType::LocalRelation` inside
  `ExecutorBatch::SqlCommandResult`; for a query plan it returns the original relation
  and the client reads it in a second request (`:252-258`).

So Sail can give a command plugin either an empty success stream (the shape of
`handle_execute_register_datasource`, `plan_executor.rs:648-708`) or rows, via the
`SqlCommand` trick or a new `ExecutorBatch` variant (`executor.rs:31-38`) with a matching
`ExecutePlanResponse` arm (`plan_executor.rs:71-99`) ([SCI] §8(b).3).

**Decision: Nutmeg's staging is a relation, not a command**, for three reasons in order of
weight. Staging **takes a DataFrame**, so a relation with the §6 envelope gets its input
resolved by Sail and its output covered by §8, while a command would need the same envelope
and the same resolution, leaving only the result shape different. Its **result is data** —
a graph identity and row counts, exactly the case Delta's five comments describe — and a
relation delivers that with no new `ExecutorBatch` variant, no new response arm, and
`plan_id` composability for free. And it is **portable**: a relation-shaped verb is what a
JVM implementation of the same library would have to do, so the client's shape survives if
anyone writes one.

Where Sail's freedom should still be used: **Sail should populate
`ExecutePlanResponse.extension`** (`base.proto:403`, which the JVM never fills — [SCX]
§5.4) for a command extension's structured result, rather than adding an `ExecutorBatch`
variant, so the divergence lives in a field the protocol already defines — [SCX] calls this
"a deliberate divergence decision, not a gap". v1 does not need it, since no reference
extension needs a command, so it is specified and not built, and `server.rs:113` is opened
with the empty-success shape only.

## 10. What each reference extension needs

### 10.1 The two, and where they pull apart

| | SedonaDB | Nutmeg |
| --- | --- | --- |
| scalar functions by name | required — **§2, zero Sail change** | no |
| aggregate / window functions by name | required — resolver work (§2) | no |
| Connect relation extension | **not needed** | **required** (§6, §7) |
| plan transformation | required — §11 | no |
| table functions | nice | required (already resolved from the DataFusion session, `resolver/query/read.rs:421`, exact at `a3761b2e`) |
| where components run | **workers** | **driver only** |
| state | none | process-resident |
| mutation | none | append and overwrite, with a revision |

**SedonaDB** is 141 `ST_*` scalars, 7 `ST_*` aggregates and 58 `RS_*` as DataFusion UDFs
(`rust/sedona-expr/src/scalar_udf.rs:69`) **[51b]**, with scalars already exported over the
FFI as `__datafusion_scalar_udf__` (`python/sedonadb/src/udf.rs:83`) **[51b]**; a spatial
join built from four logical rules, a `UserDefinedLogicalNode`, an `ExtensionPlanner` and
`SpatialJoinExec` (`rust/sedona-spatial-join/src/exec.rs:361`) **[51b]**; `SedonaOptions`, a
`ConfigExtension` with prefix `sedona` holding an `Arc`'d CRS engine
(`rust/sedona-common/src/option.rs:262, 40-55`) **[51b]**; and DataFusion 54.1.0 against
Sail's 55.1.0. **Nothing Sedona needs arrives as an `Any`**: its whole surface is names and
one plan transformation, so §2 and §11 are its entire story and §3–§9 are not for it.

**Nutmeg** embeds Grust's graph kernels in a Sail server: stage a graph from a DataFrame,
run a kernel, read a DataFrame back. Today it compiles against Sail's crates by path
(`Cargo.toml:44-48`) and embeds the server through the embedder hook that
[#2630](https://github.com/lakehq/sail/pull/2630) added, **which is merged**:
`e976c8b3` "feat: let an embedder choose the session factory (#2630)", present at
`a3761b2e` as `create_spark_session_manager_with_factory` and
`pub type ServerSessionFactoryFn` (`crates/sail-spark-connect/src/session_manager.rs:103-117`,
`crates/sail-session/src/session_manager/mod.rs:23-24`) ([SCI] §4.4). The fourth
revision described it as pending; it is upstream, and its doc comment
(`session_manager.rs:25-30`) explicitly invites the wrapping pattern. Nutmeg's remaining
defects are its own: a process-global graph store keyed by graph name
(`crates/nutmeg-graph/src/lib.rs:1109-1118`) **[51b]**, writes with no retry or attempt
identity (`nutmeg-sail/src/lib.rs:240`, `nutmeg-graph/src/lib.rs:1563`) **[51b]**, and
cancellation by stream drop signalling a detached kernel thread that keeps its resources
until it exits (`nutmeg-graph/src/lib.rs:2776, 2816-2824`) **[51b]**.

### 10.2 Nutmeg's verbs, as the envelope expresses them

The fourth revision routed Nutmeg through `format("nutmeg")` — a data-source read with an
`algorithm` option, and a write for staging — and then needed a whole section (its §7.6)
to map Spark's format API onto `FFI_TableProviderFactory`, refusing multi-path reads,
partitioning, bucketing and sort metadata along the way. **That was SQL-shaped
plumbing for verbs SQL cannot express**, and the protocol removes most of it:

```protobuf
message NutmegApi {
  oneof verb {
    StageGraph stage_graph = 1;    // envelope inputs: [vertices, edges]
    RunAlgorithm run_algorithm = 2; // input-free; names a staged graph
    DropGraph drop_graph = 3;
  }
}
```

one `oneof` envelope per library, which is the shape Delta, GraphFrames and Sinchenko's
Deequ port all converged on independently ([SCX] §3.1, §3.2, §4). The staging verb's
inputs arrive as `repeated Plan inputs` (§6.2), resolved by Sail. `format("nutmeg")` and a
table function (`read.rs:421`) remain as ergonomic and SQL surfaces, but they are no longer
the only door, and the fourth revision's option-mapping refusals shrink to whatever
`spark.read.format` genuinely needs. What stays is everything in §14 and §15: the verbs are
cheap, the execution contracts are not.

## 11. The join hook, for Sedona's spatial join

Carried from the fourth revision's §7.7 substantially unchanged, because it is the C6
case and nothing in the research touches it. SedonaDB's maintainer described the
options: "either Sail would have to hard-code some of the logical planning that
identifies a logical and/or KNN join and have a specific extension point for 'spatial
join' (which could resolve the FFI version of the executionplan), or implement some
general 'join extension' (where it passes the join condition to an extension which can
optionally return an FFI execution plan if it applies). This would be ambitious"
([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).
The general form, seated where Sail can see the join, with its own versioned
request/response ABI rather than a manifest tag:

- **Position.** A Sail-owned physical optimizer rule at a fixed place: after
  `JoinReorder`, `JoinSelection`, `FilterPushdown` and `WindowTopN`, before
  `EnsureRequirements` (`crates/sail-physical-optimizer/src/lib.rs:48-58`) **[51b]**. It
  downcasts two shapes Sail produces: `NestedLoopJoinExec` with a filter, and
  `FilterExec` over `CrossJoinExec`, which Sail's `JoinReorder` reconstructs
  (`join_reorder/reconstructor.rs:584, :600, :1010`) **[51b]**. `JoinReorder` decomposes
  only `HashJoinExec` regions, so a planner-produced nested-loop join survives it.
- **Request.** The join kind; the physical `JoinFilter` as DataFusion carries it — its
  expression, intermediate schema and side-and-index map
  (`datafusion-physical-plan` 55.1.0 `src/joins/join_filter.rs:27-33, 47-49, 66-71`)
  **[51b]** — because the expression's column indices are not indices into the
  concatenated children; both child schemas and the output schema; and the children as
  `FFI_ExecutionPlan`s. A predicate claim binds to the registered component whose
  function the resolver actually selected, not to a name.
- **Response.** An `FFI_ExecutionPlan` or a refusal, with `build_side: Left | Right |
  None`, the declared input requirements of §14.4, and an output schema Sail validates
  against the join's. A recognised predicate inside a larger condition does not authorise
  dropping residual predicates or moving them across an outer join; residuals stay with
  Sail. v1 accepts inner joins and a narrow predicate grammar; outer, semi, anti and KNN
  forms are declined without changing their results. Two extensions claiming one join is
  deterministic by registration order in v1, and the doc says so.
- **Build-side reuse.** `SpatialJoinExec` reads every build partition in every task
  (`exec.rs:466-480`) **[51b]**; Sail marks a build side `Shared` for `HashJoinExec` in
  `CollectLeft` mode and for the nested-loop, cross and piecewise-merge joins it
  downcasts (`job_graph/planner.rs:292-296, 316-326`) **[51b]**, and an unknown node
  inherits its parent's usage (`:365`) **[51b]**. The declared `build_side` travels
  through the adapter and the wire envelope. A reusable shuffle means several consumers
  may read the produced build stream; it is not proof that all tasks share one in-memory
  index, and the evidence records both.
- **Which queries reach it.** An `ON`-clause predicate is the join's filter directly. The
  cross-join-with-`WHERE` form #2001's opening post names reaches it because Sail
  installs DataFusion's default logical rules with two added and one dropped
  (`crates/sail-session/src/optimizer.rs:9-15`, `sail-logical-optimizer/src/lib.rs:24-40`)
  **[51b]**, lowers a cross join through `LogicalPlanBuilder::cross_join`
  (`resolver/query/join.rs:90`) **[51b]**, DataFusion's `push_down_filter` folds the
  predicate into the join (55.1.0 `push_down_filter.rs:431-434, 502`) **[51b]** and the
  physical planner plans a filter-only join as `NestedLoopJoinExec`
  (`physical_planner.rs:1693-1694`) **[51b]**. That chain is read, not run; increment E
  runs it. Sedona's `MergeSpatialFilterIntoJoin`, `KnnJoinEarlyRewrite` and query-side
  pushdown are not covered. Four Sail and DataFusion rules will then walk over the opaque
  node and treat it generically: `EnsureRequirements` (now seeing the adapter's declared
  requirements rather than defaults), the post-optimization `FilterPushdown`
  (`sail-physical-optimizer/src/lib.rs:71`) **[51b]**, `RewriteCollectLeftHashJoin` and
  `EnforceBarrierPartitioning` (`:73-74`) **[51b]**.

Physical optimizer rules as extension components stay deferred: neither reference
extension ships one, and the only rule in this design is Sail's.

## 12. Loading: the Rust equivalent of a jar on the classpath

### 12.1 What the JVM does, and what Sail has

The JVM answer is a class name in static server conf plus a jar on the classpath:
`spark.connect.extensions.{relation,expression,command}.classes`, built with
`buildStaticConf` (`Connect.scala:184-218, 28`), so **registration is a server-startup
decision, not a per-session one**, and the registry is a process-global lazily
initialised singleton whose instances need a zero-argument constructor and "should not
rely on internal state" (`SparkConnectPluginRegistry.scala:31,49-80`,
`RelationPlugin.java:25-32`) ([SCX] §2.2, §2.3). `spark.connect.ml.backend.classes` is
the one per-session knob, because it uses plain `buildConf` ([SCX] §2.2).

Sail's only precedent is `pysail.datasources`
(`crates/sail-data-source/src/formats/python/discovery.rs:28`), discovered by embedded
Python through `importlib.metadata` (`discovery.py:4, 20-25`), validated, **cloudpickled**
(`discovery.rs:245-251`) and stored in a **process-global `DashMap`**, `DATA_SOURCE_REGISTRY`
(`discovery.rs:58-59`), reached only from the server factory
(`crates/sail-session/src/session_factory/server.rs:113` via `formats.rs:20-25,44-52`).
**No package in the repository declares that group** — `pyproject.toml` has only
`[project.scripts]` (`:75-76`) — so it is the intended third-party seam, currently unused
and undocumented, and its failures are near-silent (`discovery.rs:130`, `:156-176`)
([SCI] §6.1). There is **no `dlopen` plugin ABI**: the single `libloading` use is
`sail-catalog-hms` loading the system GSSAPI library by fixed platform filename
(`security/gssapi.rs:165`), and the two `cdylib` crates are PyO3 extension modules
([SCI] §6.3). The `sail` binary calls `Python::initialize()` unconditionally for every
subcommand **including `worker`** (`crates/sail-cli/src/main.rs:27`), and there is no
`python` feature to compile it out (`sail-cli/Cargo.toml:13-15`) ([SCI] §6.4) — which is
what makes a Python-discovered extension reachable on workers at all (§15).

### 12.2 The manifest, carried forward with a Connect component kind

An entry point in group `pysail.extensions`, mirroring `pysail.datasources`, resolving to
an object with one method `__sail_extension__(self) -> PyCapsule`, capsule name
`sail_extension`. Distribution is PyPI; discovery is `importlib.metadata`; Sail `dlopen`s
nothing (C3, C8). The capsule holds a Sail-owned `#[repr(C)]` manifest — producible from
Rust, not a C API, and deliberately small:

```rust
#[repr(C)]
pub struct SailExtension {
    pub sail_ext_abi_version: u32,   // first field: layout of this struct
    pub datafusion_major: u64,       // must equal Sail's, or refused with a message
    pub name: *const c_char,         // "sedona", "nutmeg"
    pub version: *const c_char,
    pub placement: SailPlacement,    // AnyWorker | DriverOnly, for the whole extension
    pub n_components: u32,
    pub components: *const SailComponent,
    pub release: unsafe extern "C" fn(*mut SailExtension),
}
```

**v1 component kinds.** A kind not in this table is not in v1; there are no reserved
undefined tags.

| kind | payload | notes |
| --- | --- | --- |
| `ScalarUdf`, `AggregateUdf`, `WindowUdf` | `FFI_ScalarUDF` etc. | registered into `CatalogManager` for scalars (§2); aggregates and windows need the resolver work |
| `TableFunction` | `FFI_TableFunction` | resolves today from the DataFusion session (`read.rs:421`) |
| `TableProvider` | `FFI_TableProvider` | named, for `format("name")` reads |
| `TableProviderFactory` | `FFI_TableProviderFactory` | named, for `format("name")` reads and writes |
| `PhysicalExtensionCodec` | `FFI_PhysicalExtensionCodec` | rebound per session (§12.4) |
| `ExtensionOptions` | `FFI_ExtensionOptions` | registered into the session config |
| **`ConnectRelationHandler`** | **a Sail-defined vtable (§7.2, §8)** | **declares the type URLs it claims, the input arity and whether it accepts a bare `Any` (§6.3)** |
| **`ConnectCommandHandler`** | **same, empty-success result shape (§9)** | **same** |

The last two are new in this revision and are **not** `datafusion-ffi` objects: the FFI
has nothing shaped like "an `Any` and some planned inputs in, a `TableProvider` out". So
they are Sail's ABI, declared as such, versioned by `sail_ext_abi_version`, and §16's C1
row records the cost. The join hook (§11) is likewise its own request/response ABI.

A handler declares, at registration: the type URLs it claims (§5); its envelope mode
(§6.3); its output field names per verb, or that it computes them from the inputs (§8);
and its placement, inherited from the extension (§14.3).

### 12.3 Where the registry lives, and the defect this proposal has to own

A per-session `ConnectExtensionRegistry` would be one more `SessionExtension` — Sail
registers eight per session today (`server.rs:113-129`), plus `SparkSession` and
`PlanService` — read back from the resolver with `ctx.extension::<T>()?`, the same call
the resolver already makes for `CatalogManager` (`resolver/expression/function.rs:77`)
([SCI] §4.2). That is the right home.

**But an embedder cannot get one there.** `ServerSessionFactoryFn` is a bare
`fn(Arc<AppConfig>, RuntimeHandle) -> Box<dyn SessionFactory<ServerSessionInfo>>`
(`crates/sail-session/src/session_manager/mod.rs:23-24`) — **a function pointer, not a
boxed closure** — so an embedder cannot capture a registry in it; the registry must be
process-global, exactly as `DATA_SOURCE_REGISTRY` is ([SCI] §4.4, §9). **That is the same
multi-tenancy defect this proposal criticises in Nutmeg** (§10.1: a process-global store
keyed by graph name), and it has to be said plainly rather than left for a reviewer to
find. Two consequences:

1. v1's discovered manifests live in a process-global map, as the Python data sources do.
   Per-session state is then the *binding* (§14.2), not the registry: each session gets
   its own handles, snapshot and enablement, derived from the global manifest set.
2. The honest fix is for `ServerSessionFactoryFn` to become a boxed closure, or for
   `ServerSessionInfo` (`crates/sail-session/src/session_factory/server.rs:33-38`) to
   carry a registry the embedder chose. Either is a small Sail change and it is on the
   ask list (§18). Until then, an embedder registering handlers per tenant cannot do it
   through the factory.

Note the existing asymmetry this inherits: entry-point data sources are process-global
(`discovery.rs:58`) while Connect-registered ones are per session
(`plan_executor.rs:680-687`), and both answer the same `spark.read.format(name)` lookup
([SCI] §6.2). A third registry with a third scope would make that worse; hence one
global manifest set with per-session binding.

### 12.4 Breaking changes (C5.1)

Two numbers are checked before any component is touched, and a mismatch is an error
naming both sides. The version is the first field so a layout mismatch cannot fault
before the check runs — the gap datafusion-python describes in its own check
(`crates/util/src/lib.rs:195-198`: "`version` is not the first field on any of these
types, so a sufficiently different layout can fault before this ever runs") **[51b]**.
`datafusion_major` is in the manifest because most FFI structs carry no `version` field —
about a dozen do, and none of the UDF kinds, `FFI_TaskContext`, `FFI_PlanProperties`,
`FFI_SessionConfig`, `FFI_ExtensionOptions` or `FFI_RecordBatchStream` **[51b]** — while
`datafusion-ffi`'s own `version()` returns the crate major and nothing checks it
(`src/lib.rs:64-68`), the README calling matched versions recommended "but this is not
strictly required" (`README.md:38-40`) and stabilisation still open
([#17374](https://github.com/apache/datafusion/issues/17374)) **[51b]**. SedonaDB's
maintainer: "my main complaint with the DataFusion FFI is that the major version is not
part of the FFI, so you get a crash if you try to mix datafusion-python versions with
whatever your extension was compiled against but you could work around that here"
([#2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083581)).
So v1 **pins and tests one exact DataFusion FFI version and build tuple**, carried in the
task descriptor (§14.3). What cannot be promised is independence from DataFusion's major:
an extension releases on its own schedule within a pinned build and rebuilds when Sail
moves. C1 is met to that extent, and the Connect handler kinds are additionally versioned
by `sail_ext_abi_version` because they are Sail's own ABI.

Three further FFI properties that shape the rest: a handle returning to the library that
made it unwraps to the original `Arc` by `library_marker_id` while a handle from another
library becomes an opaque `ForeignExecutionPlan` (`src/execution_plan.rs:418-419`,
`src/query_planner.rs:29-35`, marker at `src/lib.rs:64-88`) **[51b]** — so a marker
identifies a library instance, never a wire identity (§14.1); every `ConfigExtension`
flattens to a string map and is recovered only where a `Default` parses from strings
(`src/config/mod.rs:42-78, 81-101`) **[51b]**, so a typed extension holding an `Arc` does
not cross; and `FFI_PhysicalExtensionCodec::new` rebinds an imported codec to the
supplied task-context provider (`src/proto/physical_extension_codec.rs:292-317`,
regression test at `:731`) **[51b]**, so per-session codec binding is supported.

## 13. Prerequisites that are not optional

The fourth revision called making `ExtensionPhysicalPlanner` return `Ok(None)` for
unknown nodes "worthwhile composability work". [SCI] §9 corrects both the line and the
weight, and the correction matters:

- `ExtensionQueryPlanner::create_physical_plan` builds `extension_planners` as a
  **hardcoded eight-element vector literal** at `crates/sail-session/src/planner.rs:101-110`
  (`DeltaPhysicalPlanner`, `IcebergPhysicalPlanner`, `SystemTablePhysicalPlanner`,
  `ListingPhysicalPlanner`, `ConsolePhysicalPlanner`, `NoopPhysicalPlanner`,
  `PythonPhysicalPlanner`, `ExtensionPhysicalPlanner`), passed to
  `DefaultPhysicalPlanner::with_extension_planners` at `:111`. **Nothing in a session can
  add to that list.**
- The last planner in the list **errors instead of declining**:
  `return internal_err!("unsupported logical extension node: {:?}", node);` at
  `crates/sail-session/src/planner.rs:542` (not `:540`).

So a `LogicalPlan::Extension` route needs **both** changed: the vector must become
session-derived, *and* `:542` must become `Ok(None)`, because until it does there is no
position a plugin planner could occupy even if the vector were opened ([SCI] §9,
§8.1 items 7–8). It is a prerequisite, not composability polish.

This is also the argument for §7.2's ABI: the `TableScan`-over-`TableProvider` route
needs neither change and works today, so v1 can ship the protocol seam before this
prerequisite lands, and the `LogicalPlan::Extension` route waits for it. The honest cost
of deferring is everything in §7.4's first bullet.

## 14. The execution contracts

Opening the protocol (§3–§9) admits a request. Opening the FFI (§7) admits an object. These
eight contracts are what make its execution correct afterwards. They are orthogonal to the
protocol question — they apply to whatever a handler returns — and they are carried from the
fourth revision's §6 because nothing in the research touches them. Each names the mechanism
that would otherwise break it and the v1 policy.

| | Contract | What breaks it | v1 policy |
| --- | --- | --- | --- |
| **14.1** | **Ownership and identity.** Every plan-producing boundary carries an explicit extension and component identity. | A library marker identifies a *library*, not an extension (§12.4): two manifests may share a provider library, a glue manifest may list another's objects, and a provider may return a plan another library made. | Sail wraps a foreign plan in a Sail-owned adapter carrying that identity, and the wire envelope (§15) carries the same. Markers stay an FFI unwrapping optimisation, never a wire identity. Conflicting ownership at load is a rejected load; mixed-owner children under a foreign parent are recorded per child. |
| **14.2** | **Session binding and configuration snapshots.** A host-issued session identity and incarnation, an explicit close and expiry, per-session component handles, and one configuration snapshot per query. | The server factory gets `ServerSessionInfo { session_id, user_id, session_manager, job_runner }` (`sail-session/src/session_factory/server.rs:33-38`), the worker factory gets `()`, the manager's map is keyed by `session_id` alone (`session_manager/actor/mod.rs:20`) with the id straight off the wire (`server.rs:129`), and there is **no incarnation beyond the id and no close hook exposed to extensions** (`session_manager/mod.rs:63-72`) ([SCI] §4.4). | The snapshot (enablement, `SET` values, exported-UDF options) travels to task decoding and execution, so driver and worker run one query under one effective configuration, and a query planned before a concurrent `SET` keeps its snapshot. Codecs bind per session through §12.4's rebinding. Nutmeg's session-scoped store and §12.3's per-session binding over a global registry both rest on this. |
| **14.3** | **Placement, covering functions as well as nodes.** Placement cannot be decided from foreign plan nodes alone. | A foreign scalar can sit inside an ordinary projection with no foreign node above it, while the job graph places stages by walking plan nodes, barrier and root-preservation paths included (`job_graph/planner.rs:254, 881`) **[51b]**. | A `DriverOnly` extension may not export scalar, aggregate or window functions — only table functions, providers, Connect handlers and plans, whose nodes the walk sees. Every task carries a required-extension descriptor (extension and component identity, wire-format version, build tuple, configuration identity) validated before scheduling or decoding, so a missing worker package fails with both identities named rather than at execution. Exact package equality across the deployment. |
| **14.4** | **Physical input requirements.** The adapter declares the foreign node's per-child distribution and ordering requirements and the relationships between children. | `ForeignExecutionPlan` does not forward input requirements (§7.4), so a foreign operator needing one partition, sorted or co-partitioned input can receive incompatible children — and **the answer changes, not only the plan**. | Sail validates the declarations through child replacement, optimizer passes, encoding, decoding and task preparation, and accepts only single-partition and unspecified shapes. **Sail coalesces before any foreign `insert_into`**, because `DataSinkExec` needs one input partition and executes only partition 0 (§7.4): in-process `EnsureRequirements` inserts that coalesce, across the FFI the requirement is invisible, and a multi-partition write would stage partition 0 and report success. `build_side` (§11) is an instance of this, not a substitute. |
| **14.5** | **Runtime fidelity.** Memory, temporary disk, object stores and typed services are each either provided across the boundary or refused with an explicit unsupported error — never silently defaulted. | A foreign parent executes Sail's children through a task context rebuilt with `RuntimeEnv::default()` and a `SessionConfig` carrying only `ConfigOptions`, falling back to defaults on error (`datafusion-ffi` `src/execution/task_ctx.rs:193-242`, `src/session/config.rs:137-139`) **[51b]**: no configured memory pool or spill policy, no object-store registry, no caches, no typed services (`sail-session/src/runtime.rs:42`) **[51b]**, and the same defaults for its own memory. | Until [datafusion#24733](https://github.com/apache/datafusion/pull/24733) (open, head `f509f500` when checked) or an equivalent lands, a foreign parent over a Sail child is accepted only where every part it needs is unused (a `ShuffleReadExec` child reads only `batch_size()`, `plan/shuffle_read.rs:98`) **[51b]** or declared as the extension's own independent budget. **This bites the envelope directly**: §6.2 hands a handler already-planned children. Nutmeg's kernels have their own admission; that covers the kernels, not the Sail operators or transfer buffers around them. |
| **14.6** | **The distributed scan invariant.** A foreign scan declares its partition semantics, or is restricted to the driver. | Task preparation rewrites native file scans to disable process-local sibling work sharing, because in cluster mode each partition is an isolated task and would otherwise scan every file (`sail-execution/src/task_runner/preparation.rs:58-65`); an opaque foreign node never matches that downcast. | Declared through the adapter. Local-file readability proves nothing about this. |
| **14.7** | **Mutation, retry and commit**, specified separately from residency. | The scheduler retries task regions and cancels other attempts in a failed one (`driver/job_scheduler/core.rs:150-175`), so a commit-before-acknowledgement can be replayed, and **nothing in Sail gives an extension an operation or attempt identity to key idempotency on** ([SCI] §8(b).5). Deduced from the scheduler, not fault-injected. | For Nutmeg: at-most-once, no retry, an explicit indeterminate outcome when a write's acknowledgement fails, and a retried read that pins the graph revision it started on or discloses that it may observe a newer one. An append would otherwise apply twice, and an overwrite is not automatically safe under concurrent writes or read-visible revisions. Prepare/commit keyed by session incarnation and logical operation identity is the later design. |
| **14.8** | **Cancellation end to end**, evidenced by kernel termination and accounting release rather than receipt of a request. | Spark distinguishes interrupt, release and reattachment (`service/plan_executor.rs:566`, `executor.rs:359`) **[51b]**; a stream drop across the FFI is one signal among those. | Tested through the Spark client operation: during computation, blocked on a full output channel, under `LIMIT` and early consumer stop, on session expiry, driver shutdown and task-region cancellation. Exported Arrow batches held past the drop stay valid until the last consumer releases them. |

## 15. Cluster mode: where a working plugin breaks

Unchanged in substance from the fourth revision, re-verified by [SCI] §7 with corrected
lines. The order of these facts is the point.

- **`RemoteExecutionCodec` is a unit struct** — `crates/sail-execution/src/proto/codec.rs:338`
  — so **nothing can be injected into it**. It is constructed inline at
  `driver/job_scheduler/mod.rs:37` and `task_runner/preparation.rs:59,156`. Decode is a
  closed match whose terminal arm is `codec.rs:1870`
  (`plan_err!("unsupported physical plan node: {node_kind:?}")`); encode is a closed
  downcast chain whose terminal `else` is **`codec.rs:2960`**. **That encode error is what
  a plugin `ExecutionPlan` hits — on the driver, at task-definition build time, before any
  worker is contacted.** Data sinks fail separately at **`codec.rs:2566`**. The
  serializable set is a protobuf `oneof` of 58 Sail-internal node types
  (`sail-execution/proto/sail/plan/physical.proto:12-79`); physical expressions are
  equally closed (`physical.proto:87-96`, errors at `codec.rs:4194, 4235`). There is **no
  `LogicalExtensionCodec` in the repo**.
- **UDFs have one accidental fallback that does not help.** `try_encode_udf`
  (`codec.rs:3441`) writes an empty buffer for an unmatched UDF at **`codec.rs:3756-3757`**
  and `datafusion-proto` then resolves by name from the decoding session's registry; the
  21-line TODO at **`codec.rs:2969-2990`** states verbatim that "The `match name` below has
  no session-registry fallback, so every scalar UDF needs an explicit arm or distributed
  decode fails with 'could not find scalar function'" (failure string `codec.rs:3437`,
  aggregate/window analogues `:3842, :4052`). It does not help because of the next point.
- **The worker session is the hard blocker.** `WorkerSessionFactory::create`
  (`crates/sail-session/src/session_factory/worker.rs:34-53`) is `SessionConfig::default()`
  plus exactly **two** extensions (`DeltaTableCache`, `RepartitionBufferConfig`, `:39-43`)
  and `with_default_features()` (`:45-50`). **Nothing session-registered crosses to a
  worker**: no `DataSourceRegistry`, no `CatalogManager` (hence no `CatalogManager`-registered
  UDF — §2's zero-change path), no `SparkSession`, no Sail query planner. Driver-*placed*
  tasks do run under the user's `TaskContext` (`job_runner.rs:118` → `JobDescriptor` →
  `driver/job_scheduler/core.rs:680`), so they see session-registered UDFs — but they go
  through the same encode (`core.rs:668`, placement-agnostic).
- **Placement and stage cutting are closed type matches.** `is_driver_stage_plan` is a
  closed six-type match at **`crates/sail-execution/src/job_graph/planner.rs:639-650`**, so
  a plugin node cannot opt into driver placement; stage boundaries are cut at a hardcoded
  node set at **`:370-385`** (plus join special cases at `:304-369`), so a plugin node
  cannot declare a boundary or a single-partition requirement; task assignment filters on
  free slots only, with no capability or affinity matching
  (`driver/task_assigner/core.rs:97,279,346,352`).
- **The precedent that works, and why it does not generalise.** Python UDFs and data
  sources reach workers because the payload rides as bytes inside a node type the closed
  codec already knows: `PySparkUdf { .. bytes payload = 3 .. }` (`physical.proto:281-289`,
  decode `codec.rs:3000-3029`), `PythonDataSourceExecNode { pickled_reader, .. }`
  (`physical.proto:1155-1183`, encode `codec.rs:2891-2931`, decode **`codec.rs:1797-1849`**).
  That needs a pre-existing `oneof` arm owned by `sail-execution` and a runtime in the
  worker able to materialise user code from bytes. **The worker binary is the same `sail`
  binary** (`crates/sail-cli/src/worker/entrypoint.rs:20-28`), Python is initialised in it
  unconditionally (`sail-cli/src/main.rs:27`) and Kubernetes pods run `["sail", "worker"]`
  (`worker_manager/kubernetes.rs:377-386`), so entry-point discovery *can* run there. It
  does not today: `register_external_data_sources` is reached only from the server factory
  (`session_factory/server.rs:113`).
- **Local mode bypasses all of it.** `LocalJobRunner::execute`
  (`crates/sail-execution/src/job_runner.rs:57-79`) calls
  `execute_stream(plan, ctx.task_ctx())` at `:78`: **no encode, no proto, same process,
  same `SessionContext`**. Mode selection is `ServerSessionJobRunnerFactory::create`
  (`session_factory/job_runner.rs:96-137`). **So a plugin works in `local` and breaks the
  moment the deployment mode changes, and the failure is invisible until then** — this is
  the failure users will actually hit, and it is the reason §17's increments each require a
  separately started worker rather than `local-cluster`, whose workers are actors cloned
  from one context in the server process (`worker_manager/local.rs:22`,
  `session_factory/job_runner.rs:99`) **[51b]**.

**What cluster mode therefore requires** ([SCI] §8, cluster delta): a registrable or
composable `PhysicalExtensionCodec` replacing the unit struct at both construction sites;
an envelope in `physical.proto` carrying owner identity so decode is by identity rather
than `oneof` tag, order-independent, carrying the adapter's declared input requirements
(§14.4) and the wire-format version — `FFI_PhysicalExtensionCodec` carries no
discriminator (`try_encode(plan)`, `try_decode(buf, inputs)`,
`src/proto/physical_extension_codec.rs:51-59`) **[51b]**, so the envelope must be Sail's;
worker sessions that run discovery and register every `AnyWorker` extension with the
session snapshot of §14.2; and an extension point in `is_driver_stage_plan` plus the
stage-boundary list. Classification is centralised so the main placement walk, the barrier
paths and root preservation agree; a `DriverOnly` owner forces a driver stage as
`DeltaCommitExec` does since [#2192](https://github.com/lakehq/sail/pull/2192). The
final-stage rule (`job_graph/planner.rs:59`) **[51b]** is unchanged: a driver-only read is
followed by a worker stage forwarding its output, and a driver stage that ingests a shuffle
is a new pattern that should be named as one.

**The cost for Nutmeg, stated plainly:** every row of a staged graph passes through the
Spark Connect server process on write, and a read's rows pass driver → worker → driver →
client. A `DriverOnly` extension pays that for residency. C6 points at the alternative — a
Nutmeg *service* in a separate process reached from a Python data source, needing nothing
from Sail — and what that gives up is a copy-free Arrow handoff and a single deployable.
That is a trade a maintainer may reasonably decline to support; §16's C6 row says so.

## 16. Boundaries of the first release, and the check against the constraints

**Out of v1:** logical plan transformation (the FFI cannot carry it, and §13 is the
prerequisite even for Sail-side logical nodes); generic catalog providers (Sail's
named-table resolver asks `CatalogManager`, not DataFusion's registry,
`resolver/query/read.rs:30` **[51b]**, so an imported DataFusion catalog is invisible to
Spark SQL); `FileFormat` — file formats cross as table providers, so Sail's parquet reader
gains no GeoParquet handling and SedonaDB's parquet replacement
(`rust/sedona/src/context.rs:272`) **[51b]** and dynamic object-store catalog (`:298-302`)
**[51b]** are not integrated; object stores and the host runtime (§14.5); extensible type
mapping, the geometry mapping accepting three CRSs; Sedona's client geometry UDT, a
`UserDefinedType` over `BinaryType` (`python/sedona/spark/sql/types.py:47-51`) **[51b]**
with its own preamble format against Sail's Spark 4.1 `GEOMETRY`
(`resolver/data_type.rs:329-366`) **[51b]**, so a geometry column cannot be collected;
prefix type-URL claims (§5); hidden output fields (§8); `ExecutePlanResponse.extension`
(§9); per-request options through `RequestOption` (§3.3, silently discarded); and
expression extensions — opening `proto/expression.rs:265` would need a `spec::Expr` variant
and a `resolve_named_expression` arm (`resolver/expression/mod.rs:101-106`) to serve a
client that constructs extension expressions directly, **which no known client does**
([SCI] §8(c)).

`SET k=v` already reaches a registered `ConfigExtension` through DataFusion
(`resolver/command/variable.rs:20-22` → `execute_logical_plan` → `ConfigOptions::set`,
`datafusion-common-55.1.0/src/config.rs:2018-2056`), and an unregistered prefix routes to
`FFI_ExtensionOptions` when the `datafusion_ffi` namespace is present (`:2044-2052`) **[51b]**,
so `SET sedona.x` reaches an extension's options once the manifest registers them, under
§14.2's snapshot rule. `spark.conf.set` does not — it stays in a Spark-side string map
(`sail-spark-connect/src/config.rs:145-151`) **[51b]**. What blocks Sedona is on its side:
kernels read options baked at export (`c/sedona-extension/src/scalar_kernel.rs:388-427`)
**[51b]**, not per call.

| | Met by | Strongest case against |
| --- | --- | --- |
| C1 | every FFI component is a `datafusion-ffi` object; Sail's own ABIs are the manifest, the Connect handler vtables (§12.2) and the join hook (§11) | independence holds only within a pinned DataFusion build, and this revision adds two Sail-defined ABIs the fourth did not have |
| C2 | nothing registers through the mutator in the target design | §2's zero-change scalar path reaches `CatalogManager` *only* through the mutator today, so the cheapest increment uses the thing C2 distrusts |
| C3, C8 | Python packages, entry points, capsules, no `dlopen` | the `unsafe` surface is the whole `datafusion-ffi` call surface, plus two Sail vtables |
| C4 | §17 increment A: a registration and a test, no new ABI | server-side results only, because of Sedona's client UDT |
| C5.1 | two checked versions, first-field layout, an exact build pin, `sail_ext_abi_version` for Sail's own ABIs | none found |
| C5.2 | **answered, not deferred**: §3–§9 are the Connect mechanism, with a type-URL registry, a Sail envelope and a named divergence from the JVM | the envelope breaks byte-compatibility with a JVM plugin (§6.2) |
| C5.3 | the join hook has a fixed position; claimant precedence is by registration order; §13 names the planner-order prerequisite | logical ordering is deferred with the logical layer |
| C6 | the FFI is used for one plan transformation (§11) and for leaf-shaped verbs (§7) | the leaf verbs are justified by residency, which no maintainer has endorsed, and C6 prefers a Python data source for exactly that shape |
| C7 | Sail stays a Python-distributed server; Nutmeg stops compiling against Sail's crates | Nutmeg compiles against them today, and §12.3 needs one more Sail signature change to stop |

## 17. Increments, each with the evidence that ends it

Resequenced: the protocol seam moves from last to second, because it is where one of the
two reference extensions lives and because it needs no new FFI ABI in local mode.

| | Deliverable | Evidence that ends it |
| --- | --- | --- |
| **A** | §2 with no new ABI: a native `ScalarUDF` registered into `CatalogManager`, the precedence matrix, and an independently compiled FFI fixture with a scalar, an aggregate and a window function so `DISTINCT`, `FILTER`, `ORDER BY`, nulls and partial/final aggregation are qualified now | unmodified `apache-sedona` PySpark client in `local`: `ST_*` resolves by name and server-side queries (`ST_Intersects` filters, `ST_AsText` projections, counts, aggregates) equal an independent oracle. **Not a pass condition and not achievable:** collecting a geometry column (§16). Separate wheels; the codec path in `local-cluster`; a separately started worker showing the §15 failure explicitly. No client-compatibility or performance claim |
| **B** | §3, §5, §6, §7.2, §8, §9 in local mode: the three rejections opened, two `spec` variants, the type-URL registry, the envelope with resolved inputs, the bare-`Any` path, the `FFI_TableProvider` handler ABI, the field-name contract, the empty-success command shape | Nutmeg's three verbs over Spark Connect in `local`: staging from a two-DataFrame envelope, an input-free algorithm read, correct user-facing column names on both — a test that *fails* without §8's registration — an unclaimed type URL producing an error naming it and the registered set, a bare `Any` to an envelope-only handler refused by name, recursion and size limits on a hostile nested message |
| **C** | §12 and §14.1–§14.3: the `pysail.extensions` entry point, the manifest with the two Connect handler kinds, ownership identity, session binding and snapshots, task descriptors | mismatch, lifecycle and ownership tests: two manifests from one module, a glue manifest importing another's objects, a delegated foreign plan, a missing worker package, a version mismatch; a documented statement of what the process-global registry (§12.3) does and does not isolate, with a two-tenant test |
| **D** | §13, §15 and §14.4–§14.8: the extension-planner vector and `planner.rs:542`, a composable codec and wire envelope, worker discovery, placement, the adapter carrying input requirements, and Nutmeg constrained — session-scoped store, at-most-once writes | a four-partition write stages every row; a fault injected after mutation and before acknowledgement gives the specified outcome and count; concurrent append and overwrite; a refused write leaves the previous graph intact; foreign fixtures needing single-partition, sorted and co-partitioned input give exact output over uneven and empty partitions and after post-decode child replacement; memory pressure and spill exhaustion under a foreign parent produce an explicit unsupported error, never a silent default; cancellation per §14.8 with kernel termination and accounting release observed; two sessions using one graph name see their own data; in `local-cluster` **and** with a separately started worker |
| **E** | §11: the join ABI, a codec for `SpatialJoinExec` on the Sedona side, options per call, declared requirements and build reuse | differential tests against an unoptimised oracle over nulls, empty inputs, duplicate matches, reordered and projected columns, a spatial predicate with a residual; several probe tasks and unequal build and probe partition counts; both shuffle production and per-task materialisation recorded; resource and object-store gates; unsupported shapes decline without changing results |
| **F** | generic catalogs and formats, physical rule components, logical transformation, expression extensions, `ExecutePlanResponse.extension`, type mapping, the Sedona client UDT | each with its own representable contract and tests |

Every test receipt names the Sail, DataFusion, extension and client revisions, the wheel and
build identities, the execution mode and process layout, the effective options and the input
partition counts, and keeps unsupported, mismatch, timeout, refusal and error outcomes
separate from passes. `EXPLAIN` exposes extension identity and version, configuration
identity, owner, placement, stage and attempt, and codec identity; Sail's tracing wrapper
walks the physical tree (`crates/sail-telemetry/src/execution/physical_plan.rs:60`)
**[51b]**, and the adapter must not hide operators from it.

## 18. Open questions for the maintainers

1. **The envelope, or byte-compatibility?** §6 proposes a Sail envelope so the host can
   resolve nested plans; the JVM's convention is opaque nested bytes the host cannot see.
   Sail cannot have both for a verb that takes a DataFrame, because handing a native
   handler a re-entrant planner would make `PlanResolver` a public C ABI (§6.3). Which
   side of that does Sail want?
2. **Two Sail-defined ABIs, or one?** C1 puts the extension API on `datafusion-ffi`, but
   the FFI has no object shaped like a Connect handler, and none shaped like the join
   hook. Are two small Sail vtables acceptable, or should a Connect handler be reached
   some other way — a Python handler, or a provider-factory call with the payload as an
   option string?
3. **`ServerSessionFactoryFn`.** Should it become a boxed closure, or should
   `ServerSessionInfo` carry an embedder-chosen registry (§12.3)? Without one of those, a
   plugin registry must be process-global, and this proposal inherits the defect it
   criticises in Nutmeg.
4. **Registration scope.** The JVM's is static server conf ([SCX] §2.2). Sail's Python data
   sources are process-global from entry points and per-session from Connect
   (`plan_executor.rs:680-687`) ([SCI] §6.2). Which does a Connect handler follow, and
   should a client be able to register one at runtime as it can a data source?
5. **`ExecutePlanResponse.extension`.** The protocol has it and the JVM never fills it
   ([SCX] §5.4). Should Sail, so that a command extension can return structured results
   without a new `ExecutorBatch` variant (§9)?
6. **Version independence.** This design gives up what SedonaDB's C ABI has
   ([sedona-db#407](https://github.com/apache/sedona-db/pull/407),
   [#1004](https://github.com/apache/sedona-db/pull/1004),
   [#1094](https://github.com/apache/sedona-db/pull/1094)), whose maintainer is "vaguely
   planning to propose them to DataFusion as well"
   ([paleolimbot, #2001](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17818136)).
   If that is weighed above C1's FFI basis, the manifest could carry those structs instead;
   that is a different proposal.
7. **Mutation beyond at-most-once** (§14.7): is Sail's prepare/commit pattern for lakehouse
   commits the right shape for an extension's writes, and should Sail issue an operation and
   attempt identity extensions can key idempotency on?
8. **Version alignment for increment A.** SedonaDB is on DataFusion 54.1.0 and arrow 58.3.0;
   Sail is on 55.1.0 and 59.2.0 (`Cargo.toml:165,194`) **[51b]**.

## 19. What is asked of others

- **Sail:** for A, nothing but a test and a documented registration path (§2), plus the
  aggregate and window constructions if those are wanted in A; for B, the three rejections,
  two `spec` variants, a resolver arm, the registry, the envelope and the field-name
  validation; for C, the entry point and the manifest; for D, `planner.rs:101-110` and
  `:542`, a composable codec, worker discovery, `is_driver_stage_plan` and the
  stage-boundary list; and one signature change from §12.3.
- **SedonaDB:** a DataFusion 55 build for A; an aggregate export over the FFI; options read
  per call; eventually a codec for `SpatialJoinExec`.
- **DataFusion:** nothing for A or B; for D and E, host-runtime sharing across the FFI
  ([#24733](https://github.com/apache/datafusion/pull/24733) or equivalent) is what lifts
  §14.5's restrictions; F waits on logical nodes crossing the FFI.
- **Nutmeg:** a Rust `cdylib` Python package (today `python/nutmeg` is pure Python and no
  crate exposes a module) **[51b]**; its own proto envelope and a thin PySpark client that
  switches on `is_remote()`, as GraphFrames does ([SCX] §3.2); a `PhysicalExtensionCodec`
  for its nodes (none exists); a session-scoped store; an at-most-once write policy with
  reported indeterminate outcomes; a pinned graph revision for reads; and acceptance of the
  driver cost in §15.
