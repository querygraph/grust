# 4. Commands and receipts {#module-4}

[Relations](03-relations.md) describe work without executing it. Some operations,
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
[placement and replay](05-placement.md).
