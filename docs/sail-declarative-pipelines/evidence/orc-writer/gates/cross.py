"""Each engine reads ORC files the other wrote. usage: cross.py WORKDIR SAIL_URL"""
import os, sys, shutil
from pathlib import Path
from pyspark.sql import SparkSession
for k in ['SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED','SPARK_LOCAL_REMOTE']: os.environ.pop(k,None)
os.environ['SPARK_LOCAL_IP']='127.0.0.1'
out=Path(sys.argv[1]); out.mkdir(exist_ok=False)
spark=SparkSession.builder.remote('local[2]').getOrCreate()
sail=SparkSession.builder.remote(sys.argv[2]).create()
assert spark.version=='4.2.1'
Q="SELECT id, id % 2 = 0 AS b, CAST(id % 100 AS TINYINT) t, CAST(id AS SMALLINT) s, CAST(id AS INT) i, CAST(id AS FLOAT) f, CAST(id AS DOUBLE) d, CAST(id AS STRING) x, CAST(CAST(id AS STRING) AS BINARY) y, DATE_ADD(DATE'2024-02-28', CAST(id AS INT)) dt, IF(id = 1, NULL, 'n') n FROM range(5000)"
fails=0
for codec in ['none','zlib','snappy','lz4','zstd']:
    for writer,reader,name in [(sail,spark,'sail-to-spark'),(spark,sail,'spark-to-sail')]:
        p=str(out/f'{name}-{codec}')
        writer.sql(Q).write.option('compression',codec).orc(p)
        a=sorted(map(tuple,writer.read.orc(p).collect())); b=sorted(map(tuple,reader.read.orc(p).collect()))
        same=a==b and writer.read.orc(p).schema==reader.read.orc(p).schema
        fails+=not same; print(name,codec,'rows',len(b),'OK' if same else 'DIFF')
p=str(out/'empty'); sail.range(0).write.orc(p); r=spark.read.orc(p); print('empty sail-to-spark',r.columns,r.count())
p=str(out/'multi'); sail.range(300000).repartition(4).write.orc(p); print('multi files',len([f for f in os.listdir(p) if f.endswith('.orc')]),spark.read.orc(p).count())
spark.stop(); print('FAILS',fails)
