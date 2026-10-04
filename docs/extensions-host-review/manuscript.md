# Host implementation: plain Sail and the extension prototype {#host-intro}

The [extension review guide](../EXTENSIONS-ONE-PAGER.md) describes the boundary
an extension author would use. This companion explains the changes inside Sail
that support the prototype, which responsibilities belong in the host, and
which implementation decisions remain open. Its comparison is deliberately
between named source revisions, not between an old fork and an assumed version
of upstream.

**PLAIN** means upstream `lakehq/sail` at
`4d31e15b350c975aed95c23e6cc7e7c51c59fe52`. **PROTOTYPE** means
`querygraph/sail` at `bd8ce9ae8839477e2c08a0475ab7900b115c5366`, the reviewed
`sail-extensions` revision. Their common ancestor is
`a85d912d72ae03a6d97b6a3fd151f5752da636c6`. The historical host patch runs from
that ancestor to PROTOTYPE. It records what the fork introduced; it is not a
patch prepared against PLAIN.

The current-source comparison below was made by reading both revisions.
No merge, build or runtime experiment was performed for this document. Source
structure can establish that a mechanism exists and where it lives; it cannot
qualify a rebased combination or prove a deployment's behavior.

## What the comparison actually says {#host-comparison}

PLAIN already has Spark Connect, DataFusion execution, catalogs, session
factories, distributed scheduling and extension mechanisms used internally by
Sail. It is not an engine without extensibility. The prototype adds a particular
route for independently packaged native extensions, including a constrained
stateful relation path.

| Concern | PLAIN at `4d31e15b` | PROTOTYPE at `bd8ce9ae` | Proposed decision destination |
|---|---|---|---|
| Embedding | Custom session factory is already public | Uses session construction to install extensions | Existing embedding seam; not a new prerequisite |
| Discovery | No `pysail.extensions` loader | Flag-gated wheel discovery and per-session binding | Session-layer integration |
| Native scalar codec | Existing explicit UDF codec and expression converter | Package identity and metadata-bearing field preservation | Generic codec invariants, then loader integration |
| Connect relations | Extension relation returns unsupported | Bounded envelope, registry and handler dispatch | Protocol and planner contract |
| Foreign inputs | No prototype-specific adapter | Original host context retained; partitions gathered | Host execution invariant; gathering remains a policy |
| Native placement | No driver-extension ownership node | Driver-owned references and one-attempt native regions | Scheduler implementation with explicit effect policy |
| Admission | Default runtime creation constructs a pool | Explicit shared domain plus prepaid native leases | Resource policy and small ownership ABI |
| Teardown | Existing driver/session shutdown | Terminal interruption, draining hooks and lease wait | Generic lifecycle fixes plus native policy |
| GraphUtils | No compiled-in graph utility adapter | Owned graph staging and helper functions | Separately scoped domain support |

These destinations are review proposals, not claims of upstream acceptance.
The [eight modules](../extensions-review/modules/01-discovery.md) separate the
public invariants from the particular types used to implement them.

## Preserve what current upstream already changed {#host-current-upstream}

