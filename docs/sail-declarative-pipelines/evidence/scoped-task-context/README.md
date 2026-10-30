# Resource-scoped TaskContext adapter

Recorded 2026-10-30T03:34:56.255104+00:00. Sail `779cb136d988c759a381ea1ace6c2e7649e3dbbc` constructs a fresh resource scope and a derived TaskContext, retaining task/session IDs, configuration and other extensions, all four function registries, RuntimeEnv and memory-pool identity. Each derived context replaces an inherited parent resource scope rather than sharing its cancellation domain.

All85 common-datafusion library tests, formatting and strict Clippy pass. Two new tests seed nonempty scalar, higher-order, aggregate and window registries and compare every function Arc. They also verify parent/sibling cancellation isolation, runtime/pool identity and preserved configuration/IDs. There are no dependency/lock changes.

The adapter is committed independently from runner integration. It does not yet alter task monitors, job runners, upload cleanup or ORC writing. Raw gate logs and the exact two-file patch are inventoried by provenance.json. No new public SDP count is claimed.
