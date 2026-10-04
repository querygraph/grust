# Sail extensions: the first contract {#introduction}

This review proposes a small, independently packaged native extension surface
for Sail. The first decision is whether to accept **scalar functions discovered
from Python wheels, exchanged through DataFusion FFI and resolved on workers**.
Stateful relations and distributed native operators are subsequent decisions.
The prototype demonstrates useful behavior; its implementation is evidence for
review, not a request to freeze all eight modules as public API.

The upstream maintainer's direction is already the starting point: Python distribution,
DataFusion FFI, independent release schedules and a narrow contract that leaves
Sail free to refactor. Spark Connect describes client requests; the FFI connects
native packages to the engine. These are complementary boundaries.
Sail retains planning, scheduling and resource policy. The design question is
which information an extension must expose so those responsibilities remain
possible. [Upstream discussion](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083578)

## Three decisions, in order {#introduction--three-decisions-in-order}

1. **Accept a scalar foundation.** Specify discovery, compatibility rejection,
   names, schema metadata, owner lifetime and worker package identity. Accept it
   when the small Sedona example composes with ordinary SQL across a shuffle,
   and incompatible or missing packages fail clearly.
2. **Review optional stateful relations.** Specify DataFrame inputs, planning
   without mutations, execution receipts, memory leases and cancellation.
   Require all-input consumption, explicit indeterminate outcomes and final-owner
   accounting. Driver gathering is the prototype's capacity boundary.
3. **Design distributed native operators.** Evaluate a focused spatial-join
   hook against broader planner hooks. Separate stateless worker execution from
   persistent graph ownership and recovery. Require truthful distribution,
   ordering, effects and resource requirements before promising scalable native
   execution.

The public contract should state observable behavior and ownership. Wrapper
names, session-manager organization, one-partition adapters and prepaid quota
sizes remain replaceable implementation choices. Exact engine-version pins
qualify this prototype; they do not promise compatibility with every future
DataFusion or Sail release.

## A thirty-minute review {#introduction--a-thirty-minute-review}

