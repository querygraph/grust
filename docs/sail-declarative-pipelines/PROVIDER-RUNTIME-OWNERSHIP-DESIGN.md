# Provider and runtime ownership checkpoint

Status: partial design; runtime-interruption prerequisite implemented at Sail
`9d83baa8ba77b947dcadbb8b2921309a667c8f97`. Provider hook choice and writer routing
are not implemented. This continues [multipart ownership](OWNED-MULTIPART-SUPERVISOR-DESIGN.md)
and [the earlier effect checkpoint](evidence/checkpoint-effect-adapter-design/README.md).

## Observed boundary and implemented prerequisite

The new [runtime-loss packet](evidence/owned-mutation-runtime-loss/README.md) records
an actual multipart publication followed by loss of only its provider runtime while
the response was held. The execution scope/drainer survived on another runtime.
Production before the fix retained a canceled JoinError but classified it retryable.
The exact unchanged regression fails; the fixed source passes it. Owned PUT has a
second real publication-before-runtime-loss regression.

TaskResourceScope now offers explicit spawn_mutation and completed-value run_mutation.
A lost or panicked mutation supervisor retains CommitStateUnknownError alongside its
original typed JoinError. Generic spawn/run remain generic; cooperative cancellation
that confirms settlement can drain cleanly. Normally returned factory errors retain
their existing classification: callers must classify their actual commit stage.
Owned PUT and the execution multipart adapter use the new registrations.

This proves a particular interruption boundary. It does not qualify all provider
failures, remote effects or shutdown. For example, a nested I/O task may fail while
its outer supervisor survives and returns a normal provider error. Multipart's
Complete-returned error mapping already conservatively marks that stage unknown;
PUT-returned error visibility remains an enclosing-protocol obligation. A lost outer
runtime can also leave a detached nested I/O task; failed drainage must retain the
namespace and reject automatic replay, never masquerade as a clean barrier.

## Current source facts

- DynamicObjectStoreRegistry caches Arc<dyn ObjectStore> by scheme, authority and
  optional session fingerprint. Dynamic entries are RuntimeAwareObjectStore over
  logging/lazy/raw providers. The default file entry is logging over LocalFileSystem;
  custom registration may supply any ObjectStore and bypass the runtime wrapper.
- Neither ObjectStore0.13.2 nor DataFusion55.2 ObjectStoreRegistry exposes as_any or
  a provider capability lookup. Downcasting the erased Arc is not an available seam.
- Session-specific registration/lookup currently has only unit-test call sites in
  Sail's crates. Do not claim session fingerprints already flow through every
  runtime lookup.
- RuntimeAwareObjectStore retains an inner client and its I/O Handle. PUT/creation/
  complete/abort spawn tasks on that handle. Part creation enters that runtime
  synchronously in caller order; returned part futures await tracked I/O tasks.
- RuntimeAwareMultipartUpload.abort uses a timed part wait, and Drop can spawn
  cleanup. Successful complete/abort set finished. Failed complete leaves finished
  false, so Drop can attempt abort despite uncertain publication.
- The new whole-lifetime supervisor is stronger than a plain outer forwarder: it
  retains the entire creation future, every returned part future, and the final
  complete/abort future. This may already join known nested I/O tasks on successful
  paths. That is a source-derived hypothesis to test, not a blanket qualification.
- RuntimeEnvFactory erases the registry into RuntimeEnv. Server mutators can replace
  RuntimeEnvBuilder's registry and later SessionStateBuilder's runtime/config.
  Typed metadata must match the final active registry, not an earlier default.

## Candidate A: explicit provider descriptors

Retain an immutable provider descriptor beside the legacy cached handle. Both must
share the same existing client/lazy cell and credentials; creating another client
per operation is not equivalent. A descriptor can retain raw/native capability,
its required runtime and a constructor for a lifetime-owned path. The shared cache
holds no mutable current-job owner. An operation registry overlay combines the
immutable descriptor with its own existing TaskResourceScope.

A typed resolver binding must survive session construction without a dependency
cycle. An execution-layer SessionExtension can wrap object-store metadata because
sail-execution already depends on common-datafusion and object-store. Session
construction may install it, then validate Arc identity against the final actual
registry at lookup. If a runtime/state mutator replaced the registry, stale metadata
must not silently route around it. Both server and worker construction and nested
operation overlays need explicit coverage.

