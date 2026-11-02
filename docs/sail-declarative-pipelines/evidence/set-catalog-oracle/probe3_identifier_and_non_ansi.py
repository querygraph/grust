from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("set-catalog-probe3")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
def run(label, sql):
    try:
        spark.sql(sql)
        print(f"PROBE {label} => ACCEPTED; current_catalog={spark.sql('SELECT current_catalog()').collect()[0][0]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        msg = " / ".join(l.strip() for l in str(ex).splitlines()[:3] if l.strip())[:300]
        print(f"PROBE {label} => {cond}: {msg}")
for e in ["typeof(rand())", "1 DIV 0", "CAST(1 DIV 0 AS STRING)", "assert_true(true)", "assert_true(false)",
          "explode(array('a'))", "(SELECT 'spark_catalog')", "current_timezone()", "concat(current_catalog(), '')",
          "CASE WHEN false THEN current_catalog() ELSE 'spark_catalog' END", "rand()", "NULL", "1",
          "CAST(NULL AS STRING)", "'a.b'"]:
    run(f"IDENTIFIER({e})", f"SET CATALOG IDENTIFIER({e})")
for e in ["NULL", "1", "CAST(NULL AS STRING)", "'a.b'"]:
    run(f"bare {e}", f"SET CATALOG {e}")
spark.conf.set("spark.sql.ansi.enabled", "false")
for e in ["1 DIV 0", "CAST(1 DIV 0 AS STRING)", "IDENTIFIER(1 DIV 0)", "IDENTIFIER(CAST(1 DIV 0 AS STRING))"]:
    run(f"non-ANSI {e}", f"SET CATALOG {e}")
spark.stop()
