"""Probe 12: does a failing foldable CAST under a lazy operator surface in Spark
4.2.1, and does the answer depend on the source (VALUES vs parquet) and on
whether the whole expression is foldable?  Run with the pinned venv, local[1].
"""
import json
import os
import shutil
import tempfile

from pyspark.sql import SparkSession

tmp = tempfile.mkdtemp(prefix="probe12-")
spark = (
    SparkSession.builder.master("local[1]")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", "1")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
pq_null = os.path.join(tmp, "d_null")
pq_zero = os.path.join(tmp, "d_zero")
spark.createDataFrame([(None,)], "d int").write.parquet(pq_null)
spark.createDataFrame([(0,)], "d int").write.parquet(pq_zero)
spark.read.parquet(pq_null).createOrReplaceTempView("pq_null")
spark.read.parquet(pq_zero).createOrReplaceTempView("pq_zero")


def run(sql):
    out = {"sql": sql}
    df = None
    try:
        df = spark.sql(sql)
        df.explain(extended=False)  # forces optimization without execution
        out["explain"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["explain"] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
        return out
    try:
        rows = df.collect()
        out["rows"] = [tuple(r) for r in rows]
        out["types"] = [f.dataType.simpleString() for f in df.schema.fields]
    except Exception as e:  # noqa: BLE001
        out["collect"] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
    return out


results = []
for ansi in (True, False):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    for target in ("INT", "DOUBLE", "DECIMAL(5,2)", "DECIMAL(38,10)"):
        cast = f"CAST('bad' AS {target})"
        cases = [
            ("values_null", f"SELECT {cast} / d AS v FROM VALUES (CAST(NULL AS INT)) AS t(d)"),
            ("parquet_null", f"SELECT {cast} / d AS v FROM pq_null"),
            ("parquet_zero", f"SELECT {cast} / d AS v FROM pq_zero"),
            ("foldable_null", f"SELECT {cast} / CAST(NULL AS INT) AS v"),
            ("foldable_null_over_parquet", f"SELECT {cast} / CAST(NULL AS INT) AS v FROM pq_null"),
            ("case_branch_parquet", f"SELECT CASE WHEN d IS NULL THEN 1 ELSE {cast} END AS v FROM pq_null"),
            ("identifier_null", f"SELECT 1 FROM IDENTIFIER(CAST({cast} / CAST(NULL AS INT) AS STRING))"),
        ]
        for name, sql in cases:
            r = run(sql)
            r.update({"ansi": ansi, "target": target, "case": name})
            results.append(r)
            print(json.dumps(r, default=str), flush=True)

spark.stop()
shutil.rmtree(tmp, ignore_errors=True)
