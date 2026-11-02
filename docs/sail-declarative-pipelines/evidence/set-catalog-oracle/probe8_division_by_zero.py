from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("division-by-zero-probe")
         .config("spark.ui.enabled", "false").getOrCreate())
def run(sql):
    try:
        rows = spark.sql(sql).collect()
        print(f"PROBE {sql} => {[tuple(r) for r in rows]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        jcls = None
        je = getattr(ex, "java_exception", None) or getattr(ex, "_origin", None)
        try:
            jcls = je.getClass().getName() if je is not None else None
        except Exception:  # noqa: BLE001
            jcls = None
        print(f"PROBE {sql} => {type(ex).__name__} {cond} {jcls}: {str(ex).splitlines()[0][:150]}")
queries = ["SELECT 1 / 0", "SELECT 1 DIV 0", "SELECT 1 % 0", "SELECT pmod(1, 0)", "SELECT 1.5 / 0", "SELECT 1.0 % 0.0",
           "SELECT CAST(1.0 AS DOUBLE) % CAST(0.0 AS DOUBLE)", "SELECT CAST(NULL AS INT) / 0", "SELECT CAST(NULL AS INT) % 0",
           "SELECT CAST(NULL AS INT) DIV 0", "SELECT 1 / CAST(NULL AS INT)",
           "SELECT x / 0 FROM VALUES (1), (CAST(NULL AS INT)) AS t(x)", "SELECT x / y FROM VALUES (CAST(NULL AS INT), 0) AS t(x, y)",
           "SELECT x / y FROM VALUES (1, 0) AS t(x, y)", "SELECT x % y FROM VALUES (1, 0) AS t(x, y)",
           "SELECT CASE WHEN false THEN 1 / 0 ELSE 2 END", "SELECT coalesce(2, 1 / 0)", "SELECT typeof(1 / 0)",
           "SELECT try_divide(1, 0), try_mod(1, 0)", "SELECT CAST(1 / 0 AS STRING)"]
for ansi in ("true", "false"):
    spark.conf.set("spark.sql.ansi.enabled", ansi)
    print(f"=== ansi={ansi}")
    for q in queries:
        run(q)
spark.stop()
