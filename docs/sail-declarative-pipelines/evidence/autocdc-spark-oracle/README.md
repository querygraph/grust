# AutoCDC against Spark 4.2.1

Product commit `0b6f34dd2`, on root `5111f29c8`, branch `work/sdp-initialization-intents`.

Oracle: Spark 4.2.1 from PyPI, with `SharedTablesInMemoryRowLevelOperationTableCatalog` from Maven's `spark-catalyst_2.13-4.2.1-tests.jar` and `spark-sql_2.13-4.2.1-tests.jar`. This is the catalog Spark's own AutoCDC suites use, as `cat.ns1`.

## Why a test catalog

Spark 4.2.1 refuses a Delta target. All 15 semantics cases failed on Spark 4.2.1 with Delta 4.4.1 with `AUTOCDC_TARGET_DOES_NOT_SUPPORT_MERGE`, because Delta's table has no row-level operations in that combination. Sail accepts a Delta target, which is a difference and not a port. The in-memory catalog is the only target this oracle has, so these runs compare AutoCDC, not Delta.

## How to repeat it

Put the two test jars beside `on-jvm.py`, then:

```
python on-jvm.py OUT PORT path/to/test_autocdc_semantics.py
python on-jvm.py OUT PORT path/to/test_autocdc_spark_suites.py
```

The launcher sets `AUTOCDC_ORACLE_NAMESPACE=cat.ns1`, so each test file qualifies its tables and leaves out `format`. Use a free port: another server may hold 15002.

## Results

| File                           | Spark 4.2.1          | Sail      |
| :----------------------------- | :------------------- | :-------- |
| `test_autocdc_semantics.py`    | 27 passed            | 27 passed |
| `test_autocdc_spark_suites.py` | 41 passed, 4 skipped | 45 passed |

The 4 skips are Sail-only: `ALTER` refusal on an enrolled table, refusing a format with no bounded read, Delta sources, and Iceberg targets. The Iceberg runtime for Spark 4.2 is not on Maven, so Iceberg has no oracle here.

These runs found two differences that were then fixed: a selection is checked before the sequence is evaluated, and a structured error ends with its SQLSTATE.

## What these files do not show

- Spark's `MemoryStream` is replaced by files. A file source batches differently, so the cases assert final state, not batch boundaries.
- Nothing here compares Delta commit contents, because the oracle has no Delta target.
- Error text is compared by condition, and for type changes by the two types. Other parameters are not compared.

`audit.md` is the first classification, at `f0bd5320a`: 169 cases. `audit-strict.md` is the stricter second one: 190 cases, 135 covered, 47 partial, 1 missing, 7 not applicable. It proposes a test for each open row, and those were then applied and run on both engines. The rows were not formally reclassified afterwards.

Spark's nullability assertions stay in Rust, because a file source cannot declare a non-null column. New assertions were not mutation tested. The 12 breakages of the product logic ran at `541d48b83`.
