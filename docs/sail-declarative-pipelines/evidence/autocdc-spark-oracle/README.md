# AutoCDC against Spark 4.2.1

Product commit `4389a3ede`, on root `5cc046a0c`, branch `work/sdp-initialization-intents`.

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
| `test_autocdc_semantics.py`    | 33 passed            | 33 passed |
| `test_autocdc_spark_suites.py` | 43 passed, 4 skipped | 47 passed |

The 4 skips are Sail-only: `ALTER` refusal on an enrolled table, refusing a format with no bounded read, Delta sources, and Iceberg targets. The Iceberg runtime for Spark 4.2 is not on Maven, so Iceberg has no oracle here.

The launcher sets `spark.sql.shuffle.partitions=2`: with Spark's default of 200, each stateful run takes about 30 seconds on two local cores.

Spark also accepts stateful queries before an AutoCDC merge, which Sail refused until this comparison: deduplication with and without a watermark, inner stream joins, and watermarked window aggregates. An aggregate without a watermark is refused by both.

These runs found two differences that were then fixed: a selection is checked before the sequence is evaluated, and a structured error ends with its SQLSTATE.

## What these files do not show

- Spark's `MemoryStream` is replaced by files. A file source batches differently, so the cases assert final state, not batch boundaries.
- Nothing here compares Delta commit contents, because the oracle has no Delta target.
- Error text is compared by condition, and for type changes by the two types. Other parameters are not compared.

## Other runs at the same commit

| Check                                            | Result                                                       |
| :----------------------------------------------- | :----------------------------------------------------------- |
| Whole Spark Python tree                          | 12124 passed, 0 failed, 1 error                              |
| AutoCDC in local-cluster mode, with S3 and Iggy  | 87 passed                                                    |
| Spark-verified tests on an Iceberg target        | 78 passed, 2 skipped                                         |
| AutoCDC on a Hive 4.0.1 metastore, `run-hive.sh` | 80 passed                                                    |
| SIGKILL during runs, `crash.py`                  | 24 on the memory catalog and 6 on Hive, every recovery exact |

The error is an ORC encoding failure reported at server stop, not a CDC test: see CF-0601.

The Iceberg row compares Sail's Iceberg path with expectations Spark verified on its test catalog. It is not Iceberg on Spark: the Iceberg 1.12 runtime for Spark 4.1 is binary-incompatible with 4.2.1, and running a nightly snapshot runtime needs the owner's approval.

## Audit

`audit.md` is the first classification, at `f0bd5320a`. `audit-strict.md` is the stricter second one. `audit-final.md` is the third: 190 cases, 172 covered, 11 partial, 0 missing, 7 not applicable, on stated judgement calls. Seven partial rows were closed after it by assertions it proposed, and it was not rerun. What remains is mainly the exact input set of a flow, which has no client surface, and a second catalog.

New assertions were not mutation tested. The 12 breakages of the product logic ran at `541d48b83`.
