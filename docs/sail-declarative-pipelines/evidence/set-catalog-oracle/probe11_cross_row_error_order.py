from pyspark.sql import SparkSession
import sys
master = sys.argv[1] if len(sys.argv) > 1 else "local[1]"
spark = (SparkSession.builder.master(master).appName("cross-row-error-order")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
def run(label, sql, **conf):
    for k, v in conf.items():
        spark.conf.set(k, v)
    try:
        rows = spark.sql(sql).collect()
        print(f"PROBE {label} => {[tuple(r) for r in rows]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {label} => {type(ex).__name__} {cond}: {str(ex).splitlines()[0][:110]}")
# row 1: right ok, left raises USER_RAISED_EXCEPTION; row 2: right fails CAST_INVALID_INPUT
left_fails_first = ("SELECT (CASE WHEN a THEN CAST(raise_error('L') AS INT) ELSE 1 END) / CAST(b AS INT) "
                    "FROM VALUES (true, '1'), (false, 'y') AS t(a, b)")
right_fails_first = ("SELECT (CASE WHEN a THEN CAST(raise_error('L') AS INT) ELSE 1 END) / CAST(b AS INT) "
                     "FROM VALUES (false, 'y'), (true, '1') AS t(a, b)")
for codegen in ("true", "false"):
    run(f"{master} codegen={codegen} row1-left-fails", left_fails_first, **{"spark.sql.codegen.wholeStage": codegen})
    run(f"{master} codegen={codegen} row1-right-fails", right_fails_first, **{"spark.sql.codegen.wholeStage": codegen})
# same-partition order with a zero divisor on row 2 and a left failure on row 1 (both ANSI errors)
run(f"{master} row1-left-raise row2-div0", "SELECT (CASE WHEN a THEN CAST(raise_error('L') AS INT) ELSE 1 END) / b FROM VALUES (true, 1), (false, 0) AS t(a, b)")
run(f"{master} row1-div0 row2-left-raise", "SELECT (CASE WHEN a THEN CAST(raise_error('L') AS INT) ELSE 1 END) / b FROM VALUES (false, 0), (true, 1) AS t(a, b)")
# two partitions: which error surfaces
run(f"{master} 2 partitions left-raise vs cast", "SELECT (CASE WHEN a THEN CAST(raise_error('L') AS INT) ELSE 1 END) / CAST(b AS INT) FROM (SELECT /*+ REPARTITION(2) */ * FROM VALUES (true, '1'), (false, 'y') AS t(a, b))")
spark.stop()
