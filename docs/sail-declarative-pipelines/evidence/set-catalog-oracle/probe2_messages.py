from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("set-catalog-probe2")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
exprs = ["typeof(raise_error('x'))", "typeof(current_catalog())", "(SELECT 'spark_catalog')", "current_user()",
         "date_format(current_date(), 'yyyy')", "current_timezone()", "version()", "CAST(typeof(1) AS STRING)",
         "IDENTIFIER(current_catalog())", "IDENTIFIER(typeof(current_catalog()))", "IDENTIFIER(raise_error('x'))"]
for e in exprs:
    try:
        spark.sql(f"SET CATALOG {e}")
        print(f"PROBE {e} => ACCEPTED; current_catalog={spark.sql('SELECT current_catalog()').collect()[0][0]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        msg = " / ".join(l.strip() for l in str(ex).splitlines()[:4] if l.strip())[:420]
        print(f"PROBE {e} => {cond}: {msg}")
spark.stop()
