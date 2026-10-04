"""Which side does Sail/DataFusion build for Pecan's frontier expansion join? Local mode, tiny Parquet inputs."""
import os, socket, subprocess, sys, time, tempfile
from pathlib import Path
sail = sys.argv[1]; out = Path(tempfile.mkdtemp(prefix='join-side-'))
with socket.socket() as s: s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
import sysconfig
env = dict(os.environ, SAIL_MODE='local', RUST_LOG='warn', PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()['purelib'],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var('LIBDIR') or '', LD_LIBRARY_PATH=sysconfig.get_config_var('LIBDIR') or '')
proc = subprocess.Popen([sail, 'spark', 'server', '--ip', '127.0.0.1', '--port', str(port)], env=env, stdout=open(out/'server.log','w'), stderr=subprocess.STDOUT)
try:
    for _ in range(600):
        if proc.poll() is not None: raise SystemExit('sail exited during startup: ' + (out/'server.log').read_text()[-500:])
        try: socket.create_connection(('127.0.0.1', port), timeout=0.2).close(); break
        except OSError: time.sleep(0.1)
    else: raise SystemExit('sail did not listen within 60 s')
    from pyspark.sql.connect.session import SparkSession
    from pyspark.sql.connect import functions as F
    spark = SparkSession.builder.remote(f'sc://127.0.0.1:{port}').create()
    n, m = 200000, 1600000
    edges = spark.range(m).select((F.col('id') % n).alias('src'), ((F.col('id') * 7919) % n).alias('dst'), F.lit(1.0).alias('weight'))
    edges.repartition(8).write.mode('overwrite').parquet((out/'adjacency').as_uri())
    spark.range(1).select(F.lit(0).cast('long').alias('id'), F.lit(0.0).alias('distance'), F.lit(0).cast('long').alias('hops'), F.lit(0).cast('long').alias('parent')).repartition(8).write.mode('overwrite').parquet((out/'frontier').as_uri())
    adjacency = spark.read.parquet((out/'adjacency').as_uri()); active = spark.read.parquet((out/'frontier').as_uri())
    for name, frame in (('pecan: adjacency.join(active)', adjacency.join(active, adjacency.src == active.id)),
                        ('swapped: active.join(adjacency)', active.join(adjacency, active.id == adjacency.src))):
        plan = frame.select(adjacency.dst.alias('id'), (active.distance + adjacency.weight).alias('distance'))._explain_string(extended=True)
        physical = plan[plan.find('== Physical Plan =='):] if '== Physical Plan ==' in plan else plan
        print('\n###', name); print('\n'.join(l for l in physical.splitlines() if 'Join' in l or 'Repartition' in l or 'ParquetExec' in l or 'DataSource' in l or 'Coalesce' in l)[:1800])
finally:
    proc.terminate(); proc.wait(timeout=10)
