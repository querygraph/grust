# Positive dataset and Flow parser assertion ports

Test-only commit19b7e9c0527a1c48790909d7d0631b194f4fddb7 preserves original parser fixtures from Spark617618396087429b5627a86ce933bb0f5d6645cb. It adds native tests for six dataset declarations under both inherited syntaxes: columns (including nested nullability, comments and absent defaults/generation/identity), identity partitioning, comments, provider, IF NOT EXISTS and properties. It also preserves all three Flow declarations: optional comments, three multipart names, and the overwrite/dynamic-partition/BY NAME INSERT child and query equality.

Only cfg(test) modules changed relative tof998. Exact detached formatting/strict Clippy and40 analyzer tests pass. Runtime remainsc50ef2253; no fresh CLI/public run is claimed. Original Spark parser suites pass in the expanded-reference packet. Native representations differ: configured STRING storage, no top-level Spark ColumnDefinition metadata, and write privileges assigned at a later boundary. The overwrite parser fixture does not authorize overwrite registration/execution. Nine canonical sites become partial behavioral ports; no whole-suite or original-JVM-on-Sail verdict is promoted.

The pending7d7 clause-rejection production candidate is separate and failed its public filename-wrapper assertion. It contributes no accepted coverage here. Canonical accounting after this unit is486 declarations,109 reviewed,80 partial and406 unmapped.

The canonical inventory snapshot records accounting at this test-only increment. Its verifier binds that historical snapshot, so later accepted coverage does not invalidate this evidence. Current totals remain in the canonical inventory and latest handoff.
