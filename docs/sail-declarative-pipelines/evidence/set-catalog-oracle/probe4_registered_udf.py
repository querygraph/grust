from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType
spark = (SparkSession.builder.master("local[1]").appName("set-catalog-probe4")
         .config("spark.ui.enabled", "false").config("spark.sql.ansi.enabled", "true").getOrCreate())
spark.udf.register("det_identity", udf(lambda s: s, StringType()))
spark.udf.register("nondet_identity", udf(lambda s: s, StringType()).asNondeterministic())
def run(sql):
    try:
        spark.sql(sql)
        print(f"PROBE {sql} => ACCEPTED; current_catalog={spark.sql('SELECT current_catalog()').collect()[0][0]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        msg = " / ".join(l.strip() for l in str(ex).splitlines()[:3] if l.strip())[:300]
        print(f"PROBE {sql} => {cond}: {msg}")
for e in ["det_identity('spark_catalog')", "typeof(det_identity('x'))", "nondet_identity('spark_catalog')",
          "typeof(nondet_identity('x'))", "concat(det_identity('spark_'), 'catalog')"]:
    run(f"SET CATALOG {e}")
    run(f"SET CATALOG IDENTIFIER({e})")
run("SELECT IDENTIFIER(det_identity('x')) FROM (SELECT 1 AS x)")
run("SELECT IDENTIFIER(typeof(det_identity('x'))) FROM (SELECT 1 AS string)")
spark.stop()
