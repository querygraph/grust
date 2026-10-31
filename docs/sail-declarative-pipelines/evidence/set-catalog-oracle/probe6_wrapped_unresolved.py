from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("wrapped-unresolved-probe")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
def run(sql):
    try:
        spark.sql(sql)
        print(f"PROBE {sql} => ACCEPTED; current_catalog={spark.sql('SELECT current_catalog()').collect()[0][0]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {sql} => {cond}: {' / '.join(l.strip() for l in str(ex).splitlines()[:2])[:220]}")
for sql in ["SET CATALOG IDENTIFIER(missing)", "SET CATALOG IDENTIFIER(concat(current_catalog(), missing))",
            "SET CATALOG IDENTIFIER(typeof(missing))", "SET CATALOG missing", "SET CATALOG `spark_catalog`",
            "SET CATALOG IDENTIFIER('spark_catalog')", "SET CATALOG IDENTIFIER(:p)", "SET CATALOG IDENTIFIER(CAST(NULL AS STRING))",
            "SELECT * FROM IDENTIFIER(missing)", "SELECT * FROM IDENTIFIER(concat(current_catalog(), missing))"]:
    run(sql)
spark.stop()