Opaque custom registrations need an explicit capability/adapter path rather than
an invented downcast or an assumption that all futures join internal work. Existing
normal registration/read behavior must be preserved. A temporary unsupported owned
path is unfinished coverage, not the desired final state for supported custom stores.
The design must provide a concrete route for custom/local/provider tests too.

Directly registering a provider-runtime task in the existing scope could avoid a
forwarding task that itself detaches an I/O task on runtime loss. A future
spawn_mutation_on-style API would retain the actual I/O JoinHandle in that scope;
no fresh independent scope. No such API or registry change is selected by this
checkpoint. RuntimeManager must outlive all relevant drainage either way.

## Candidate B: retained-creation context for the known runtime wrapper

A narrower alternative is a crate-local Tokio task-local marker denoting that
multipart creation is inside a whole retained lifetime. It carries no job owner,
namespace or mutable session-global current-job state. Only a store-based prepared
supervisor helper would install it; ordinary calls preserve legacy behavior.

RuntimeAwareObjectStore would snapshot the marker before its runtime hop and
explicitly propagate it through creation on the I/O runtime, including nested
known wrappers. The resulting RuntimeAwareMultipartUpload would use an externally
owned lifetime mode. In that mode Drop would spawn no cleanup, and explicit abort
would join its tracked parts without treating a timeout as success. The outer
supervisor already owns the part and settlement futures. Failed completion would
remain uncertain without a hidden Drop abort of a possibly committed upload.

This could preserve the erased standard registry/session/custom-store resolution
path and avoid a broad capability side channel. It is also a contextual contract:
unknown wrappers that spawn tasks without propagating the marker can break it.
Task-local state is not automatically inherited by arbitrary Tokio tasks. Marker
propagation through each known runtime hop, full outer lifetime retention, and
absence of hidden cleanup must therefore be demonstrated, not assumed. The helper
must make it hard to create an externally owned raw handle without registering its
supervisor first. Provider-specific opaque work remains a qualification obligation.

This option is proposed for a small proof experiment, not implemented or selected.
It must be compared with explicit descriptors using actual source and held-provider
controls. Do not conflate a cleanup-mode marker with a mutable ambient job owner.

## Required discriminating proofs and incremental units

1. **Done:** interrupted owned mutation becomes nonretryable uncertainty while
   retaining JoinError; generic resources and normal returned failures unchanged.
2. Run the current whole supervisor against known nested RuntimeAware wrappers:
   hold creation/parts/complete/abort, lose observers, seal/cancel the scope, and
   distinguish joined futures from timeout/Drop work. Include a provider that
   publishes then returns complete error; record any implicit abort after it.
3. Choose and implement the smallest hook unit supported by those results. Preserve
   legacy runtime affinity and part order. Qualify double wrappers and custom/local
   stores; keep unsupported/unknown distinct from clean confirmed settlement.
4. Add isolated operation registry/context routing using RuntimeEnvBuilder's
   preservation path. Preserve IDs/config/extensions/all function maps, pool/disk,
   underlying caches and encryption registry; the new CacheManager container need
   not have the same Arc identity. Prove sibling operation isolation and final
   custom-mutator registry binding. Never alter a globally cached store's owner.
5. Route actual checkpoint sink writes and compensating operations. ParquetSink
   re-resolves through TaskContext.runtime_env, and its child-task/error paths must
   also be joined. Existing late-publication controls must become actual writer
   integration regressions before enabling cleanup-qualified deletion.
6. Qualify runtime loss, distributed workers and session/manager/transport teardown.
   A failed/uncertain drain must retain ownership metadata/prefix; a timeout or an
   observed read-back cannot establish cleanup or durable commit by itself.

Failure recovery also needs an explicit boundary: a typed failed abort/complete
report retains causes but is not a retained raw upload/recovery identity by itself.
If provider-qualified retry requires that state, preserve it under the failed
operation owner before claiming resumable cleanup. Neither candidate currently
supplies that recovery protocol; namespace retention alone must not be advertised
as proof of retryable multipart disposal.

No C0 byte-authority, B12 tie, Iggy position-store or CDC durability decision is
selected here. Full original Spark4.2.1 SDP acceptance remains the goal.
