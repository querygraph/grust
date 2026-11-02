# Lake metadata and table-property callbacks use selected Session

Sail d6d802d223749e1be94a3c09cc449a0cbd6b108c on b30ec33fb changes only
three provider call sites: row-target infer_metadata and the path/catalog branches
of SHOW TBLPROPERTIES. Lookup/access authority stays unchanged. Six tests resolve
actual commands through the existing command dispatcher, checking selected scope,
task-context identity, store data and captured config7 after direct parent mutation
to9; legacy sees parent config/store and no new owner. Metadata GET runs inside the
selected owner, before any physical planner call. DELETE tests intentionally stop
at the subsequent source callback; no row operation is planned or executed.

Exact detached fmt/strict all-target/all-feature Clippy and55 plan library tests
pass. Six optimized metadata tests pass under ten joined CPU-load workers. Unchanged
03efd36c7 three-site bypass fails all three scoped cases while all three legacy
cases pass; test blobs identical. Qualifier checked exact source/log/binary hashes,
positive/negative counts and worker exits before conditional advancement.

Initial f6d6de58c fixture used private helpers from another resolver submodule;
21c0f0b65 then failed expect/expect_err lints; c9fd1aed6 failed panic lint. Those
failures are retained. Final fixture uses existing command entry and normal Result
propagation, preserving metadata assertions. Named catalog and format-path callbacks
are both exercised. No new dependency/public caller or effect activation.
Latest public CLI pin remains7723dc4de; no fresh CLI verdict for this helper change.
Other procedure/delta/row-operation callbacks, analyzer/capture/execution/session/
cluster/effect paths and full Spark4.2.1 SDP acceptance remain incomplete.

SHA256.json covers all packet files except itself. Historical absolute scripts and
receipts identify advancement-time evidence; replay into fresh outputs.
