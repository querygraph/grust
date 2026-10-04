# Sail extensions: the first contract {#intro}

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

## Three decisions, in order

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

## A thirty-minute review

Spend five minutes here and on the [decision map](extensions-review/overview.md),
fifteen on the [complete Sedona sample](extensions-review/code-listings.md#sample-path),
and ten choosing the first acceptance boundary. The main sample is 246 lines of
Rust, Python bootstrap and packaging plus the existing 20-line client. Build
support, tests and protocol/resource interfaces follow in full listings.

The example exports native scalar functions. Indexed spatial joins, session
`SET` propagation and the complete Sedona feature set remain outside it.
No new runtime or cluster qualification is claimed by this document build.

For a consecutive deeper reading, follow: [Module 1: Discovery](extensions-review/modules/01-discovery.md) → [Module 2: Functions](extensions-review/modules/02-functions.md) → [Module 3: Relations](extensions-review/modules/03-relations.md) → [Module 4: Commands](extensions-review/modules/04-commands.md) → [Module 5: Placement](extensions-review/modules/05-placement.md) → [Module 6: Memory](extensions-review/modules/06-memory.md) → [Module 7: Lifecycle](extensions-review/modules/07-lifecycle.md) → [Module 8: Compatibility](extensions-review/modules/08-compatibility.md).
Each chapter separates the proposed contract, current implementation,
alternatives and acceptance criteria.

**Review target:** `querygraph/sail` at `bd8ce9ae8839477e2c08a0475ab7900b115c5366`.
Later graph experiments and optimizations are outside this snapshot.
Continue with the [module and decision maps](extensions-review/overview.md).
The separate [host companion](extensions-host-review/manuscript.md) compares
plain Sail with the prototype and maps changes to their proposed owners.
