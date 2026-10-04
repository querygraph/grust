# From the brief to the design {#design-map}

The brief asks for three decisions. The following maps connect those decisions
to the eight parts of the existing prototype. Read them as an index of review
responsibilities: an implemented component can establish feasibility without
becoming part of the stable author-facing contract.

## The eight-module map {#module-map}

This retains Fable's module map, with the scope and choices made explicit.
The rows also provide the consecutive reading order.

| Module | Owner | Prototype status | Choice to review |
|---|---|---|---|
| [Module 1: Discovery and binding](modules/01-discovery.md) | Sail session integration; package author | Flag-gated Python entry points and per-session binding | Wheel discovery plus FFI, versus statically linked embedding or another package loader |
| [Module 2: Functions](modules/02-functions.md) | Extension; Sail registry and codec | Native scalar functions, including workers | Names, collisions, metadata and identity; later specialized planning needs a separate decision |
| [Module 3: Relations](modules/03-relations.md) | Sail Connect/planner; extension handler | Bounded envelope, driver-local provider | Explicit DataFrame inputs versus table-function or catalog-based invocation |
| [Module 4: Commands](modules/04-commands.md) | Extension execution; host outcome handling | Mutating relations emit receipts | Reuse the relation path versus a dedicated command entry point; effects remain explicit |
| [Module 5: Placement and replay](modules/05-placement.md) | Sail scheduler; extension declarations | Driver-native regions receive one attempt | Separate placement, state ownership and replay safety; preserve a path to worker operators |
| [Module 6: Native memory](modules/06-memory.md) | Sail admission; participating extension | Prepaid, non-spillable driver quota | Shared admission and lease lifetime versus the particular prepayment policy |
| [Module 7: Lifecycle and teardown](modules/07-lifecycle.md) | Sail session/executor lifecycle; native owner | Cleanup corrections; stuck-owner policy open | Cooperative cancellation, retained ownership and a bounded operational failure policy |
| [Module 8: Packaging and compatibility](modules/08-compatibility.md) | Package author; host/worker validation | Exact version pins and content identities | Initial tested combinations versus a future compatibility promise |

The scalar foundation primarily needs modules 1, 2 and 8, plus the applicable
ownership and cancellation behavior in module 7. The stateful relation surface
adds modules 3 to 6. This is a capability split, not a claim that memory or
lifecycle correctness can be omitted from scalar execution. Some generic codec
and lifecycle corrections apply with extension discovery disabled.

## The decision map {#decision-matrix}

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

## How this fits Sail's design

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

Continue to [Module 1: Discovery and binding](modules/01-discovery.md).
