# 6. Native memory {#module-6}

The [placement decision](05-placement.md) identifies the process that owns native
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
survive a later policy change. [Lifecycle and teardown](07-lifecycle.md) determine
what happens when an admitted owner does not finish promptly.
