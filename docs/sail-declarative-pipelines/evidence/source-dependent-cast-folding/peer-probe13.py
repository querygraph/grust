"""Probe 13: Spark 4.2.1 string -> numeric CAST / TRY_CAST oracle over a parquet
column (so no plan-time folding), ANSI and legacy: malformed, special values,
whitespace, suffixes, hex, overflow, rounding, NaN/inf to decimal.
"""
import json
import os
import shutil
import tempfile

from pyspark.sql import SparkSession

INPUTS = [
    "bad", "", " ", "1.5", " 1.5 ", "1.5d", "1.5f", "1e3", "1e400", "-1e400",
    "0x10", "1_000", "NaN", "nan", "inf", "+inf", "-inf", "Infinity", "-Infinity",
    "1.235", "1.245", "-1.235", "123456", "99999.999", "1,000", "+1", "0.", ".5",
    "1e-400", "9" * 40,
]
TARGETS = ["DOUBLE", "FLOAT", "INT", "BIGINT", "DECIMAL(5,2)", "DECIMAL(38,10)"]

tmp = tempfile.mkdtemp(prefix="probe13-")
spark = (
    SparkSession.builder.master("local[1]")
    .config("spark.ui.enabled", "false")
    .config("spark.sql.shuffle.partitions", "1")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("ERROR")
path = os.path.join(tmp, "s")
spark.createDataFrame([(i, s) for i, s in enumerate(INPUTS)], "i int, s string").write.parquet(path)
spark.read.parquet(path).createOrReplaceTempView("t")


def one(sql):
    try:
        rows = spark.sql(sql).collect()
        return {"ok": True, "rows": {r[0]: (repr(r[1]) if r[1] is not None else None) for r in rows}}
    except Exception as e:  # noqa: BLE001
        msg = str(e).splitlines()[0]
        return {"ok": False, "error": f"{type(e).__name__}: {msg[:220]}"}


for ansi in (True, False):
    spark.conf.set("spark.sql.ansi.enabled", str(ansi).lower())
    for target in TARGETS:
        for fn in ("CAST", "TRY_CAST"):
            # whole-column cast: in ANSI a single bad row fails the whole query,
            # so also probe row by row for the per-input error condition.
            whole = one(f"SELECT i, {fn}(s AS {target}) FROM t ORDER BY i")
            per_row = {}
            if not whole["ok"]:
                for i, s in enumerate(INPUTS):
                    r = one(f"SELECT i, {fn}(s AS {target}) FROM t WHERE i = {i}")
                    per_row[i] = r["rows"].get(i) if r["ok"] else r["error"]
            print(json.dumps({"ansi": ansi, "target": target, "fn": fn, "input": INPUTS,
                              "whole": whole, "per_row": per_row}, default=str), flush=True)

spark.stop()
shutil.rmtree(tmp, ignore_errors=True)
