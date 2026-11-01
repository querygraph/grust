# AutoCDC against Spark 4.2.1

Product commit `541d48b83`, on root `be0881c80`, branch `work/sdp-initialization-intents`.

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
| `test_autocdc_semantics.py`    | 18 passed            | 18 passed |
| `test_autocdc_spark_suites.py` | 35 passed, 3 skipped | 38 passed |

The 3 skips are Sail-only: `ALTER` refusal on an enrolled table, refusing a format with no bounded read, and Delta sources, which need jars this oracle does not load.

## What these files do not show

- Spark's `MemoryStream` is replaced by files. A file source batches differently, so the cases assert final state, not batch boundaries.
- Nothing here compares Delta commit contents, because the oracle has no Delta target.
- Error text is compared by condition, and for type changes by the two types. Other parameters are not compared.

`audit.md` classifies every Spark AutoCDC test at the pin before this work's last additions: 169 cases, 130 covered, 29 partial, 3 missing, 7 not applicable. Its behaviour gaps were inferred from code. All five were then fixed and tested. Its partial and missing rows were not reclassified one by one afterwards.
