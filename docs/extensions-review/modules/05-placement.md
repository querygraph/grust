# 5. Placement and replay {#module-5}

The [command contract](04-commands.md) makes an uncertain mutation outcome
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
the next question is [whose memory budget admits the native work](06-memory.md).
