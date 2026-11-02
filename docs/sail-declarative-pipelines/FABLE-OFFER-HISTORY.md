# Historical Fable offers

Preserved from the coordinator handoff on 2026-10-30. This is the historical
offer/review ledger, not current integration state; use [FABLE-HANDOFF.md](../../FABLE-HANDOFF.md)
and the live coordination log for subsequent imports/corrections.

## Fable offers and integration state

Fable's starting Sail base is `779cb136d988c759a381ea1ace6c2e7649e3dbbc`.
Original offers: Grust1493d8a36 (columns kernel), Saild07a95c2c (vendor) and
Sail167d577c6 (CDC definition validation). Preserve them as evidence.
The original vendor-only commit puts a connect dependency edge in Cargo.lock
before its Cargo.toml declaration; assemble independently buildable vendor and
consumer units during integration rather than blindly cherry-picking that defect.

| Offered Sail commit | Work / present review state |
| --- | --- |
| `49f32b65d` C1 | Attribute/source identifiers. Exact parser matched JVM on 9,338 names; source/parser correction accepted at that boundary. |
| `29056716b` C3 | Sink rejection removed from graph validation; source phase correction accepted. |
| `f4537586b` C2 | Original ROOT lowercase model. Rejected: 1,332 mismatches in 39,215 independent contexts. Preserve failed evidence. |
| `a495cb02d` C4 | Caller-resolver kernel and Scala map-order adapter. 23,050 independent queries / 771 schemas match; 16 kernel tests, Clippy/fmt and exact vendor hashes pass. |
| `2dcd0eaa9` | Corrected JDK word-break iterator. 68,588 independent contexts match, including all earlier failures; combined 23,050 lookups also match. Common helper integrated atcae618d7f; CDC consumers still pending. |
| `550bb198a` C5 | First phase correction; rejected as incomplete global analysis-before-validation ordering. |
| `1eea0b140` C6 | Construction-test rename, real PySpark-produced wire fixture, opt-in lookup replay. Full source/evidence review pending. |
| `b7118b953` unit2a | Original-row validation before dedup; pure DataFusion component. Initial source reading performed, independent reference/edge review not finished. |
| `f7adb3f05` unit2b | Dedup using existing MaxByFunction/StructFunction; disclosed sail-function dependency edge. Independent review not finished. |
| `c9a0132cf` unit3 | Bounded deterministic source/intents/progress; cross-run incarnation and zero/stall findings raised. |
| `6620ee940` unit5 | Prepared-input manifest, canonical row order, receipt/content digests. New blocking review CF-0043, below. |
| `d38058973` | Opt-in external lowercase replay. Fable reports detached gate and both corpus replays; inspect exact evidence. |
| `769914891` | Offered C5/global-phase + incarnation-bound progress corrections. Fable reports 124 Rust pipeline / 249 Python pipeline tests and a detached verdict in CF-0045. Source-reviewed in CF-0058: fixes earlier checks/progress schedules; no new independent runtime verdict. Schema-merge/missing-source phase divergence and full failure-map semantics remain open. |
| `dc8b7eb31` | Prepared-input fixes: IPC schema encoding, manifest consistency checks, strict case labels and C4-bound keys at every row count; tested independently at the component boundary in the later source71e4a94d9. |
| `71e4a94d9` | Expected authoritative InputIdentity binding; Fable detached fmt/Clippy/common/pipeline/maturin/249 Python verdict CF-0052. Independent prepared-component review passes the stated API checks; physical IPC representation boundary remains open. |
| `33a883091` | Approved move-only lower bounded-source contract extraction; detached common/common-datafusion/Connect and249 Python gate CF-0062. Offered, not integrated. |
| `bc23c8db6` / `105967e17` | Typed per-flow report and callback carrier, unwired, detached gates CF-0070/0073. Source review CF-0071 requires retaining maps in the raised error, not dropping them when constructing its message. Not integrated. |
| `798cd35c9` | Retained report variant + actual AnalysisException Status mapping, detached gate CF-0078. Fixes source-level map loss; unwired/unintegrated. |
| `92ab01326` / `b61da2c98` | Typed merge-error prerequisite then C5 loop; the loop also corrects raw JVM renderer parameters (64 cases), preserves scopes via two constructor call-site edits, and leaves event diagnostics as strict xfail. Offered/unintegrated;133 Rust +265 Python/1 xfail gate. |
| `f93efc3c9` / `2561606e9` / `7962984be` | Source error-only types (no async conversion), phase6 no-flow ordering, phase4 table/streamingness predicate. Latest detached gate133 Rust +277 Python/1 xfail (CF-0102). Offered/unintegrated. |

Grust offers: kernel727baa3e; evidence5538854f/aba8ef64 (lowercase),31997f0f
(CDC validation),275e666b (microbatch),834cae55 (streaming/prepared),8b0bd605
(Iggy),f13e9b48 (corpus replay); draft88e48c03 (bounded admission). These objects
are in the shared Grust repository and files in the Fable docs worktree.
The coordination reader2103fb56 was integrated and fixed as Codexb7290eb1;
IDs/protocol foundation is16a0a7f4. Do not integrate that reader twice.

Peer event follow-up37c4d9c4a remains unintegrated; CF-0123 reports detached gates.
Earlier3ef4e238a detached gate passes; FIFO13e0d4f96's race/pytest exit1 remains
retained. HTTP entry fixes scheduling; latest source adds full setup cleanup,
joined-state assertions and Shared(Context) lines. Shared Status classification
needs a separate probe; message-only events do not qualify origin/WARN assertions.