The session-factory hook from #2630 is already in PLAIN.
`create_spark_session_manager_with_factory` accepts an embedder's factory, and
the normal constructor delegates to it. An embedder can wrap Sail's normal
configuration rather than replace its semantics. It should not be presented
as work still needed to enable the prototype.
[PLAIN session manager](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-spark-connect/src/session_manager.rs#L96).

Upstream has also advanced since the common ancestor. Its Spark session
initialization now seeds DataFusion's execution timezone from the resolved
Spark session timezone. Its planner prepares asynchronous functions; its UDF
codec includes the Jev async wrapper. Its job-graph planner materializes shared
file-scan build sides so a single-partition build can be scanned once and
broadcast. These are concrete changes in paths the prototype also touches,
not hypothetical future conflicts.
[PLAIN timezone initialization](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-spark-connect/src/session_manager.rs#L61),
[query planner](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-session/src/planner.rs),
[job-graph planner](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-execution/src/job_graph/planner.rs).

A future upstream change must retain those behaviors while adding the narrowly
chosen extension mechanism. Replacing a current file with its fork version
would not be such an integration. The historical patch is useful review
material precisely because its baseline remains explicit; applicability and
combined regression coverage are separate work.

## Discovery stays above execution {#host-discovery}

PROTOTYPE discovers `pysail.extensions` entry points when the flag is enabled,
reads manifests, validates exact API/DataFusion/Arrow declarations, checks
collisions, and binds fresh session state. Native objects cross named DataFusion
capsules. The loader retains package code for process lifetime and retains
session owners where native objects require them. Execution crates do not need
to discover Python packages themselves.
[PROTOTYPE loader](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/mod.rs).

PLAIN has a session-factory seam but not this package protocol. The proposed
addition is therefore a loader and registration policy, not the invention of
session customization. Name precedence, collision errors, partial-load failure
and worker installation requirements belong in the user-visible contract;
Python ownership wrappers and registry storage are implementation details.

This direction matches the upstream maintainer's preference for Python distribution and
DataFusion FFI, with independently scheduled releases and no public Sail Rust
trait. Exact version declarations and package fingerprints currently define a
narrow qualification boundary. They do not prove arbitrary capsule layouts safe
or establish a stable ABI range. Neither wheel installation nor content identity
replaces testing the supported artifact pair.
[Maintainer discussion](https://github.com/lakehq/sail/discussions/2001);
[compatibility module](../extensions-review/modules/08-compatibility.md).

## Registry and codec changes have different jobs {#host-codec}

PLAIN already resolves functions and serializes many built-in and Python UDF
variants. Its current decoder remains an explicit codec, not the prototype's
package-identity registry. PROTOTYPE adds `OwnedScalar`, retaining the native
owner and identifying the package/configuration and function. Workers resolve
that identity from installed code; pointers never travel in the plan.
[PLAIN codec](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-execution/src/proto/codec.rs#L3003),
[PROTOTYPE native registry](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-common-datafusion/src/native_scalar.rs#L70).

There is a second concern: preserving complete return fields, including their
metadata, while expressions cross the distributed codec. PROTOTYPE's converter
handles native scalars and metadata-bearing scalar, literal and cast expressions.
That invariant matters even when an ordinary builtin sits between native calls;
a package loader alone cannot preserve information the host codec discards.
[PROTOTYPE expression handling](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-execution/src/proto/native_expr.rs).

Review these changes separately: generic field-preservation tests can stand
without a loader, while package registration needs collision and identity tests.
Any port must preserve PLAIN's newer UDF behavior, including async wrappers.
Source inspection here does not establish that the historical wrapper composes
with every current function kind.

## Envelopes and foreign inputs need host boundaries {#host-inputs}

PLAIN explicitly rejects `Relation.extension`. PROTOTYPE decodes either an
allowed bare payload or a Sail envelope containing a typed payload and input
plans. It enforces envelope and payload sizes, input arity, type-URL length and
nesting limits before dispatching through a relation registry. The handler
returns a provider, not eagerly computed result rows.
[PLAIN dispatch](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-spark-connect/src/proto/plan.rs#L1339),
[PROTOTYPE decoder](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-spark-connect/src/proto/extension.rs).

The input adapter addresses a narrower runtime problem. DataFusion's foreign
context reconstruction does not retain all Sail services, so `HostInputExec`
executes and polls its child under the original host context and runtime.
It also installs `CoalescePartitionsExec`, exposing one gathered partition.
That gathering is the prototype's initial input policy, not an inherent
requirement of native interoperability.
[PROTOTYPE adapter](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-common-datafusion/src/connect_extension.rs#L125).

The upstream contract should preserve execution context, schemas, ownership and
truthful distribution properties. A later partition-preserving adapter must
satisfy those invariants explicitly. It should not be prevented by declaring
single-partition gathering permanent. Nor should the current adapter be read
as propagation of every host service into arbitrary foreign operators.

## Placement and retry must remain distinguishable {#host-placement}

PLAIN's scheduler uses the configured attempt limit for its task regions.
PROTOTYPE identifies regions containing `DriverExtensionExec` and limits them
to one attempt. A bound plan is referenced by owner and plan identifiers;
decoding validates liveness, ownership, input arity and schemas. This prevents
a worker from treating a driver-local reference as its own native state.
[PLAIN attempt policy](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-execution/src/driver/job_scheduler/core.rs#L249),
[PROTOTYPE attempt policy](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-execution/src/driver/job_scheduler/core.rs#L264).

The conservative rule protects opaque operations whose mutation may have
committed before an acknowledgement was lost. It includes reads because the
host lacks a general effect classification. It is not cross-request exactly-once
execution. Its cost is giving up otherwise useful retry opportunities.

Stateless foreign worker operators are a possible next design, before
replicated or recoverable native state. Replay-safe reads are another separate
choice. Neither requires exposing scheduler internals as a public SDK. The
review decision is whether this initial driver policy is acceptable, and what
evidence would justify an additional placement or replay class.
[Placement module](../extensions-review/modules/05-placement.md).

## Memory ownership changes admission semantics {#host-memory}

In PLAIN's default runtime factory, creating a runtime constructs a memory pool
from configuration; its mutator can subsequently customize the builder.
PROTOTYPE adds an explicitly owned admission domain. With extensions enabled,
the standard manager supplies its domain to sessions and in-process workers.
A separately started worker factory owns another domain.
[PLAIN runtime factory](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-session/src/runtime.rs#L42),
[PROTOTYPE domain](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/runtime/memory.rs).

The resource bridge prepays a non-spillable quota from that host pool and passes
an opaque lease to the extension. Participating state and exported buffers must
retain it until final storage release. The manifest currently restricts this
bridge to driver placement; it does not automatically admit worker scalar
allocations. Idle prepaid capacity stays reserved.

These are process-local admission domains, not a cgroup or machine limit.
Independent worker pools do not jointly enforce one physical-memory budget.
Pool configuration, process count and headroom for unaccounted runtime, Python
and transport allocations all matter. Even a correct reservation ledger is not
an RSS measurement.

The ownership invariant merits a small ABI review; prepayment and manager-wide
sharing merit a separate policy review. Hierarchical admission is a legitimate
alternative to prepayment. The unsafe case is independent promises against the
same capacity, not the mere existence of multiple pools.
[Memory module](../extensions-review/modules/06-memory.md).

## Lifecycle corrections extend beyond plugin loading {#host-lifecycle}

PLAIN shuts down drivers and the gateway through the session manager. PROTOTYPE
adds protocol-resource draining, rejection of late session work, native-release
tracking and cleanup tasks for sessions already removed from the live map.
Its executor gains a terminal interrupted state so reattachment can observe
interruption without retaining execution buffers. Python-owner destruction
acquires the GIL to avoid indefinitely deferred decrefs.
[PLAIN shutdown](https://github.com/lakehq/sail/blob/4d31e15b350c975aed95c23e6cc7e7c51c59fe52/crates/sail-session/src/session_manager/actor/core.rs#L120),
[PROTOTYPE shutdown](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/session_manager/actor/core.rs#L125).

Several corrections alter ordinary Sail paths without requiring the extension
flag. They should be proposed and tested as such, rather than described as
entirely isolated experimental code. The source includes focused regression
fixtures, but this document does not report a fresh run against PLAIN.

The native-release wait is unbounded. Cooperative cancellation and retaining
quota for surviving owners are the safety requirements; a timeout cannot
pretend those owners have stopped. Upstream must choose between continued
charged ownership after a reported shutdown failure, a stronger isolation model,
or termination of the owning process. That operational decision remains open
and must accompany any promise about bounded shutdown.
[Lifecycle module](../extensions-review/modules/07-lifecycle.md).

## Keep graph helpers distinct from a generic SDK {#host-domain-helpers}

PROTOTYPE also compiles GraphUtils into `sail-session`: graph-client staging,
owned run cleanup and helper functions. It deliberately uses the host's object
store and credentials rather than passing them into a wheel. Its configured
root and request type are domain-facing facilities, not necessities for every
extension.
[PROTOTYPE GraphUtils](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/graph_utils/mod.rs).

This distinction prevents the physical location of code from deciding its
architectural status. A helper can use generic host hooks while remaining a
separate integration. Sedona's metadata handling similarly demonstrates useful
requirements without making every geometry-specific decision part of the
core contract. Review generic invariants with small fixtures first, then review
the domain adapters that exercise them.

## A phased route to upstream review {#host-upstream-plan}

1. **Rebase the reasoning before the code.** Compare each proposed change with
   PLAIN, preserve newer upstream behavior, and identify the smallest current
   reproduction or missing interface. The historical patch is an inventory,
   not a merge verdict.
2. **Separate general corrections.** Propose lifecycle and field-preservation
   changes with regressions that do not require the full loader. State which
   ordinary execution paths change and test them on the proposed current tree.
3. **Review bounded host interfaces.** Settle envelope validation, handler
   dispatch, ownership and host-context guarantees. Review the resource ABI
   separately from admission-domain policy and shutdown deadlines.
4. **Integrate package loading and worker identity.** Define collision rules,
   qualified versions, failure before partial registration, and package
   installation expectations. Exercise real driver/worker codec round trips.
5. **Add policy and domain integrations deliberately.** Qualify the initial
   driver-only relation policy, then assess stateless worker execution and
   replay-safe classes independently. Keep GraphUtils and recoverable graph
   state outside the minimum SDK proposal.

Every proposed commit needs its own current-source tests; combinations need a
combined gate. Nothing here claims that the historical patch applies cleanly,
that all prototype choices should be upstreamed, or that source inspection
qualifies a cluster deployment. The goal is a reviewable host contract whose
implementation can evolve without forcing extensions to depend on Sail's
private session, scheduler or pool machinery.
