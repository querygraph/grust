# Stable clock replayability review

Review of Fable d77fc47958641933e84577bfa88e3be5cfbd9471, before root
integration. Admission only tests Expr::is_volatile: DataFusion 55.2.0 checks
signature == Volatility::Volatile. Stable functions can change across query
executions. Sail TimestampNow is Stable and simplifies from the query execution
start time (source pinned to b30ec33fb); current_timestamp/now resolve to it.
The bounded-plan design explicitly requires current_timestamp non-replayable.

Independent test-only150611117 fails at the first now() item:9pass/1fail.
Separate test-onlyca2038b94 exercises date/time independently:9pass/2fail,
both clocks wrongly get replayable=true. Immutable arithmetic and the eight
existing admission cases pass. Production prefix before cfg(test) is identical
to offered d77; only fixtures added. No admission/target effect was activated.
Both detached runs exited101. Initial loop failure is preserved, not overwritten.

CF-0181 reports finding; CF-0182 ACKs correction on peer components/offered branches:
non-Immutable signatures, no name-only clock exception. Correction/replay and root
combined gate remain pending. This packet does not prove behavior of optimized
plans after functions were folded, or select C0 replay/staging authority.
SHA256.json covers all packet files except itself. Historical scripts use /tmp;
replay into fresh outputs rather than overwriting evidence.
