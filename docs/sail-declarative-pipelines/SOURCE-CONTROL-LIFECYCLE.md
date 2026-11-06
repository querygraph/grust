# Bind live source requests to registration and execution lifetime

A checkpoint request can outlive its caller, source reader or task attempt. A
numeric identifier alone could therefore acknowledge the wrong reader after
replacement. Use an owner-scoped controller, a compiled source-partition address and
an opaque registration handle. The handle must match the current registration when
sending, acknowledging and unregistering.

Retain one current operation per source. Repeating its identifier returns the same
pending or completed result. A lower identifier is Stale, including a previous
success after a greater operation begins. A greater identifier while pending is
Busy; after completion it starts the next operation. This bounds retained state
without silently renaming uncertain work.

Closing the execution makes every new request Closed, including duplicates.
Pending receipts become Closed even if their command was already dequeued. A
successful receipt remains an immutable historical marker handoff, carrying its
original scope and registration. Cancellation cannot turn that historical fact
into authorization for another attempt.

An unexecuted declared source is NotReady while the job is live; output completion
or drop closes it. Source drop closes that registration. A replacement receives a
new token, and old handles become Stale. Duplicate active registrations and duplicate
compiled manifest identifiers are errors. Unknown addresses and invalid partitions
are rejected before enqueueing.

Validate successful acknowledgement and scope activity atomically after encoding the
marker. Otherwise cancellation can race with a false success. Use paused time and
explicit polls for ordering and idle-reader checks. Exercise old cleanup and late
acknowledgement against a replacement, plus timeout/retry and historical receipt
behavior. Do these rules prevent cross-execution effects while preserving observable
ordered handoffs? They establish live control, not replay or durable completion.
