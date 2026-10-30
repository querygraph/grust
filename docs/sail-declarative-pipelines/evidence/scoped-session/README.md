# Preserve captured planning state through the existing Session interface

Sail `b90c4fbbef8ed16dc59f2348898852e78e71d798` adds ScopedSession in the existing
common-datafusion session module. It owns an already-captured SessionState without
rebuilding it, attaches the exact supplied resource owner and implements the
existing DataFusion Session interface. A caller may supply an isolated object-store
registry, deriving RuntimeEnv while preserving shared pool/disk/cache resources.
Physical planning invokes the captured custom query planner with this Session view;
derived TaskContext sees the same scope, function maps, config and routed runtime.
No job admission, session commands or parent mutation is performed by this helper.

Four tests exercise native prepared-plan retention (private snapshot tested through
native command dispatch), config-sensitive UDF Arc/result retention, all four
nonempty function maps/physical rules/query planner/type registry, snapshot timing,
and a real provider scan through a custom query planner to a distinct memory store.
The scan admits its actual GET through the supplied scope and checks derived task
identity; the parent store and extension remain independent. as_any returns the
wrapper, never a disguised underlying SessionState.

Final fmt/strict all-target/all-feature Clippy,129 library tests and129 optimized
tests under ten joined busy workers pass. Final runtime bypass679da6a20 changes
only runtime_env: the identical provider test reads parent instead of child bytes
and fails at the actual content assertion. Builder reconstructionec54a6f2d changes
only construction: identical native prepared-plan and UDF tests fail separately.
The final negative controls have identical test blobs to the final fixed commit.
Source/log/binary qualification preceded conditional branch advancement.

All earlier attempts remain: dc9db5c16 fails compilation on ambiguous bytes AsRef
and a disallowed inherent catalog accessor;31ca43dee fails the test-only native
Statement import lint. The fix uses the existing Session trait's required catalog
interface, with Sail resolution still on CatalogManager, and the same local
expect(disallowed_types) native-path test pattern as Sail's variable resolver.
No lint suppression or alternate catalog resolution was added to product code.
5b644ea72 passes128 tests; ba469bec0 separates the prepared/UDF tests and passes129
library/optimized tests. Its runtime control86bc48b4d stops at an early registry
identity assertion, so it does not demonstrate an actual wrong-store scan; the
initial qualifier correctly refuses the stronger claim. Final b90 moves that
unchanged identity assertion after the scan and repeats all gates/controls.
Earlier builder controlb25d162c5 and all receipts are retained too.

This is a provider/physical-planner component, not a resolver/context activation.
Commands remain on authoritative SessionContext; callers choose the capture phase
after authority mutation. Native command dispatch is not implemented by this view.
Logical optimization/physical expression creation delegate to the preserved state;
custom callbacks that reach its original runtime remain an audit obligation.
Providers requiring SessionState downcasts need an explicit compatible seam.
Resolver helper queries, functions/table functions and all factories still need
routing audits. No production registry is installed; effect bounds/outcomes,
cluster/session joins and full original Spark4.2.1 acceptance remain open. Latest
public CLI verdict remainsa0a369baa (300 selected+67 upstream Python), not this SHA.

SHA256.json covers all packet files except itself. Absolute receipt/binary paths
identify advancement-time evidence; use fresh outputs for replay. Candidate/control
objects are retained under refs/sdp/evidence. No dependency change.
