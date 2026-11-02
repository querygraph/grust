# Missing-catalog errors at explicit catalog loads

Product55c237c489d551bb82b1aa9da3d6b035ab4a57ca, parent
4761d0064b592f66647dec807801c57fcfc546c9, preserves typed catalog failures only
when CatalogCommandExec executes SetCurrentCatalog. The shared typed factory uses
Sail's existing quote_sql_identifier and StructuredSparkError. The Connect codec
emits Spark's measured five-class CatalogNotFoundException hierarchy, preserving
the native reason and PySpark's SparkException selection. No catalog provider,
manager, planner, serialized representation, dependencies or success path changes.
CommitStateUnknown and other command errors retain their existing paths.

Spark4.2.1's16-case oracle covers the Catalog API and public SQL, dotted/quoted/
non-ASCII/empty/malformed names, and namespace fallbacks. Source hashes and actual
installed runtime JAR hashes are recorded separately. Raw Connect error capture
records native reason/domain/classes/condition/SQLSTATE/parameters. The command
factory emits CATALOG_NOT_FOUND/42P08; malformed raw names retain Spark's
INVALID_ATTRIBUTE_NAME_SYNTAX, which comes from identifier parsing inside the
factory. Namespace resolution has different errors and must not be retagged.
Fable973788dd identified this scope boundary;885c91eb reviewed the final candidate
without a requested change. No flow runs or data writes occur.

Detached fmt, strict Clippy and439 libraries pass (140shared+15physical+104plan+
180Connect). Two controls make the unchanged metadata test fail0/1 independently when
corrupting the shared diagnostic condition or removing the measured superclass
hierarchy. A fresh CLI
passes300 selected public tests+67 upstream executions+4 existing parameter tests.
The same16 queries improve0→12 outcome/condition matches and0→12 complete public
metadata sets. All ten CATALOG_NOT_FOUND cases also match the native reason,
domain, five-class hierarchy and parsed metadata fields. The two invalid-name
cases still use Sail's existing single-class analysis hierarchy, an explicit wire
difference. Transient error IDs, JVM stacks and full message/origin equality are
not claimed as matching by this comparison.

The same48 catalog-phase cases improve28→33 behaviors, metadata8→13; earlier14
arithmetic cases improve6→8 behaviors, metadata3→5. All earlier positive matches
remain positive and all20 provenance observations are unchanged. The four remaining
16-case differences are Sail's USE CATALOG grammar extension versus Spark's parse
error and three namespace-resolution diagnostics. The three namespace errors,
including their public messages, are byte-identical to Sail's parent observations.
All remaining differences are retained. None of these selections qualifies full
original Scala SDP-suite acceptance.

attempt-01 preserves an initial test compilation failure from using the private
ErrorDetails.error_info field instead of its accessor. attempt-02 preserves the
broader generic planner mapping and its passing439-test gate, never advanced;
Spark's actual fallback semantics rejected that design despite its green gates.
The final planner and catalog crate trees are byte-identical to the parent.

verify.py checks source/artifact hashes, exact detached gates, unchanged test
blobs/controls, fresh CLI identity, probe accounting, preservation of namespace
errors and owned-server teardown. reference.py generated both16-case observations;
run-probe.py owns the immutable Sail server. controls-gates.py/runtime-gates.py
preserve orchestration. SHA256.json covers every retained file.
