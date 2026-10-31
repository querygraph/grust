from pyspark.sql import SparkSession
spark = (SparkSession.builder.master("local[1]").appName("missing-catalog-sites")
         .config("spark.ui.enabled", "false").getOrCreate())
def run(label, fn):
    try:
        out = fn()
        print(f"PROBE {label} => OK {str(out)[:80]}")
    except Exception as ex:  # noqa: BLE001
        cond = getattr(ex, "getCondition", None)
        cond = cond() if cond else None
        print(f"PROBE {label} => {type(ex).__name__} {cond}: {' / '.join(l.strip() for l in str(ex).splitlines()[:2])[:200]}")
run("SET CATALOG missing", lambda: spark.sql("SET CATALOG missing"))
run("catalog.setCurrentCatalog('missing')", lambda: spark.catalog.setCurrentCatalog("missing"))
run("SELECT * FROM missing.db.t", lambda: spark.sql("SELECT * FROM missing.db.t").collect())
run("SHOW NAMESPACES IN missing", lambda: spark.sql("SHOW NAMESPACES IN missing").collect())
run("SHOW TABLES IN missing.db", lambda: spark.sql("SHOW TABLES IN missing.db").collect())
run("USE missing.db", lambda: spark.sql("USE missing.db"))
run("catalog.listTables('missing.db')", lambda: spark.catalog.listTables("missing.db"))
run("CREATE TABLE missing.db.t (x INT)", lambda: spark.sql("CREATE TABLE missing.db.t (x INT)"))
spark.stop()
