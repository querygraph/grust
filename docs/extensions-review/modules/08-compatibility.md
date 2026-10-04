# 8. Packaging and compatibility {#module-8}

The [lifecycle contract](07-lifecycle.md) assumes that both sides interpret their
shared objects correctly. Packaging makes an extension discoverable;
compatibility determines whether Sail may call into it. Those are related
concerns, but a wheel that installs successfully is not by itself evidence
that its native boundary is compatible.

The public contract should identify the supported extension API and native
interchange versions, reject declared incompatibility before accessing capsule
layouts, and define package identity consistently across driver and workers.
It must also make the trust boundary explicit: native packages promise the
named capsule layout and ownership rules. Their declarations are not a proof
that arbitrary native code is safe. Function pointers remain process-local;
workers resolve their installed implementation from a serialized identity.

At `bd8ce9ae`, the loader accepts `api_version: 1`, DataFusion 55.1.0 and Arrow
59.3.0, checking these declarations before binding native objects. Its
[manifest checks](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/manifest.rs#L31)
are deliberately exact. The
[package fingerprint](https://github.com/querygraph/sail/blob/bd8ce9ae8839477e2c08a0475ab7900b115c5366/crates/sail-session/src/extensions/package_identity.py)
combines manifest options and installed package-file contents. It detects a
different installed package identity; it is not a universal ABI certificate,
an approved-artifact signature, or a fingerprint of every external dependency.
Sail does not distribute extension wheels to workers. Operators must install
matching packages there.

This is a qualified prototype boundary, not a promise that extensions must
forever share Sail's release cadence. The upstream maintainer's
[extension design response](https://github.com/lakehq/sail/discussions/2001)
explicitly favors Python distribution and DataFusion FFI so Sail and extensions
can release independently, while treating session mutators as implementation
details. Avoiding a public Sail Rust trait supports that direction. Exact pins
currently limit the demonstrated compatibility; they do not establish the
range that a future stable interface could support.

A tested compatibility range would reduce rebuilds but needs evidence for
every admitted boundary and a policy for breaking changes. Exact artifact pairs
are easier to qualify initially and can fail closed when declarations differ.
A custom C ABI could provide another stability boundary, but requires its own
versioning and ownership design. It is an alternative with maintenance costs,
not an impossibility ruled out by choosing wheels.

Acceptance should include wrong API and engine-version declarations, invalid
capsule names or types, missing worker packages, and changed package identities. Positive
controls should exercise the qualified artifacts across the actual planning,
codec and execution path. Only those tested pairs should be advertised as
supported; matching version strings alone cannot extend the claim.

The decision is the initial support statement and the evidence required to
widen it. With the eight boundaries explicit, the [code listings](../code-listings.md)
show the concrete extension surface reviewers can inspect next.
