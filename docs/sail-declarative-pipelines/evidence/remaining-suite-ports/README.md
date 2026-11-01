# Remaining suite ports

Sail `061c49208` adds file streams and the APITest port. `d521ca587` closes the divergences found by porting the rest of the suites in this lane. Both passed the native gate across 14 or 15 crates and frozen 300 + 67, with the harness in `evidence/spark-suite-ports/harness`.

Spark 4.2.1: the third port set 83 passed, 3 skipped; `test_api_suite.py` 15 of 15; the file stream tests 2 passed, 1 skipped.

**Whole tree.** `python/pysail/tests/spark` on `d521ca587` and on the `061c49208` binary, 12,321 tests: 0 newly failing, 14 newly passing. 114 failed and 17 errors remain on this binary, the same set with or without this change plus the 14 now fixed. These are from this external-server harness and missing optional modules (`duckdb`, `jedi`, `PIL`) or are pre-existing; they were not diagnosed.

**Correction.** One of the 114 was mine: a strict expected-failure marker covered the control case of `test_internal_batch_read_options_are_propagated`, which passes. So `d521ca587` landed with one failing pipelines test, because the landing check did not require a passing pipelines run. `73d5f5f99` fixes the marker and the pipelines directory is 824 passed, 0 failed, 14 strict expected failures. `land.sh` now requires that run on the exact commit.

**Changed outside pipelines, deliberately.** The memory catalog matches table and view names case-insensitively. A direct read of a local path that does not exist now fails with `PATH_NOT_FOUND`. `DEFAULT COLLATION` on an ordinary table is reported as not implemented rather than a syntax error. Three gold files changed, in error text only; the diff was read.

**Strict expected failures on Sail** (all pass on Spark): the 4 from `evidence/spark-suite-ports`, plus: three CLI tests, because Sail catalogs are per session; column constraints are a syntax error, four cases; a batch read of a graph dataset ignores its read options; duplicate unqualified columns are refused while resolving a flow; a closed session lacks `INVALID_HANDLE.SESSION_CLOSED`.

**Differences that are not tested as failures.** A console sink discards its rows and prints nothing. A memory sink is a parquet directory under storage behind a temporary view. `maxFilesPerTrigger` is parsed, not applied; a run is one batch. File streams from partitioned directories keep no partition columns.
