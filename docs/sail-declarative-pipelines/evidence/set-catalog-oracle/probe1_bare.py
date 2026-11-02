from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("set-catalog-probe")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
print("VERSION", spark.version)
exprs = [
    "current_catalog()", "typeof(rand())", "rand()", "raise_error('x')", "typeof(raise_error('x'))",
    "assert_true(true)", "assert_true(false)", "typeof(current_catalog())", "CAST(1 DIV 0 AS STRING)",
    "1 DIV 0", "concat(current_catalog(), '')", "CASE WHEN false THEN current_catalog() ELSE 'spark_catalog' END",
    "date_format(current_date(), 'yyyy')", "explode(array('a'))", "(SELECT 'spark_catalog')",
    "CAST(raise_error('x') AS STRING)", "current_user()", "current_timezone()", "uuid()", "version()",
    "element_at(transform(array('spark_catalog'), x -> x), 1)",
]
for e in exprs:
    try:
        spark.sql(f"SET CATALOG {e}")
        print(f"PROBE {e} => ACCEPTED; current_catalog={spark.sql('SELECT current_catalog()').collect()[0][0]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None) or getattr(ex, "getErrorClass", None)
        cond = cond() if cond else None
        first = str(ex).splitlines()[0][:160]
        print(f"PROBE {e} => {cond}: {first}")
spark.stop()