Spend five minutes here and on the [decision map](#overview),
fifteen on the [complete Sedona sample](#code-listings--sample-path),
and ten choosing the first acceptance boundary. The main sample is 246 lines of
Rust, Python bootstrap and packaging plus the existing 20-line client. Build
support, tests and protocol/resource interfaces follow in full listings.

The example exports native scalar functions. Indexed spatial joins, session
`SET` propagation and the complete Sedona feature set remain outside it.
No new runtime or cluster qualification is claimed by this document build.

For a consecutive deeper reading, follow: [Module 1: Discovery](#module-01-discovery) → [Module 2: Functions](#module-02-functions) → [Module 3: Relations](#module-03-relations) → [Module 4: Commands](#module-04-commands) → [Module 5: Placement](#module-05-placement) → [Module 6: Memory](#module-06-memory) → [Module 7: Lifecycle](#module-07-lifecycle) → [Module 8: Compatibility](#module-08-compatibility).
Each chapter separates the proposed contract, current implementation,
alternatives and acceptance criteria.

**Review target:** `querygraph/sail` at `bd8ce9ae8839477e2c08a0475ab7900b115c5366`.
Later graph experiments and optimizations are outside this snapshot.
Continue with the [module and decision maps](#overview).
The separate [host companion](https://github.com/querygraph/grust/blob/work/extensions-review-guide/docs/extensions-host-review/manuscript.md) compares
plain Sail with the prototype and maps changes to their proposed owners.


# From the brief to the design {#overview}

The brief asks for three decisions. The following maps connect those decisions
to the eight parts of the existing prototype. Read them as an index of review
responsibilities: an implemented component can establish feasibility without
becoming part of the stable author-facing contract.

## The eight-module map {#overview--module-map}

This retains Fable's module map, with the scope and choices made explicit.
The rows also provide the consecutive reading order.

| Module | Owner | Prototype status | Choice to review |
|---|---|---|---|
| [Module 1: Discovery and binding](#module-01-discovery) | Sail session integration; package author | Flag-gated Python entry points and per-session binding | Wheel discovery plus FFI, versus statically linked embedding or another package loader |
| [Module 2: Functions](#module-02-functions) | Extension; Sail registry and codec | Native scalar functions, including workers | Names, collisions, metadata and identity; later specialized planning needs a separate decision |
| [Module 3: Relations](#module-03-relations) | Sail Connect/planner; extension handler | Bounded envelope, driver-local provider | Explicit DataFrame inputs versus table-function or catalog-based invocation |
| [Module 4: Commands](#module-04-commands) | Extension execution; host outcome handling | Mutating relations emit receipts | Reuse the relation path versus a dedicated command entry point; effects remain explicit |
| [Module 5: Placement and replay](#module-05-placement) | Sail scheduler; extension declarations | Driver-native regions receive one attempt | Separate placement, state ownership and replay safety; preserve a path to worker operators |
| [Module 6: Native memory](#module-06-memory) | Sail admission; participating extension | Prepaid, non-spillable driver quota | Shared admission and lease lifetime versus the particular prepayment policy |
| [Module 7: Lifecycle and teardown](#module-07-lifecycle) | Sail session/executor lifecycle; native owner | Cleanup corrections; stuck-owner policy open | Cooperative cancellation, retained ownership and a bounded operational failure policy |
| [Module 8: Packaging and compatibility](#module-08-compatibility) | Package author; host/worker validation | Exact version pins and content identities | Initial tested combinations versus a future compatibility promise |

The scalar foundation primarily needs modules 1, 2 and 8, plus the applicable
ownership and cancellation behavior in module 7. The stateful relation surface
adds modules 3 to 6. This is a capability split, not a claim that memory or
lifecycle correctness can be omitted from scalar execution. Some generic codec
and lifecycle corrections apply with extension discovery disabled.

## The decision map {#overview--decision-matrix}

This second table turns the implementation inventory into questions that can
change its shape. It preserves the review's comparison while identifying the
cost of each choice.

| Topic | What the prototype establishes | Decision and trade-off |
|---|---|---|
| Minimum contract | A set of host adapters can support independent packages. | Promise schemas, ownership and errors; keep wrapper and manager structure private. A smaller ABI still needs adequate semantic information. |
| Distributed execution | Scalars travel to workers; native relations gather on the driver. | Gathering simplifies state ownership but concentrates data and work. Compare partition-preserving stateless operators separately from recoverable graph state. |
| Sedona integration | Native scalar predicates compose with general Sail joins. | A focused join hook can constrain complexity; broad optimizer hooks offer more freedom but expose ordering and plan internals. Neither is proved by the scalar example. |
| Native memory | Prepaid quota remains charged through its final owner. | Prepayment simplifies admission but holds idle capacity. Coordinated subpools or dynamic admission can preserve one authority with more bookkeeping. |
| Compatibility | Exact versions and package identity reject known mismatches. | Start with qualified combinations; expand only with compatibility evidence. Discovery and manifest checks do not make arbitrary native code safe. |

## How this fits Sail's design {#overview--how-this-fits-sails-design}

The upstream maintainer's public feedback endorses Python packaging and an FFI built on
DataFusion, while treating the session mutator as an internal detail. The
prototype follows that direction. The original broad Rust-trait proposal is
an alternative from an extension author, not evidence that Sail prefers that
API. [the maintainer's comment](https://github.com/lakehq/sail/discussions/2001#discussioncomment-17083578)

Sail's authors also describe lakehouse operations as engine-visible plans that
can be optimized and distributed. Applying that principle here is a design
inference: independently shipped extensions should describe enough semantics
for Sail to manage their work. An opaque driver region is a useful initial
boundary, with an explicit limit; it does not establish the distributed
operator model. [Engine-contract article](https://lakesail.com/blog/lakehouse-engine-contract/)

The next chapters move from finding a package, to calling its functions,
to constructing relations and effects, and then to the placement, ownership
and compatibility obligations that make those operations reliable. Each ends
by connecting to the next concern. The final code section gives the complete
small sample and the supporting listings without interrupting that argument.

Continue to [Module 1: Discovery and binding](#module-01-discovery).


# 1. Discovery and binding {#module-01-discovery}

The first boundary is installation: how does an independently built package
become available to a Sail session? The prototype uses Python packaging for
discovery and DataFusion FFI for native objects. Those are complementary
choices. A wheel supplies a familiar distribution mechanism; it does not, by
itself, establish binary compatibility or define query semantics.

The **public behavior** is a discoverable `pysail.extensions` entry point,
a readable manifest, and a fresh bound owner for each session incarnation.
The manifest names the package, version, API and engine versions, placement,
and supported relation types. Binding returns the object that supplies scalar
functions or relation handlers. Declared mismatches and duplicate registrations
must fail before those registrations become visible. Packages requesting a
native quota additionally implement `bind_with_resources`; ordinary scalar
packages can use `bind`. The owner must remain alive while its callbacks or
exported objects can still be used.

At the pinned Sail commit, the **implementation** checks API version 1,
DataFusion 55.1.0 and Arrow 59.3.0 before importing native capsules. Discovery
is enabled by `SAIL_EXPERIMENTAL_EXTENSIONS=1`. The session loader assigns an
incarnation, hashes installed package files and manifest options, and retains
loaded code for the process lifetime. These checks identify known mismatches;
the loader still trusts the package's declared capsule layout and native
callbacks. They are not a sandbox or proof of arbitrary binary safety.
[Manifest validation and binding](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/mod.rs#L158).

Sedona has no Sail host-crate dependency and implements no Sail Rust trait.
The [Sedona listing](#code-listings--listing-sedona-lib) nevertheless needs
its own [Python manifest](#code-listings--listing-sedona-bootstrap),
[entry point](#code-listings--listing-sedona-pyproject),
[Cargo dependencies](#code-listings--listing-sedona-cargo) and
[build preparation](#code-listings--listing-sedona-prepare). Nutmeg makes a different, explicit choice: its optional memory
contract depends on the small [resource ABI](#code-listings--listing-resource-abi)
crate, `sail-native-resource-ffi`. “No host
trait dependency” describes both paths more accurately than “no Sail dependency.”

A statically linked Rust trait can suit an application built as one unit; it
is not the selected boundary for separately compiled wheels. A C loader could
also retain Python packaging or use another discovery mechanism. Python UDFs
remain useful for expression workloads, including wrappers around native code,
but do not alone supply this table-provider contract. None of these alternatives
is intrinsically disqualified by its language.

The acceptance questions are concrete: does an incompatible manifest fail,
does a duplicate name leave no partially registered catalog, and can one
session's owner outlive another without sharing mutable session state? The
source provides validation tests; a platform verdict still needs the matching
artifact receipts. The decision here is whether trusted wheel discovery and
session ownership are the minimum supported surface. With that established,
[functions](#module-02-functions) are the smallest useful native export.


# 2. Functions {#module-02-functions}

[Discovery](#module-01-discovery) gives Sail a bound package owner. The simplest
use of that owner is a scalar function: the client submits an ordinary named
function call, and Sail resolves it without a custom expression protocol.
Sedona provides the concrete example. Its
[170-line Rust adapter](#code-listings--listing-sedona-lib) wraps existing
Apache SedonaDB Rust and GEOS kernels rather than reimplementing spatial
operations in Sail.

The **public behavior** is `scalar_udfs()` returning objects whose
`__datafusion_scalar_udf__()` method exports a `datafusion_scalar_udf` capsule
containing `FFI_ScalarUDF`. Names, aliases, argument and return semantics,
including metadata-bearing fields, must survive planning and worker execution.
The package owner remains live for every exported callback. The current policy
rejects collisions with built-ins or other registrations. Scalar packages use
`placement: "any"`; every executing worker must have the matching installed
package identity. Native function pointers do not travel over the network.

The **implementation** retains Python owners, wraps imported functions and
encodes package identity plus expression fields in Sail's task codec. Those
wrapper types and registry structures can change without becoming an API that
extension authors implement. The semantic requirement is that a geometry's
metadata survives intervening built-ins and a shuffle, and that a worker
rejects an unavailable or different package instead of selecting another
implementation by name.

The Sedona scope is deliberately smaller than a spatial engine. The package
exports 128 native scalar functions, not the entire SedonaDB catalog. It
omits five colliding functions: `st_asbinary`, `st_geomfromwkb`,
`st_geogfromwkb`, `st_setsrid` and `st_srid`. Each binding captures immutable
default options because the FFI configuration path does not preserve Sedona's
typed runtime services; host `SET sedona.*` propagation is absent. Raster,
GeoParquet readers, PROJ services and indexed `SpatialJoinExec` are not supplied.
General Sail joins can use spatial predicates, but this does not demonstrate
an indexed spatial join or its performance.
[Exact package scope](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/sedona/README.md#L70).

A raw `Expression.extension` would support custom expression syntax but require
another client representation and dispatch contract. A linked built-in would
avoid dynamic loading while coupling domain releases to the host build.
Driver-only functions could serve local use, but would need an explicit
placement restriction in distributed queries. Name resolution is the smallest
current choice for existing DataFusion scalar kernels, not an answer to every
extension shape.

Acceptance should cover nulls, aliases, geometry-field composition, worker
identity mismatch and an actual shuffle; the repository contains corresponding
fixtures, not a fresh execution verdict from this document. Reviewers should
decide the collision and configuration policies explicitly. A function still
returns values within a row: producing a new table requires the
[relation boundary](#module-03-relations).


# 3. Relations {#module-03-relations}

[Scalar functions](#module-02-functions) fit ordinary expressions. A graph algorithm
or another table-producing operation instead needs a request, zero or more
DataFrame inputs, and a result schema. The proposal has two boundaries:
Spark Connect carries that request from the client; DataFusion FFI connects
Sail to the installed implementation. Choosing the Connect envelope does not
replace or compete with choosing the native FFI.

The **public behavior** is a lazy relation. `Relation.extension` contains a
registered type URL and either an allowed bare payload or version 1 of
`SailExtensionRequest`, with payload bytes and input plans. The host validates
the request before dispatch, resolves the inputs and preserves their column
names. The bound package receives execution-plan capsules and returns a
`datafusion_table_provider` capsule describing its output. Planning, schema
inspection and EXPLAIN must not consume inputs or perform mutations. That is
an obligation of the trusted handler, not something a capsule can enforce.

The pinned **implementation** limits the envelope to 8 MiB, payload to 1 MiB,
inputs to 16, input nesting depth to 64 and type URLs to 512 bytes. Input
expressions are rejected. These bounds are reviewable policy, not incidental
parser behavior.
[Wire limits](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-spark-connect/src/proto/extension.rs#L14).
The handler receives planned physical inputs, not an FFI logical-plan API or
permission to replace Sail's optimizer. A host adapter retains Sail's task
context and runtime and coalesces every input partition into one host input
partition. Distributed native relations are driver-resident in this contract;
input gathering is not distributed execution of the native algorithm.
[Input adapter](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-common-datafusion/src/connect_extension.rs#L125).

A registered table function is a legitimate alternative for a table produced
from ordinary arguments. Arguments can carry string or binary payloads; lack
of an opaque payload is not a reason to reject it. The missing convenience in
the current function path is direct passage of arbitrary DataFrame plans.
Named tables or another handle protocol would need their own ownership and
consistency rules. A new RPC offers greater protocol freedom at the cost of
another routing and compatibility surface. A session-factory hook can install
a registry, but is complementary to the per-request relation contract.

Acceptance should include malformed envelopes rejected before child callbacks,
empty and uneven input partitions, schema preservation, and planning without
execution. Source fixtures exercise these boundaries; they do not establish
sorted or co-partitioned inputs, arbitrary host-service propagation, or indexed
spatial-join planning. Those require separate contracts and evidence.

The decision is whether this bounded physical-input interface is sufficient
for the first table-producing extensions. Once a relation may change native
state, laziness alone is insufficient: [commands and receipts](#module-04-commands)
make execution and acknowledgement explicit.


# 4. Commands and receipts {#module-04-commands}

[Relations](#module-03-relations) describe work without executing it. Some operations,
such as staging or dropping a graph, must also change state. The prototype
represents them as relations with mutating verbs and small receipt results.
The client explicitly collects the receipt. This reuses the relation transport
and input handling while making the execution boundary visible to the caller.

The **public behavior** should distinguish planning, attempted execution,
committed state and an acknowledged result. Constructing a DataFrame or asking
for its schema must not mutate state. A successful stage receipt identifies
the graph, node and edge counts, and revision; a drop receipt reports whether
removal occurred. If execution or acknowledgement is interrupted, absence of
a receipt is not proof that no mutation happened. Callers need an indeterminate
outcome, not an automatic retry presented as harmless. None of this promises
cross-request exactly-once execution or durable recovery.

The pinned **implementation** uses Nutmeg's `MutationTable` and an execution
node with one output partition. Its shared attempt state changes from ready
to running before the mutation; completion caches the receipt batch. Another
execution of that same completed object can return the cached receipt. A
running or previously failed attempt is refused rather than executed again.
A newly planned request has a new attempt object, so this mechanism is not a
persistent idempotency key.
[Mutation state and execution](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/nutmeg/src/mutation.rs#L207).
The client `stage` and `drop` methods collect the result eagerly; ordinary
algorithm results remain lazy.
[Client behavior](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/examples/extensions/nutmeg/python/sail_nutmeg/client.py#L53).

A separate safeguard sits in Sail's scheduler: a task region containing
driver-native execution receives one attempt, including native reads. That
conservative placement rule prevents the scheduler from silently replaying a
region whose effects it cannot classify. It does not prevent a client from
submitting a new request, make a lost receipt recoverable, or establish
transactions across operations. The package's cached receipt and the
scheduler's region policy solve different replay problems.

Spark Connect's raw `Command.extension` is a fair alternative and is not
implemented by this prototype. It would distinguish effects at the protocol
level, while requiring command dispatch, acknowledgement and input semantics.
The relation approach reduces the initial surface but cannot infer that an
arbitrary relation is safe to replay. A durable operation identifier and
result log would be additional design work under either transport.

Acceptance should verify no mutation during EXPLAIN, one effect on repeated
execution of a single provider, and explicit failure after an interrupted
attempt; a disconnected client must never imply rollback. The decision is
whether receipts plus conservative non-replay suffice initially, or whether
read/effect classification is required first. That leads directly to
[placement and replay](#module-05-placement).


# 5. Placement and replay {#module-05-placement}

The [command contract](#module-04-commands) makes an uncertain mutation outcome
explicit. Placement determines where that mutation may execute; replay policy
determines whether another attempt is safe. These are separate decisions. A
function over ordinary input batches can be stateless even when it runs on a
worker, while an operation tied to a process-local graph needs that owner's
state to remain available.

The public contract should require Sail to respect declared placement, reject
invalid or expired ownership, and avoid replaying work whose effects are
unknown. A serialized reference must identify the intended owner and plan, and
decoding must validate input arity and schemas. A live pointer cannot identify
an object in another process. This does not require publishing Sail's registry
layout or scheduler types as extension APIs.

At the review commit, `bd8ce9ae`, `DriverExtensionExec` references a bound plan
through owner and plan identifiers. Its registry holds weak references so it
does not independently prolong query state. A driver-native region receives
one scheduler attempt, including reads, because the host has no general
classification of extension effects. The host input adapter gathers partitions
for this initial driver policy. These are concrete implementation choices, with
the ownership and retry checks visible in the
[driver boundary](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-common-datafusion/src/driver_extension.rs)
and [scheduler](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-execution/src/driver/job_scheduler/core.rs#L264).
One attempt within a job does not provide deduplication across client requests.

The next alternative need not be replicated native state. A stateless foreign
worker operator could use serializable parameters and ordinary partitioned
inputs, provided its codec, execution context, ownership and replay behavior
are defined. Declared replay-safe reads are another possible increment.
Recoverable stateful worker stages require a larger design. None follows merely
from accepting an execution-plan capsule. Keeping these alternatives separate
also preserves Sail's goal of engine-visible distributed execution, illustrated
by its [lakehouse planning design](https://lakesail.com/blog/lakehouse-engine-contract/).

Acceptance should demonstrate rejection of wrong-owner, expired and wrong-schema
handles; no scheduler replay after a mutation loses its acknowledgement; and
ordinary retry behavior for unaffected regions. Explain output should expose
the placement boundary. A later distributed extension must also demonstrate
the partitioning properties it advertises, rather than inherit an accidental
single-partition assumption.

The immediate decision is whether conservative driver placement and one attempt
are acceptable initial policies. Approving them should not make gathering or
`DriverExtensionExec` permanent public requirements. Once placement is explicit,
the next question is [whose memory budget admits the native work](#module-06-memory).


# 6. Native memory {#module-06-memory}

The [placement decision](#module-05-placement) identifies the process that owns native
work. Memory admission must then account for that work alongside Sail's own
operators. An extension that allocates substantial state outside the host's
budget can exhaust memory even when every participating DataFusion operator
honors its reservation.

The public invariant is that participating allocations have admission before
they are made, and retain that admission until their storage and allocation
authority are gone. Native state, snapshots, producers and exported Arrow
buffers can outlive the initiating request. Returning quota when a session
closes is therefore too early if any of those owners survives. The extension
must cooperate with this protocol; a lease is not an allocator interception
mechanism or a tenant security boundary.

The review implementation prepays the manifest's `memory_bytes` from the host
DataFusion pool. A small resource ABI carries a byte limit and opaque ownership
callbacks; the extension subdivides the reservation internally. The reservation
is non-spillable, including unused capacity. At `bd8ce9ae`, this bridge serves
participating **driver-native allocations**: the
[manifest validator](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/manifest.rs#L55)
rejects `memory_bytes` with another placement. It does not supply equivalent
admission for worker scalar UDF allocations. The
[host reservation](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-common-datafusion/src/native_resource.rs#L104)
accounts participating bytes, not process RSS.

With extensions enabled, the standard session manager shares one admission
domain with its sessions and in-process workers. Separately started worker
factories own separate domains. This topology and the pool's configured limit
must be disclosed; equal numeric limits do not imply shared ownership or a
cluster-wide budget. Runtime, Python, transport, metadata and other unaccounted
allocations require additional headroom.

Prepayment is a straightforward initial policy, but hierarchical pools or
dynamic requests to a common admission coordinator are valid alternatives.
The unsafe alternative is two independent pools each promising the same
capacity. Dynamic lending could improve utilization, at the cost of defining
failure, concurrency and reclamation across the boundary. Native spilling
additionally requires an extension-specific recovery path; it is not created
by setting a host spill option.

Acceptance should show host operators and native reservations contending against
the same finite limit, rejected admission before allocation, and a retained
Arrow output preventing early quota reuse. Last-owner tests must inspect storage
lifetime as well as reservation counters. Passing a counter-only check cannot
prove that the last buffer was already freed.

The decision is whether coarse, prepaid admission is acceptable initially, with
its scope and idle-capacity cost explicit. The public ownership invariant should
survive a later policy change. [Lifecycle and teardown](#module-07-lifecycle) determine
what happens when an admitted owner does not finish promptly.


# 7. Lifecycle and teardown {#module-07-lifecycle}

The [memory contract](#module-06-memory) ends only when the final owner releases its
storage and allocation authority. Cancellation begins that process; it does not
prove completion. A dropped client connection, interrupted query or deleted
session may still leave native producers or exported buffers alive.

The public contract needs obligations on both sides. Sail must stop accepting
new work for a closing session, request cancellation, release its streams and
buffers, and preserve an appropriate terminal identity for client reattachment.
The extension must cooperate with cancellation, stop creating new work, and
retain admission for surviving state and outputs. Neither side may present a
cancellation request as evidence that native execution has stopped. A shutdown
result should distinguish successful draining from outstanding ownership.

The implementation at `bd8ce9ae` drains protocol executors before discarding
session contexts. It separately tracks cleanup for sessions already deleted
from the manager and waits for native leases to be released. The
[shutdown sequence](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/session_manager/actor/core.rs#L125)
and [cleanup task set](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/session_manager/cleanup.rs)
are host machinery, not API types an extension should implement. A Python owner
also acquires the GIL for final destruction, avoiding a deferred decref that
could otherwise retain quota until another Python entry. Some lifecycle
corrections affect ordinary Sail execution without the extension flag; their
review and regression coverage should state that scope.

The unresolved operational policy is consequential: the native-release wait
has no deadline. Waiting indefinitely preserves accounting but can prevent
graceful shutdown. A bounded wait that reports failure is viable only if live
owners remain charged and the process prevents their state from being reused
as though cleanup succeeded. Process termination is another policy, with a
larger failure boundary. A timeout alone cannot safely revoke arbitrary native
memory or preempt a noncooperative thread. The choice must specify who acts,
what remains live, and what the caller observes.

Acceptance should cover cancellation during input and output, deletion followed
immediately by shutdown, late plan rejection, and a retained output released
after the request ends. A deliberately blocked owner should exercise the chosen
timeout or termination policy. Tests should verify both terminal client behavior
and continued admission while the owner survives, then final release when it
actually exits. Forced termination needs separate process-level evidence.

The review decision is therefore both the cooperative lifecycle contract and
the host's failure policy. It cannot be deferred behind a claim that cleanup
is already complete. Finally, [compatibility](#module-08-compatibility) determines
which independently built extensions may safely participate in this protocol.


# 8. Packaging and compatibility {#module-08-compatibility}

The [lifecycle contract](#module-07-lifecycle) assumes that both sides interpret their
shared objects correctly. Packaging makes an extension discoverable;
compatibility determines whether Sail may call into it. Those are related
concerns, but a wheel that installs successfully is not by itself evidence
that its native boundary is compatible.

The public contract should identify the supported extension API and native
interchange versions, reject declared incompatibility before accessing capsule
layouts, and define package identity consistently across driver and workers.
It must also make the trust boundary explicit: native packages promise the
named capsule layout and ownership rules. Their declarations are not a proof
that arbitrary native code is safe. Function pointers remain process-local;
workers resolve their installed implementation from a serialized identity.

At `bd8ce9ae`, the loader accepts `api_version: 1`, DataFusion 55.1.0 and Arrow
59.3.0, checking these declarations before binding native objects. Its
[manifest checks](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/manifest.rs#L31)
are deliberately exact. The
[package fingerprint](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/package_identity.py)
combines manifest options and installed package-file contents. It detects a
different installed package identity; it is not a universal ABI certificate,
an approved-artifact signature, or a fingerprint of every external dependency.
Sail does not distribute extension wheels to workers. Operators must install
matching packages there.

This is a qualified prototype boundary, not a promise that extensions must
forever share Sail's release cadence. The upstream maintainer's
[extension design response](https://github.com/lakehq/sail/discussions/2001)
explicitly favors Python distribution and DataFusion FFI so Sail and extensions
can release independently, while treating session mutators as implementation
details. Avoiding a public Sail Rust trait supports that direction. Exact pins
currently limit the demonstrated compatibility; they do not establish the
range that a future stable interface could support.

A tested compatibility range would reduce rebuilds but needs evidence for
every admitted boundary and a policy for breaking changes. Exact artifact pairs
are easier to qualify initially and can fail closed when declarations differ.
A custom C ABI could provide another stability boundary, but requires its own
versioning and ownership design. It is an alternative with maintenance costs,
not an impossibility ruled out by choosing wheels.

Acceptance should include wrong API and engine-version declarations, invalid
capsule names or types, missing worker packages, and changed package identities. Positive
controls should exercise the qualified artifacts across the actual planning,
codec and execution path. Only those tested pairs should be advertised as
supported; matching version strings alone cannot extend the claim.

The decision is the initial support statement and the evidence required to
widen it. With the eight boundaries explicit, the [code listings](#code-listings)
show the concrete extension surface reviewers can inspect next.


# Complete code and reading path {#code-listings}

## The small author sample {#code-listings--sample-path}

Read the first five listings consecutively: the native adapter, its Python
bootstrap, the two package manifests, and the spatial SQL/shuffle client.
The first four total 246 lines. The client is copied verbatim from the pinned
tutorial; its import of `functions as F` is retained even though this example
uses SQL strings. Expected assertions are distance 5.0 and distances 0 through
16 after repartition. These are expectations in the existing example, not a
new execution result from this documentation build.

Every printed source file below is complete. The client is the complete Python body of the tutorial example; server
startup is its complete shell block. Their source line intervals are recorded. Rust, Python, TOML, shell, protobuf and patch listings have
language tags for color syntax rendering. Long lines may wrap in exported
editions; the source bytes are preserved in the Markdown and code bundle.

## Running the sample {#code-listings--running-the-sample}

Use a dedicated checkout with Rust 1.97.1, shared-library Python 3.12, uv,
protoc and a C/C++ toolchain; Sedona also needs GEOS 3.12 or newer. The pinned
tutorial describes platform setup. Review these commands before running them:
the original build script synchronizes its virtual environment and builds both
Sedona and Nutmeg. This document does not run it.

```bash
git clone https://github.com/querygraph/sail.git sail-extension-review
cd sail-extension-review
git checkout --detach bd8ce9ae8839477e2c08a0475ab7900b115c5366
bash examples/extensions/scripts/build.sh
.venv/bin/python examples/extensions/sedona/scripts/smoke.py
```

In terminal A use the complete [server startup](#code-listings--listing-server-start) listing.
In terminal B save the [client](#code-listings--listing-sedona-client) as a Python file and run
it with `SPARK_CONNECT_MODE_ENABLED=1 .venv/bin/python <client-file.py>` from
the checkout. Stop the server before changing execution modes. To exercise
separate workers, retain the startup exports and change its final launch to
`SAIL_MODE=local-cluster SAIL_EXPERIMENTAL_PROCESS_WORKERS=1` followed by the
same executable and arguments. A local shuffle alone does not prove remote
worker execution; placement must be observed in the selected deployment.

The code bundle preserves the original file paths, complete Cargo lockfile,
licenses and notices, and a SHA-256 manifest. Third-party library implementations
are pinned dependencies, not reprinted here. The much larger Sail integration
is documented separately in the [host implementation companion](https://github.com/querygraph/grust/blob/work/extensions-review-guide/docs/extensions-host-review/manuscript.md).
That companion includes the complete historical host patch, with a comparison
against the separately pinned plain-Sail revision.

## Listings {#code-listings--sample-listings}

### The native scalar adapter {#code-listings--listing-sedona-lib}

Source: [examples/extensions/sedona/src/lib.rs](#code-listings--listing-sedona-lib). 170 lines.

```rust
//! The extension is an independent dynamic library with no Sail crate dependency.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::Arc;

use datafusion_common::config::ConfigOptions;
use datafusion_common::{Result, ScalarValue};
use datafusion_expr::{ColumnarValue, ScalarUDF, ScalarUDFImpl};
use datafusion_ffi::udf::FFI_ScalarUDF;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyCapsule;
use sedona_common::SedonaOptions;
use sedona_expr::scalar_udf::{ScalarKernelRef, SedonaScalarKernel};
use sedona_schema::datatypes::SedonaType;

/// FFI 55.1 cannot preserve Sedona's typed runtime services in ConfigOptions.
/// Each bound session therefore captures an explicit, immutable Sedona default
/// snapshot. Session SET propagation is outside this local proof of concept.
#[derive(Debug)]
struct SnapshotKernel {
    inner: ScalarKernelRef,
    options: Arc<ConfigOptions>,
}

fn guarded<T>(call: impl FnOnce() -> Result<T>) -> Result<T> {
    catch_unwind(AssertUnwindSafe(call))
        .unwrap_or_else(|_| datafusion_common::exec_err!("Apache SedonaDB native scalar panicked"))
}

impl SedonaScalarKernel for SnapshotKernel {
    fn return_type(&self, args: &[SedonaType]) -> Result<Option<SedonaType>> {
        guarded(|| self.inner.return_type(args))
    }

    fn return_type_from_args_and_scalars(
        &self,
        args: &[SedonaType],
        scalars: &[Option<&ScalarValue>],
    ) -> Result<Option<SedonaType>> {
        guarded(|| self.inner.return_type_from_args_and_scalars(args, scalars))
    }

    fn invoke_batch(
        &self,
        arg_types: &[SedonaType],
        args: &[ColumnarValue],
    ) -> Result<ColumnarValue> {
        guarded(|| self.inner.invoke_batch(arg_types, args))
    }

    fn invoke_batch_from_args(
        &self,
        arg_types: &[SedonaType],
        args: &[ColumnarValue],
        return_type: &SedonaType,
        rows: usize,
        _host_options: Option<&ConfigOptions>,
    ) -> Result<ColumnarValue> {
        guarded(|| {
            self.inner.invoke_batch_from_args(
                arg_types,
                args,
                return_type,
                rows,
                Some(&self.options),
            )
        })
    }
}

#[pyclass(skip_from_py_object)]
#[derive(Clone)]
struct NativeScalarUdf {
    inner: Arc<ScalarUDF>,
}

#[pymethods]
impl NativeScalarUdf {
    fn name(&self) -> &str {
        self.inner.name()
    }

    fn aliases(&self) -> Vec<String> {
        self.inner.aliases().to_vec()
    }

    fn __datafusion_scalar_udf__<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyCapsule>> {
        PyCapsule::new_with_value(
            py,
            FFI_ScalarUDF::from(Arc::clone(&self.inner)),
            c"datafusion_scalar_udf",
        )
    }
}

#[pyclass]
struct BoundSedona {
    #[pyo3(get)]
    session_id: String,
    functions: Vec<NativeScalarUdf>,
}

#[pymethods]
impl BoundSedona {
    #[new]
    fn new(session_id: String) -> PyResult<Self> {
        let mut set = sedona_functions::register::default_function_set();
        for (name, kernels) in sedona_geos::register::scalar_kernels() {
            set.add_scalar_udf_impl(name, kernels)
                .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;
        }
        let mut options = ConfigOptions::new();
        options.extensions.insert(SedonaOptions::default());
        let options = Arc::new(options);
        let mut functions: Vec<_> = set
            .scalar_udfs()
            // The first host policy rejects built-in shadowing. Omit the
            // complete UDF (including aliases) when any name would collide.
            .filter(|function| {
                const BUILTINS: &[&str] = &[
                    "st_asbinary",
                    "st_geomfromwkb",
                    "st_geogfromwkb",
                    "st_setsrid",
                    "st_srid",
                ];
                !BUILTINS.contains(&function.name())
                    && !function
                        .aliases()
                        .iter()
                        .any(|name| BUILTINS.contains(&name.as_str()))
            })
            .map(|function| {
                let kernels = function
                    .kernels()
                    .iter()
                    .map(|kernel| {
                        Arc::new(SnapshotKernel {
                            inner: Arc::clone(kernel),
                            options: Arc::clone(&options),
                        }) as ScalarKernelRef
                    })
                    .collect();
                NativeScalarUdf {
                    inner: Arc::new(function.clone().with_kernels(kernels).into()),
                }
            })
            .collect();
        functions.sort_by(|a, b| a.inner.name().cmp(b.inner.name()));
        Ok(Self {
            session_id,
            functions,
        })
    }

    fn scalar_udfs(&self) -> Vec<NativeScalarUdf> {
        self.functions.clone()
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<BoundSedona>()?;
    module.add_class::<NativeScalarUdf>()?;
    Ok(())
}

#[cfg(test)]
mod tests;
```

### Discovery and binding {#code-listings--listing-sedona-bootstrap}

Source: [examples/extensions/sedona/python/sail\_sedona/\_\_init\_\_.py](#code-listings--listing-sedona-bootstrap). 23 lines.

```python
"""Apache SedonaDB functions exported through the DataFusion 55.1 capsule API."""


class SedonaExtension:
    def manifest(self):
        # Keep validation possible before importing any native capsule provider.
        return {
            "name": "sedona",
            "version": "0.1.0",
            "api_version": 1,
            "datafusion_version": "55.1.0",
            "arrow_version": "59.3.0",
            "placement": "any",
            "relation_types": [],
        }

    def bind(self, session_id):
        from ._native import BoundSedona

        return BoundSedona(session_id)


extension = SedonaExtension()
```

### Native package dependencies {#code-listings--listing-sedona-cargo}

Source: [examples/extensions/sedona/Cargo.toml](#code-listings--listing-sedona-cargo). 34 lines.

```toml
[package]
name = "sail-sedona-extension"
version = "0.1.0"
edition = "2021"
publish = false
license = "Apache-2.0"

# This wheel is deliberately compiled independently of Sail.
[workspace]
exclude = [".deps/sedona-db", ".deps/sedona-db/*"]

[lib]
name = "_native"
crate-type = ["cdylib"]

[dependencies]
arrow-schema = "=59.3.0"
datafusion-common = { version = "=55.1.0", default-features = false }
datafusion-expr = { version = "=55.1.0", default-features = false }
datafusion-ffi = "=55.1.0"
pyo3 = "=0.29.0"
sedona-common = { path = ".deps/sedona-db/rust/sedona-common" }
sedona-expr = { path = ".deps/sedona-db/rust/sedona-expr" }
sedona-functions = { path = ".deps/sedona-db/rust/sedona-functions" }
sedona-geos = { path = ".deps/sedona-db/c/sedona-geos" }
sedona-schema = { path = ".deps/sedona-db/rust/sedona-schema" }

[profile.dev]
debug = 0
incremental = false

[profile.release]
debug = 0
incremental = false
```

### Python packaging and entry point {#code-listings--listing-sedona-pyproject}

Source: [examples/extensions/sedona/pyproject.toml](#code-listings--listing-sedona-pyproject). 19 lines.

```toml
[build-system]
requires = ["maturin>=1.8,<2"]
build-backend = "maturin"

[project]
name = "sail-sedona-extension"
version = "0.1.0"
description = "Apache SedonaDB native scalar extension for the Sail extension proof of concept"
requires-python = ">=3.12"
license = "Apache-2.0"
license-files = ["LICENSE-SEDONADB", "NOTICE-SEDONADB", "LICENSE-GEOS", "NOTICE"]

[project.entry-points."pysail.extensions"]
sedona = "sail_sedona:extension"

[tool.maturin]
features = ["pyo3/extension-module"]
module-name = "sail_sedona._native"
python-source = "python"
```

### Complete spatial SQL and shuffle client {#code-listings--listing-sedona-client}

Source: [examples/extensions/TUTORIAL.md](#code-listings--listing-server-start). 20 lines.

```python
from pyspark.sql.connect.session import SparkSession
from pyspark.sql import functions as F
spark = SparkSession.builder.remote("sc://127.0.0.1:50051").create()
try:
    row = spark.sql("""SELECT
        ST_AsText(ST_Point(1.0, 2.0)) AS wkt,
        ST_Distance(ST_Point(0.0, 0.0), ST_Point(3.0, 4.0)) AS distance
    """).first()
    print(row)
    assert row.distance == 5.0
    points = spark.range(0, 17, numPartitions=4).selectExpr(
        "id", "ST_Point(CAST(id AS DOUBLE), 2.0) AS geom")
    rows = points.repartition(4, "id").selectExpr(
        "id", "ST_AsText(geom) AS wkt",
        "ST_Distance(geom, ST_Point(0.0, 2.0)) AS distance"
    ).orderBy("id").collect()
    assert [r.distance for r in rows] == [float(i) for i in range(17)]
    print("Sedona: 17 geometry rows survived the shuffle")
finally:
    spark.stop()
```

### Complete native adapter tests {#code-listings--listing-sedona-tests}

Source: [examples/extensions/sedona/src/tests.rs](#code-listings--listing-sedona-tests). 178 lines.

```rust
use arrow_schema::{Field, FieldRef};
use datafusion_expr::{ReturnFieldArgs, ScalarFunctionArgs, ScalarUDFImpl};
use datafusion_ffi::udf::ForeignScalarUDF;

use super::*;

#[test]
fn kernel_panic_becomes_a_result_before_the_ffi_boundary() {
    let result: Result<()> = guarded(|| panic!("injected native kernel failure"));
    assert!(result
        .unwrap_err()
        .to_string()
        .contains("native scalar panicked"));
}

fn argument(value: ScalarValue) -> (ColumnarValue, FieldRef) {
    let field = Arc::new(Field::new("arg", value.data_type(), true));
    (ColumnarValue::Scalar(value), field)
}

fn one_value(value: ColumnarValue) -> ScalarValue {
    // The Arrow FFI materializes scalar arguments as one-row arrays. Assert
    // cardinality explicitly, then compare the exact value rather than the
    // implementation's Scalar/Array representation.
    let array = value.into_array(1).unwrap();
    assert_eq!(array.len(), 1);
    ScalarValue::try_from_array(&array, 0).unwrap()
}

fn call(
    bound: &BoundSedona,
    name: &str,
    args: Vec<(ColumnarValue, FieldRef)>,
) -> Result<(ColumnarValue, FieldRef)> {
    let function = bound
        .functions
        .iter()
        .find(|f| f.inner.name() == name)
        .unwrap();
    // A foreign marker prevents the same-library optimization bypassing FFI.
    extern "C" fn foreign_marker() -> usize {
        0
    }
    let mut ffi = FFI_ScalarUDF::from(Arc::clone(&function.inner));
    ffi.library_marker_id = foreign_marker;
    let imported: Arc<dyn ScalarUDFImpl> = ffi.into();
    assert!(imported.is::<ForeignScalarUDF>());
    let function = ScalarUDF::new_from_shared_impl(imported);
    let (values, fields): (Vec<_>, Vec<_>) = args.into_iter().unzip();
    let rows = values
        .iter()
        .filter_map(|value| match value {
            ColumnarValue::Array(array) => Some(array.len()),
            ColumnarValue::Scalar(_) => None,
        })
        .next()
        .unwrap_or(1);
    let scalars = values
        .iter()
        .map(|v| match v {
            ColumnarValue::Scalar(s) => Some(s),
            ColumnarValue::Array(_) => None,
        })
        .collect::<Vec<_>>();
    let result_field = function.return_field_from_args(ReturnFieldArgs {
        arg_fields: &fields,
        scalar_arguments: &scalars,
    })?;
    let value = function.invoke_with_args(ScalarFunctionArgs {
        args: values,
        arg_fields: fields,
        number_rows: rows,
        return_field: Arc::clone(&result_field),
        config_options: Arc::new(ConfigOptions::new()),
    })?;
    Ok((value, result_field))
}

#[test]
fn ffi_geometry_metadata_and_geos_predicate() {
    let bound = BoundSedona::new("ffi-test".to_string()).unwrap();
    let point = call(
        &bound,
        "st_point",
        vec![
            argument(ScalarValue::Float64(Some(1.0))),
            argument(ScalarValue::Float64(Some(2.0))),
        ],
    )
    .unwrap();
    let polygon = call(
        &bound,
        "st_geomfromwkt",
        vec![argument(ScalarValue::Utf8(Some(
            "POLYGON ((0 0, 3 0, 3 3, 0 3, 0 0))".to_string(),
        )))],
    )
    .unwrap();
    let result = call(&bound, "st_intersects", vec![point.clone(), polygon]).unwrap();
    assert_eq!(one_value(result.0), ScalarValue::Boolean(Some(true)));
    let result = call(&bound, "st_astext", vec![point]).unwrap();
    assert_eq!(
        one_value(result.0),
        ScalarValue::Utf8(Some("POINT(1 2)".into()))
    );
}

#[test]
fn ffi_null_geometry_and_aliases_are_preserved() {
    let bound = BoundSedona::new("null-test".to_string()).unwrap();
    let null = call(
        &bound,
        "st_geomfromwkt",
        vec![argument(ScalarValue::Utf8(None))],
    )
    .unwrap();
    let result = call(&bound, "st_astext", vec![null]).unwrap();
    assert_eq!(one_value(result.0), ScalarValue::Utf8(None));
    let from_wkt = bound
        .functions
        .iter()
        .find(|f| f.inner.name() == "st_geomfromwkt")
        .unwrap();
    assert!(from_wkt.aliases().iter().any(|a| a == "st_geomfromtext"));
}

#[test]
fn envelope_bypass_state_matches_partial_update_for_nulls_and_filters() {
    use datafusion_common::arrow::array::{BooleanArray, StringArray};
    use datafusion_expr::EmitTo;

    let bound = BoundSedona::new("aggregate-port".to_string()).unwrap();
    let texts = ColumnarValue::Array(Arc::new(StringArray::from(vec![
        Some("POINT(1 2)"),
        None,
        Some("POINT(10 20)"),
        Some("POINT(3 4)"),
    ])));
    let geometry = call(
        &bound,
        "st_geomfromwkt",
        vec![(
            texts,
            Arc::new(Field::new("wkt", arrow_schema::DataType::Utf8, true)),
        )],
    )
    .unwrap();
    let input_type = SedonaType::from_storage_field(&geometry.1).unwrap();
    let args = [input_type];
    let functions = sedona_functions::register::default_function_set();
    let udf = functions.aggregate_udf("st_envelope_agg").unwrap();
    let (kernel, output_type) = udf
        .kernels()
        .iter()
        .find_map(|kernel| {
            kernel
                .return_type(&args)
                .unwrap()
                .map(|output| (kernel, output))
        })
        .unwrap();
    let arrays = [geometry.0.into_array(4).unwrap()];
    let groups = [0, 0, 1, 1];
    let filter = BooleanArray::from(vec![Some(true), Some(true), Some(false), Some(true)]);
    let mut partial = kernel.groups_accumulator(&args, &output_type).unwrap();
    partial
        .update_batch(&arrays, &groups, Some(&filter), 3)
        .unwrap();
    let expected = partial.evaluate(EmitTo::All).unwrap();

    let bypass = kernel.groups_accumulator(&args, &output_type).unwrap();
    let states = bypass.convert_to_state(&arrays, Some(&filter)).unwrap();
    let mut merged = kernel.groups_accumulator(&args, &output_type).unwrap();
    merged.merge_batch(&states, &groups, 3).unwrap();
    let actual = merged.evaluate(EmitTo::All).unwrap();
    assert_eq!(actual.len(), 3);
    assert_eq!(actual.to_data(), expected.to_data());
}
```

### Installed-wheel smoke check {#code-listings--listing-sedona-smoke}

Source: [examples/extensions/sedona/scripts/smoke.py](#code-listings--listing-sedona-smoke). 31 lines.

```python
"""Verify the installed wheel manifest and every native capsule without Sail."""

import ctypes
from importlib.metadata import entry_points

from sail_sedona import extension

manifest = extension.manifest()
assert manifest == {
    "name": "sedona",
    "version": "0.1.0",
    "api_version": 1,
    "datafusion_version": "55.1.0",
    "arrow_version": "59.3.0",
    "placement": "any",
    "relation_types": [],
}
entries = [e for e in entry_points(group="pysail.extensions") if e.name == "sedona"]
assert len(entries) == 1
assert entries[0].load().manifest() == manifest
bound = extension.bind("sedona-wheel-smoke")
functions = {f.name(): f for f in bound.scalar_udfs()}
assert len(functions) == 128
assert {"st_point", "st_geomfromwkt", "st_astext", "st_intersects", "st_distance"} <= functions.keys()
assert "st_geomfromtext" in functions["st_geomfromwkt"].aliases()
assert not {"st_asbinary", "st_geomfromwkb", "st_geogfromwkb", "st_setsrid", "st_srid"} & functions.keys()
is_valid = ctypes.pythonapi.PyCapsule_IsValid
is_valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
is_valid.restype = ctypes.c_int
assert all(is_valid(f.__datafusion_scalar_udf__(), b"datafusion_scalar_udf") for f in functions.values())
print({"manifest": manifest, "scalars": len(functions), "capsules": "valid"})
```

### Pinned dependency preparation {#code-listings--listing-sedona-prepare}

Source: [examples/extensions/sedona/scripts/prepare.py](#code-listings--listing-sedona-prepare). 57 lines.

```python
#!/usr/bin/env python3
"""Fetch a fixed Apache SedonaDB revision and apply the reviewed DF55 port."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".deps" / "sedona-db"
REVISION = "0a1993d9be8bcf52150593ad08fc6a3412d50f29"
PATCH = ROOT / "patches" / "datafusion-55.patch"


def git(*args):
    return subprocess.run(["git", "-C", str(SOURCE), *args], check=True)


if not SOURCE.exists():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout",
         "https://github.com/apache/sedona-db.git", str(SOURCE)],
        check=True,
    )
    git("checkout", "--detach", REVISION)
else:
    actual = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != REVISION:
        raise SystemExit(f"Expected Apache SedonaDB {REVISION}, found {actual}")

applied = subprocess.run(
    ["git", "-C", str(SOURCE), "apply", "--reverse", "--check", str(PATCH)],
    capture_output=True,
).returncode == 0
if not applied:
    git("apply", "--check", str(PATCH))
    git("apply", str(PATCH))

# A reversible patch alone does not prove that unrelated source was unchanged.
# Construct the expected patched tree with an isolated index, without resetting
# the checkout or touching its own index, and compare every tracked source file.
with tempfile.TemporaryDirectory(prefix="sail-sedona-source-") as temporary:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
    command = ["git", "-C", str(SOURCE)]
    subprocess.run(command + ["read-tree", REVISION], env=env, check=True)
    subprocess.run(command + ["apply", "--cached", str(PATCH)], env=env, check=True)
    expected = subprocess.check_output(command + ["write-tree"], env=env, text=True).strip()
    subprocess.run(command + ["diff", "--exit-code", expected, "--"], check=True)
    extras = subprocess.check_output(
        command + ["ls-files", "--others", "--exclude-standard"], text=True
    ).strip()
    if extras:
        raise SystemExit(f"Unexpected untracked files in pinned SedonaDB source:\n{extras}")
print(f"Apache SedonaDB {REVISION}, DF55 patch ready at {SOURCE}")
```

### Complete SedonaDB compatibility patch {#code-listings--listing-sedona-patch}

Source: [examples/extensions/sedona/patches/datafusion-55.patch](#code-listings--listing-sedona-patch). 111 lines.

```diff
diff --git a/Cargo.toml b/Cargo.toml
index 4f7c991..4d01e6a 100644
--- a/Cargo.toml
+++ b/Cargo.toml
@@ -71,14 +71,14 @@ categories = ["science::geo", "database"]
 adbc_core = ">=0.24.0"
 adbc_ffi = ">=0.24.0"
 approx = "0.5"
-arrow = { version = "58.3.0", features = ["prettyprint", "ffi", "chrono-tz"] }
-arrow-array = { version = "58.3.0" }
-arrow-buffer = { version = "58.3.0" }
-arrow-cast = { version = "58.3.0" }
-arrow-data = { version = "58.3.0" }
-arrow-ipc = { version = "58.3.0" }
-arrow-json = { version = "58.3.0" }
-arrow-schema = { version = "58.3.0" }
+arrow = { version = "=59.3.0", features = ["prettyprint", "ffi", "chrono-tz"] }
+arrow-array = { version = "=59.3.0" }
+arrow-buffer = { version = "=59.3.0" }
+arrow-cast = { version = "=59.3.0" }
+arrow-data = { version = "=59.3.0" }
+arrow-ipc = { version = "=59.3.0" }
+arrow-json = { version = "=59.3.0" }
+arrow-schema = { version = "=59.3.0" }
 async-trait = { version = "0.1.87" }
 bytemuck = "1.25"
 byteorder = "1"
@@ -86,21 +86,21 @@ bytes = "1.11"
 chrono = { version = "0.4.41", default-features = false }
 comfy-table = { version = "8.0" }
 criterion = { version = "0.8", features = ["html_reports"] }
-datafusion = { version = "54.1.0", default-features = false }
-datafusion-catalog = { version = "54.1.0" }
-datafusion-common = { version = "54.1.0", default-features = false }
-datafusion-common-runtime = { version = "54.1.0", default-features = false }
-datafusion-proto = { version = "54.1.0", default-features = false }
-datafusion-datasource = { version = "54.1.0", default-features = false }
-datafusion-datasource-parquet = { version = "54.1.0" }
-datafusion-execution = { version = "54.1.0", default-features = false }
-datafusion-expr = { version = "54.1.0", default-features = false }
-datafusion-ffi = {  version = "54.1.0" }
-datafusion-optimizer = { version = "54.1.0" }
-datafusion-physical-expr = { version = "54.1.0" }
-datafusion-physical-plan = { version = "54.1.0" }
-datafusion-pruning = { version = "54.1.0" }
-datafusion-session = { version = "54.1.0" }
+datafusion = { version = "=55.1.0", default-features = false }
+datafusion-catalog = { version = "=55.1.0" }
+datafusion-common = { version = "=55.1.0", default-features = false }
+datafusion-common-runtime = { version = "=55.1.0", default-features = false }
+datafusion-proto = { version = "=55.1.0", default-features = false }
+datafusion-datasource = { version = "=55.1.0", default-features = false }
+datafusion-datasource-parquet = { version = "=55.1.0" }
+datafusion-execution = { version = "=55.1.0", default-features = false }
+datafusion-expr = { version = "=55.1.0", default-features = false }
+datafusion-ffi = {  version = "=55.1.0" }
+datafusion-optimizer = { version = "=55.1.0" }
+datafusion-physical-expr = { version = "=55.1.0" }
+datafusion-physical-plan = { version = "=55.1.0" }
+datafusion-pruning = { version = "=55.1.0" }
+datafusion-session = { version = "=55.1.0" }
 dirs = "7.0.0"
 env_logger = "0.11"
 fastrand = "2.4"
@@ -122,8 +122,8 @@ num-traits = { version = "0.2", default-features = false, features = ["libm"] }
 object_store = { version = "0.13.2", default-features = false }
 once_cell = "1.20"
 parking_lot = "0.12"
-parquet = { version = "58.3.0", default-features = false, features = ["arrow", "async", "geospatial", "object_store"] }
-parquet-geospatial = { version = "58.3.0" }
+parquet = { version = "=59.3.0", default-features = false, features = ["arrow", "async", "geospatial", "object_store"] }
+parquet-geospatial = { version = "=59.3.0" }
 pin-project-lite = "0.2"
 prost = "0.14.1"
 pyo3 = { version = "0.29.0" }
diff --git a/rust/sedona-functions/src/st_envelope_agg.rs b/rust/sedona-functions/src/st_envelope_agg.rs
index 1b5f9ec..b4bc203 100644
--- a/rust/sedona-functions/src/st_envelope_agg.rs
+++ b/rust/sedona-functions/src/st_envelope_agg.rs
@@ -442,10 +442,29 @@ impl<T: WkbBounder2D + Default + 'static> GroupsAccumulator for BoundsGroupsAccu
         &mut self,
         values: &[ArrayRef],
         group_indices: &[usize],
-        opt_filter: Option<&arrow_array::BooleanArray>,
         total_num_groups: usize,
     ) -> Result<()> {
-        self.merge_state(values, group_indices, opt_filter, total_num_groups)
+        self.merge_state(values, group_indices, None, total_num_groups)
+    }
+
+    fn convert_to_state(
+        &self,
+        values: &[ArrayRef],
+        opt_filter: Option<&BooleanArray>,
+    ) -> Result<Vec<ArrayRef>> {
+        // The bypass path represents every input row as its own group, while
+        // preserving the normal update path's null and FILTER semantics.
+        let rows = values[0].len();
+        let groups: Vec<_> = (0..rows).collect();
+        let mut accumulator = Self::new(self.input_type.clone());
+        accumulator.execute_update(
+            values,
+            &groups,
+            opt_filter,
+            rows,
+            self.input_type.clone(),
+        )?;
+        accumulator.emit_state(EmitTo::All)
     }
 
     fn evaluate(&mut self, emit_to: EmitTo) -> Result<ArrayRef> {
```

### Original two-wheel build script {#code-listings--listing-build-script}

Source: [examples/extensions/scripts/build.sh](#code-listings--listing-build-script). 55 lines.

```bash
#!/usr/bin/env bash
# Reproducible local PoC: one host executable, two independent native wheels.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
base="$repo/examples/extensions"
venv=${SAIL_EXTENSION_VENV:-"$repo/.venv"}
target=${SAIL_EXTENSION_TARGET:-"$repo/target/extensions-poc"}
python=${SAIL_EXTENSION_PYTHON:-python3.12}
export CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0
export CARGO_BUILD_JOBS=${CARGO_BUILD_JOBS:-4}
df -h "$repo"
if [[ ! -x "$venv/bin/python" ]]; then
    uv venv --python "$python" "$venv"
fi
uv pip sync --python "$venv/bin/python" "$base/requirements.lock"
export PYO3_PYTHON="$venv/bin/python"
if [[ "$(uname -s)" == Darwin ]]; then
    export DYLD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
else
    export LD_LIBRARY_PATH=$("$venv/bin/python" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')
fi
"$venv/bin/python" "$base/sedona/scripts/prepare.py"
mkdir -p "$target/wheels"
for package in sedona nutmeg; do
    raw=$(mktemp -d "$target/raw-wheel-$package.XXXXXX")
    CARGO_TARGET_DIR="$target/$package" "$venv/bin/python" -m maturin build \
        --manifest-path "$base/$package/Cargo.toml" --locked --profile dev \
        --interpreter "$venv/bin/python" --out "$raw" --auditwheel repair
    if [[ "$(uname -s)" == Darwin ]]; then
        "$venv/bin/python" -m delocate.cmd.delocate_wheel -v -w "$raw/repaired" "$raw"/*.whl
        raw="$raw/repaired"
    fi
    for wheel in "$raw"/*.whl; do
        if [[ "$package" == sedona ]]; then
            "$venv/bin/python" "$base/scripts/check_wheel.py" "$wheel" \
                --output "$target/sedona-native-dependencies.json"
        fi
        # A repaired macOS wheel may acquire a newer minimum OS tag. Remove
        # stale variants of this package so pip cannot pick the unrepaired one.
        "$venv/bin/python" - "$wheel" "$target/wheels" <<'PY'
from pathlib import Path
import shutil
import sys
wheel, output = map(Path, sys.argv[1:])
for old in output.glob(wheel.name.split('-')[0] + '-*.whl'):
    old.unlink()
shutil.copy2(wheel, output / wheel.name)
PY
    done
done
uv pip install --python "$venv/bin/python" --reinstall "$target"/wheels/*.whl
# Pecan keeps its established source directory; its distribution is pyspark-pecan.
uv pip install --python "$venv/bin/python" --no-deps "$base/graph-algorithms"
CARGO_TARGET_DIR="$target/host" cargo build --manifest-path "$repo/Cargo.toml" --locked -p sail-cli
printf 'Host: %s\nPython: %s\nWheels: %s\n' "$target/host/debug/sail" "$venv/bin/python" "$target/wheels"
```

### Native wheel dependency check {#code-listings--listing-wheel-check}

Source: [examples/extensions/scripts/check\_wheel.py](#code-listings--listing-wheel-check). 65 lines.

```python
#!/usr/bin/env python3
"""Require the Sedona wheel's GEOS dependencies to resolve inside the wheel."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile


def check(wheel):
    with tempfile.TemporaryDirectory(prefix="sail-wheel-check-") as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        libraries = [path for path in root.rglob("*") if path.is_file() and
                     (path.name.endswith((".so", ".dylib")) or ".so." in path.name)]
        geos = [path for path in libraries if "geos" in path.name.lower()]
        if len(geos) < 2:
            raise RuntimeError("Sedona wheel must contain both GEOS C and C++ shared libraries")
        links = {}
        for library in libraries:
            if platform.system() == "Darwin":
                output = subprocess.check_output(["otool", "-L", str(library)], text=True)
                dependencies = [line.strip().split(" (", 1)[0] for line in output.splitlines()[1:]]
                # A dylib's own install ID appears in -L output but is not a dependency.
                ids = subprocess.check_output(["otool", "-D", str(library)], text=True).splitlines()[1:]
                dependencies = [name for name in dependencies if name not in ids]
                for name in dependencies:
                    if name.startswith(("/usr/lib/", "/System/Library/")):
                        continue
                    if not name.startswith("@loader_path/"):
                        raise RuntimeError(f"external native dependency in {library.name}: {name}")
                    resolved = (library.parent / name.removeprefix("@loader_path/")).resolve()
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        raise RuntimeError(f"unresolved bundled dependency: {name}")
            elif platform.system() == "Linux":
                output = subprocess.check_output(["patchelf", "--print-needed", str(library)], text=True)
                dependencies = output.splitlines()
                bundled = {path.name for path in libraries}
                for name in dependencies:
                    if "geos" in name.lower() and name not in bundled:
                        raise RuntimeError(f"external GEOS dependency in {library.name}: {name}")
                if library.name.startswith("_native"):
                    rpath = subprocess.check_output(["patchelf", "--print-rpath", str(library)], text=True)
                    if "$ORIGIN" not in rpath:
                        raise RuntimeError("native module lacks a wheel-relative library search path")
            else:
                raise RuntimeError("wheel dependency check supports macOS and Linux")
            links[str(library.relative_to(root))] = dependencies
        return {"wheel": wheel.name, "bundled_geos": [str(path.relative_to(root)) for path in geos],
                "dependencies": links}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(check(args.wheel), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    print(result, end="")
```

### Python dependency lock {#code-listings--listing-requirements}

Source: [examples/extensions/requirements.lock](#code-listings--listing-requirements). 69 lines.

```text
# This file was autogenerated by uv via the following command:
#    uv pip compile --universal --python .venv/bin/python examples/extensions/requirements.in -o examples/extensions/requirements.lock
altgraph==0.17.5 ; sys_platform == 'darwin'
    # via macholib
apache-sedona==1.8.0
    # via -r examples/extensions/requirements.in
attrs==26.1.0
    # via apache-sedona
colorama==0.4.6 ; sys_platform == 'win32'
    # via pytest
delocate==0.13.0 ; sys_platform == 'darwin'
    # via -r examples/extensions/requirements.in
googleapis-common-protos==1.75.4
    # via
    #   grpcio-status
    #   pyspark
grpcio==1.84.0
    # via
    #   grpcio-status
    #   pyspark
grpcio-status==1.84.0
    # via pyspark
iniconfig==2.3.0
    # via pytest
macholib==1.16.4 ; sys_platform == 'darwin'
    # via delocate
maturin==1.9.6
    # via -r examples/extensions/requirements.in
numpy==2.5.3
    # via
    #   pandas
    #   pyspark
    #   shapely
packaging==26.3
    # via
    #   delocate
    #   pytest
pandas==3.0.6
    # via pyspark
pluggy==1.6.0
    # via pytest
protobuf==7.36.2
    # via
    #   googleapis-common-protos
    #   grpcio-status
py4j==0.10.9.9
    # via pyspark
pyarrow==21.0.0
    # via
    #   -r examples/extensions/requirements.in
    #   pyspark
pygments==2.21.0
    # via pytest
pyspark==4.0.1
    # via -r examples/extensions/requirements.in
pytest==8.4.2
    # via -r examples/extensions/requirements.in
python-dateutil==2.9.0.post0
    # via pandas
shapely==2.1.2
    # via apache-sedona
six==1.17.0
    # via python-dateutil
typing-extensions==4.16.0
    # via
    #   delocate
    #   grpcio
tzdata==2026.4 ; sys_platform == 'emscripten' or sys_platform == 'win32'
    # via pandas
```

### Complete relation envelope {#code-listings--listing-protocol}

Source: [crates/sail-spark-connect/proto/sail/extension/v1/extension.proto](#code-listings--listing-protocol). 20 lines.

```protobuf
// Experimental local-mode protocol. This schema is a wire contract, not a native ABI.
syntax = "proto3";
package sail.extension.v1;

import "spark/connect/base.proto";
import "spark/connect/expressions.proto";

// Pack into Relation.extension with type URL:
// type.googleapis.com/sail.extension.v1.SailExtensionRequest
message SailExtensionRequest {
  string payload_type_url = 1;
  bytes payload = 2;
  // Only Plan.root is accepted. Names are restored to the input DataFrame's
  // user-facing names before the native handler receives a physical plan.
  repeated spark.connect.Plan inputs = 3;
  // Reserved by the proposal; this PoC rejects any occurrence of this field.
  repeated spark.connect.Expression input_expressions = 4;
  // Required value: 1. An omitted proto3 value (0) is rejected.
  uint32 envelope_version = 5;
}
```

### Complete optional resource ABI {#code-listings--listing-resource-abi}

Source: [crates/sail-native-resource-ffi/src/lib.rs](#code-listings--listing-resource-abi). 160 lines.

```rust
//! The small C ABI shared by independently compiled native extensions and Sail.
//! An opaque, prepaid memory lease crosses the boundary; Rust ownership and
//! allocator layouts stay entirely inside the library that issued the lease.
use std::ffi::{CStr, c_void};
use std::fmt::{Debug, Formatter};
use std::ptr::NonNull;
use std::sync::Arc;

pub const MEMORY_LEASE_CAPSULE: &CStr = c"sail_native_memory_lease_v1";

#[repr(C)]
struct Header {
    version: u32,
    size: u32,
}

/// A non-spillable host admission retained until the final clone is released.
///
/// Callbacks must be thread-safe and must never unwind. Every instance owns one
/// reference. A consumer may inspect the header before touching versioned fields.
#[repr(C)]
pub struct MemoryLease {
    header: Header,
    bytes: u64,
    opaque: *const c_void,
    retain: unsafe extern "C" fn(*const c_void),
    release: unsafe extern "C" fn(*const c_void),
}

// SAFETY: constructors require a Send + Sync owner; imports promise the same
// thread-safe callback contract. The opaque object is never accessed here.
unsafe impl Send for MemoryLease {}
unsafe impl Sync for MemoryLease {}

impl MemoryLease {
    /// Export ownership through callbacks compiled in the issuing library.
    pub fn new<T: Send + Sync + 'static>(owner: Arc<T>, bytes: u64) -> Self {
        unsafe extern "C" fn retain<T>(opaque: *const c_void) {
            // SAFETY: only new() constructs this token, from Arc<T>::into_raw.
            unsafe { Arc::<T>::increment_strong_count(opaque.cast::<T>()) };
        }
        unsafe extern "C" fn release<T>(opaque: *const c_void) {
            // SAFETY: each token owns one reference created by new()/retain().
            unsafe { drop(Arc::<T>::from_raw(opaque.cast::<T>())) };
        }
        Self {
            header: Header {
                version: 1,
                size: std::mem::size_of::<Self>() as u32,
            },
            bytes,
            opaque: Arc::into_raw(owner).cast::<c_void>(),
            retain: retain::<T>,
            release: release::<T>,
        }
    }

    /// Validate the ABI and quota, then take an independently releasable reference.
    ///
    /// # Safety
    /// `pointer` must address a readable, aligned header. A matching header must
    /// address a live MemoryLease with valid thread-safe, non-unwinding callbacks.
    /// Its issuing library must remain loaded until every imported clone is gone.
    pub unsafe fn import(
        pointer: NonNull<c_void>,
        expected_bytes: u64,
    ) -> Result<Self, &'static str> {
        // SAFETY: the caller guarantees at least the fixed header is readable.
        let header = unsafe { pointer.cast::<Header>().as_ref() };
        if header.version != 1 || header.size as usize != std::mem::size_of::<Self>() {
            return Err("native memory lease ABI mismatch");
        }
        // SAFETY: the validated header and caller's capsule contract cover Self.
        let lease = unsafe { pointer.cast::<Self>().as_ref() };
        if lease.bytes != expected_bytes || lease.opaque.is_null() {
            return Err("native memory lease quota mismatch");
        }
        Ok(lease.clone())
    }

    pub fn bytes(&self) -> u64 {
        self.bytes
    }
}

impl Clone for MemoryLease {
    fn clone(&self) -> Self {
        // SAFETY: self owns a live reference and callbacks obey the ABI contract.
        unsafe { (self.retain)(self.opaque) };
        Self {
            header: Header {
                version: self.header.version,
                size: self.header.size,
            },
            bytes: self.bytes,
            opaque: self.opaque,
            retain: self.retain,
            release: self.release,
        }
    }
}

impl Drop for MemoryLease {
    fn drop(&mut self) {
        // SAFETY: this instance owns exactly one reference, relinquished once.
        unsafe { (self.release)(self.opaque) };
    }
}

impl Debug for MemoryLease {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MemoryLease")
            .field("version", &self.header.version)
            .field("bytes", &self.bytes)
            .finish_non_exhaustive()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    struct Owner(Arc<AtomicUsize>);
    impl Drop for Owner {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    #[test]
    fn imports_validate_before_clone_and_release_only_the_final_owner() -> Result<(), &'static str>
    {
        let drops = Arc::new(AtomicUsize::new(0));
        let exported = MemoryLease::new(Arc::new(Owner(drops.clone())), 64);
        let pointer = NonNull::from(&exported).cast::<c_void>();
        // SAFETY: the exported lease remains alive during both imports.
        assert!(unsafe { MemoryLease::import(pointer, 65) }.is_err());
        let imported = unsafe { MemoryLease::import(pointer, 64) }?;
        drop(exported);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        let output_owner = imported.clone();
        drop(imported);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        std::thread::spawn(move || drop(output_owner))
            .join()
            .map_err(|_| "release thread failed")?;
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        let wrong = Header {
            version: 2,
            size: 8,
        };
        // SAFETY: a rejected version only reads the fixed header.
        assert!(
            unsafe { MemoryLease::import(NonNull::from(&wrong).cast::<c_void>(), 64) }.is_err()
        );
        Ok(())
    }
}
```

### Resource ABI crate manifest {#code-listings--listing-resource-cargo}

Source: [crates/sail-native-resource-ffi/Cargo.toml](#code-listings--listing-resource-cargo). 9 lines.

```toml
[package]
name = "sail-native-resource-ffi"
version = "0.1.0"
edition = "2024"
license = "Apache-2.0"
publish = false

[lints]
workspace = true
```

### Complete local server startup commands {#code-listings--listing-server-start}

Source: [examples/extensions/TUTORIAL.md](#code-listings--listing-server-start). 10 lines.

```bash
export PYTHONHOME="$(.venv/bin/python -c 'import sys; print(sys.base_prefix)')"
export PYTHONPATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
export DYLD_LIBRARY_PATH="$(.venv/bin/python -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR") or "")')"
export LD_LIBRARY_PATH="$DYLD_LIBRARY_PATH"
export SAIL_EXPERIMENTAL_EXTENSIONS=1
export SAIL_EXECUTION__DEFAULT_PARALLELISM=4
export SAIL_CLUSTER__WORKER_INITIAL_COUNT=2
export SAIL_CLUSTER__WORKER_MAX_COUNT=2
SAIL_MODE=local SAIL_EXPERIMENTAL_PROCESS_WORKERS=0 \
  target/extensions-poc/host/debug/sail spark server --ip 127.0.0.1 --port 50051
```
