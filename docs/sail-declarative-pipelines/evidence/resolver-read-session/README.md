# Pass the selected Session into resolver read factories

Sail `ddd83d815c0bcb1ffaa6da2909b7328d91bca122`, parent2e7beda82, propagates the
optional borrowed query Session to read source factories, lake-relation creation
and native table-function provider creation. Registry/function lookup stays on
authoritative SessionContext. A private carrier borrows the selected view or boxes
one legacy ctx.state snapshot captured at the previous call phase; the captured
branch does not reconstruct/copy the state. Write/procedure factories remain open.

Four new tests exercise actual callbacks before physical planning. Direct and
format.path data sources admit an actual GET into the selected scope, reading the
selected store/config7 after parent config changes to9. Native UDTF lookup stays
authoritative: registered after view capture, its callback receives the selected
Session and spawns a scope-owned GET that drain joins. The fallback source callback
sees parent config9/store/no new scope. These are direct config-state mutations,
not SQL/RPC SET. Catalog-table/lake-relation opt-in paths are source-reviewed and
type-checked, not separately provider-qualified by new dedicated fixtures here.

Exact fmt/strict all-target/all-feature Clippy,46 library and46 optimized tests
under ten joined CPU-load workers pass. Unchanged control9990b5561 changes only
the carrier's selected branch to use authority: the three scoped factory tests
fail for missing scope while fallback passes (exit101,1 passed/3 failed). The
control's dead-code warning is retained, not treated as a passing strict-Clippy
verdict on that source. Exact source, identical factory-test blob, log and binary
checks preceded conditional branch advancement. No initial product/test failure
was encountered in this unit.

Rebuilt CLI at the same exact commit passes300 selected public+67 upstream Python
executions, Spark4.2.1, owned server exit0/no listener. This is a regression selection,
not original Scala acceptance. No public caller currently supplies the view; no
production owned registry, target effect, streaming/CDC or cluster path is activated.
Native authority/lookup is retained. Earlier metadata/catalog I/O, write/procedure/
row-level propagation, capture/execution transfer and full provider joins still
need their own qualification. No dependency change. SHA256.json covers packet
files except itself. Historical absolute paths/binary hashes identify advancement-
time evidence; replay into fresh outputs. Commit objects are retained under
refs/sdp/evidence. Historical linker unwind-size warning is preserved.
