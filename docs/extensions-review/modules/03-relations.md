# 3. Relations {#module-3}

[Scalar functions](02-functions.md) fit ordinary expressions. A graph algorithm
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
state, laziness alone is insufficient: [commands and receipts](04-commands.md)
make execution and acknowledgement explicit.
