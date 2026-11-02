from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("string-arith-decimal-probe")
         .config("spark.ui.enabled", "false").getOrCreate())
def run(sql):
    try:
        df = spark.sql(sql)
        rows = df.collect()
        schema = [(f.name, f.dataType.simpleString(), f.nullable) for f in df.schema.fields]
        print(f"PROBE {sql} => {[tuple(r) for r in rows]} schema={schema}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {sql} => {type(ex).__name__} {cond}: {str(ex).splitlines()[0][:140]}")
queries = ["SELECT '7' / '2'", "SELECT '1' / '0'", "SELECT 1 / '0'", "SELECT '7' % '2'", "SELECT '7' DIV '2'", "SELECT 7 / '2'",
           "SELECT CAST(1 AS DECIMAL(10,2)) / CAST(3 AS DECIMAL(10,2))",
           "SELECT CAST(1 AS DECIMAL(10,0)) / CAST(3 AS DECIMAL(10,0))",
           "SELECT CAST(1 AS DECIMAL(38,0)) / CAST(3 AS DECIMAL(38,0))",
           "SELECT CAST(1 AS DECIMAL(10,2)) % CAST(3 AS DECIMAL(10,2))",
           "SELECT CAST(1 AS DECIMAL(10,2)) DIV CAST(3 AS DECIMAL(10,2))",
           "SELECT CAST(1 AS DECIMAL(10,2)) / 3",
           "SELECT CASE WHEN x > 0 THEN x ELSE 2 END AS c FROM VALUES (1) AS t(x)",
           "SELECT CASE WHEN x > 0 THEN x END AS c FROM VALUES (1) AS t(x)",
           "SELECT x / 2 AS d, x / y AS e FROM VALUES (CAST(1 AS DECIMAL(10,2)), CAST(2 AS DECIMAL(10,2))) AS t(x, y)"]
for ansi in ("true", "false"):
    spark.conf.set("spark.sql.ansi.enabled", ansi)
    print(f"=== ansi={ansi}")
    for q in queries:
        run(q)
spark.stop()
