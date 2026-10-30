# Supplied listing schema preparation and partition reference

Sail `b52dfd5ad656d6caf2ae6900f3a25ed83874cdfd` adds a defaulted ReadFormat preparation hook before
partition extraction. Existing format behavior retains required/optional physical
inference, case reconciliation, empty-schema inference and file-only validation.
Formats may retain supplied names, ordering and explicit empty schemas while
deferring per-file checks. The hook is not called for an absent schema.

Five tests exercise defaults, inference failures, ambiguity and validation,
preserved nested metadata/nullability and empty-versus-absent handling. Exact
formatting, strict Clippy and all 189 data-source tests pass. Two prior attempts
are retained: three test-only Debug-bound compile errors, then formatting with
the wrong Rust edition. Neither ran Rust tests; assertions were preserved.

[Ten Spark schema cases and eleven filters](spark-reference/README.md) establish
the next shared listing requirements: retain omitted directory columns, use
supplied partition names/types under the captured case policy, make discovered
partitions nullable, and distinguish empty schema from absent schema. These
observations use two same-spelling string directories and native vectorized ORC;
they do not establish other partition types or mixed directory-key casing.

[The source handoff](partition-handoff/HANDOFF.md) proposes separate logical
partition fields and physical directory keys, with filter rebinding for parsing
and pruning. Its source pin is the first failed hook candidate, explicitly not
a gate verdict. The passing hook itself does not implement partition preparation
or binding fixes, register ORC or increase public SDP acceptance counts. Spark
source files retain their headers; root license and notice are included.
