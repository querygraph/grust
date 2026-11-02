import json, os, re, sys, shutil, subprocess
from pathlib import Path
from pyspark.sql import SparkSession
JARS=Path(__file__).parent
def session(out):
    for k in ["SPARK_REMOTE","SPARK_CONNECT_MODE_ENABLED","SPARK_LOCAL_REMOTE"]: os.environ.pop(k,None)
    os.environ["SPARK_LOCAL_IP"]="127.0.0.1"
    cp=":".join(str(JARS/j) for j in ["delta-spark_4.2_2.13-4.4.1.jar","delta-storage-4.4.1.jar"])
    s=(SparkSession.builder.remote("local[2]").appName("sdp-delta")
       .config("spark.sql.warehouse.dir",(out/"warehouse").as_uri())
       .config("spark.driver.extraClassPath",cp)
       .config("spark.sql.extensions","io.delta.sql.DeltaSparkSessionExtension")
       .config("spark.sql.catalog.spark_catalog","org.apache.spark.sql.delta.catalog.DeltaCatalog")
       .config("spark.databricks.delta.retentionDurationCheck.enabled","false")
       .getOrCreate())
    assert s.version=="4.2.1"
    return s
