# 7. Lifecycle and teardown {#module-7}

The [memory contract](06-memory.md) ends only when the final owner releases its
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
is already complete. Finally, [compatibility](08-compatibility.md) determines
which independently built extensions may safely participate in this protocol.
