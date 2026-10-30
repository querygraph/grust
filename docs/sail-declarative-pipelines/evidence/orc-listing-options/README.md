# ORC listing options and session defaults

Sail `26b9461b93092ab99f1d5718fa82c73327970a27` separates generated planning options (mergeSchema and
pathGlobFilter) from the existing physical resource options and worker wire.
Resolution applies defaults, immutable session settings, table properties, then
operation layers. Explicit false and an empty glob remain overrides.

Connect initializes and refreshes the typed session defaults on set/unset. Earlier
SessionState snapshots and resolved options retain their values. ORC-affecting
multi-key changes refresh the mirror even if a later entry fails, preserving the
original error and existing partial-update behavior. The narrow lock-order audit
found no inverse held-lock path; no concurrency stress claim is made.

A new strict parser preserves Spark boolean syntax. Operations accept untrimmed
true/false using Java case equivalence; SQLConf first trims U+0000..U+0020.
The existing generic Sail parser is unchanged. The [finite reference](boolean-reference/README.md)
retains 34 Java/Scala calls, exact jar/source identities and terminal process
evidence; it did not start Spark. Four new data-source and six new Connect tests
cover precedence, lexical controls, snapshots and partial-failure ordering.

Formatting, strict Clippy, 206 data-source tests and 66 Connect tests pass on the
exact detached commit. Root and independent source reviews found no blocker.
No failed Rust gates occurred. The [frozen handoff](implementation/HANDOFF.md) records
scope; unsupported read-mode guarding and the private reader/registry remain
separate units. No public ORC or full SDP runtime result is added here.
