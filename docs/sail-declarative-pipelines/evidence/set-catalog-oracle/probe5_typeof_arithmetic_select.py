from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("typeof-arithmetic-probe")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
def run(sql):
    try:
        rows = spark.sql(sql).collect()
        print(f"PROBE {sql} => {[tuple(r) for r in rows]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {sql} => {cond}: {str(ex).splitlines()[0][:160]}")
for sql in ["SELECT typeof(1 DIV 0)", "SELECT typeof(1 / 0)", "SELECT typeof(1 % 0)", "SELECT typeof(CAST(1 DIV 0 AS STRING))",
            "SELECT typeof(raise_error('x'))", "SELECT typeof(assert_true(false))", "SELECT 1 DIV 0",
            "SELECT typeof(1 DIV 0) FROM VALUES (1), (2) AS t(x)", "SELECT typeof(x DIV 0) FROM VALUES (1) AS t(x)",
            "SELECT IDENTIFIER(typeof(1 DIV 0)) FROM (SELECT 1 AS bigint)"]:
    run(sql)
spark.stop()
