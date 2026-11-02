from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("signed-zero-probe")
         .config("spark.ui.enabled", "false").getOrCreate())
def run(sql):
    try:
        rows = spark.sql(sql).collect()
        print(f"PROBE {sql} => {[tuple(r) for r in rows]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {sql} => {type(ex).__name__} {cond}: {str(ex).splitlines()[0][:120]}")
queries = ["SELECT 1.0 / -0.0", "SELECT 1 / CAST(-0.0 AS DOUBLE)", "SELECT 1 / CAST(-0.0 AS FLOAT)", "SELECT 1.0 % -0.0",
           "SELECT CAST(1 AS FLOAT) % CAST(-0.0 AS FLOAT)", "SELECT 1 DIV CAST(-0.0 AS DOUBLE)", "SELECT pmod(1.0, -0.0)",
           "SELECT 1 / CAST(-0.00 AS DECIMAL(3,2))", "SELECT CAST(-0.0 AS DOUBLE) = 0.0, nullif(CAST(-0.0 AS DOUBLE), 0.0)",
           "SELECT x / y FROM VALUES (CAST(1 AS DOUBLE), CAST(-0.0 AS DOUBLE)) AS t(x, y)",
           "SELECT 1.0 / CAST('NaN' AS DOUBLE), 1.0 % CAST('NaN' AS DOUBLE)", "SELECT typeof(1 / CAST(-0.0 AS FLOAT))",
           "SELECT -0.0 / 1.0, CAST(-0.0 AS DOUBLE) / 1"]
for ansi in ("true", "false"):
    spark.conf.set("spark.sql.ansi.enabled", ansi)
    print(f"=== ansi={ansi}")
    for q in queries:
        run(q)
spark.stop()
