# Typed resolver native analysis

Sail `17b8ac254139e9213327dfcc7fc8badb4fdd27b2` on
`a74c3f429b092fd5cde6f65d36371760471a07f6` adds explicit
PlanResolver::with_scoped_query_session(&ScopedSession). A private Generic/Scoped
enum keeps the native analysis mode alongside the provider Session; last setter
wins. Existing generic with_query_session keeps native analysis on authority.
Persistent-view child resolvers copy the complete mode. A shared native helper
calls ScopedSession::analyze only for typed mode; legacy/generic retain their old
state capture and analyzer/config/observer. No as_any masquerade, optimizer
substitution or authority fallback from typed mode.

Delta replacement generated-column validation and procedure-predicate resolution
use this helper. Existing read/write/provider/collection paths still use the
selected dyn Session. No public caller, cluster, provider, catalog, JobService,
owned-router, SDK or CDC activation. Arbitrary custom rules do not gain I/O
supervision. Delta log-store lineage and re-resolution remain separate.

Exact detached fmt/strict all-target/all-feature Clippy/136 common-datafusion+
78 plan libraries pass (214). Earlier41aff40c5 passed136+76, before two generated
fixtures, and was not integrated. Seven added test families cover:

- Captured config7 and captured rule objects after authority config/rules change;
  constant Filter retained and zero optimizer-barrier calls.
- Typed custom analyzer cause reachable through PlanError/source/downcast.
- Legacy/generic authoritative native analysis and both last-setter orders.
- Actual procedure-predicate resolution using config7 after parent9, reaching the
  existing procedure factory sentinel with two scope-registered metadata reads.
- Actual catalog-backed generated-column replacement resolution in typed7 and
  generic9 modes, without physical planning, backend metadata I/O or mutation.

Authority-fallback control `26a1c234316c174c9110779627d760421872ccc3` changes
only the typed helper branch to authoritative analysis. The seven unchanged
tests yield2pass/5fail: generic cases pass; captured rule-identity/counter and
actual command config assertions fail. Raw failures and source are retained.
No new scheduling/concurrency mechanism is added, so no new optimized stress
verdict is claimed. These are analyzer/routing checks, not live Delta effects,
public CLI acceptance or original Scala-suite qualification. Latest fresh public
CLI verdict remains09d2f0cb8 (300 selected+67 upstream).

SHA256.json covers packet files except itself. Historical absolute paths and
qualifier assume advancement-time parent/output state; replay only in fresh
worktrees/output directories rather than overwriting retained evidence.
