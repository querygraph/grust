"""Sail: the cost of DataFrameWriter.partitionBy against a plain Parquet write of the same rows.

Starts a Sail server in local mode (no extensions), writes one frame four ways, and reports wall
seconds and the server process's CPU seconds for each write.

    python repro.py /path/to/release/sail [rows] [buckets]
"""
import json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time

sail = pathlib.Path(sys.argv[1]).resolve()
rows = int(sys.argv[2]) if len(sys.argv) > 2 else 16_000_000
buckets = int(sys.argv[3]) if len(sys.argv) > 3 else 10
root = pathlib.Path(tempfile.mkdtemp(prefix="sail-partitionby-", dir=os.environ.get("PROBE_TMP")))
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "",
           LD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local", RUST_LOG="warn")
env.pop("SAIL_EXPERIMENTAL_EXTENSIONS", None)
server = subprocess.Popen([str(sail), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                          env=env, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def cpu_seconds():
    text = subprocess.run(["ps", "-o", "cputime=", "-p", str(server.pid)], capture_output=True, text=True).stdout.strip()
    days, _, clock = text.rpartition("-")
    parts = [float(p) for p in clock.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return (int(days) if days else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]

try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.05)
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").getOrCreate()
    source = root / "source"
    # Two incompressible columns and a bucket in [0, buckets).
    spark.range(rows).select(
        F.xxhash64("id").alias("id"), F.xxhash64("id", F.lit(1)).cast("double").alias("value"),
        F.pmod(F.xxhash64("id"), F.lit(buckets)).cast("int").alias("bucket")).write.parquet(source.as_uri())
    frame = spark.read.parquet(source.as_uri())
    assert frame.count() == rows
    modes = {
        "plain": lambda: frame.write,
        "repartition(n, bucket)": lambda: frame.repartition(buckets, "bucket").write,
        "partitionBy(bucket)": lambda: frame.write.partitionBy("bucket"),
        "repartition(n, bucket) + partitionBy(bucket)": lambda: frame.repartition(buckets, "bucket").write.partitionBy("bucket"),
    }
    results = []
    for repeat in range(3):
        for mode, writer in modes.items():
            target = root / "out"
            shutil.rmtree(target, ignore_errors=True)
            cpu, started = cpu_seconds(), time.perf_counter()
            writer().parquet(target.as_uri())
            wall, used = time.perf_counter() - started, cpu_seconds() - cpu
            files = list(target.rglob("*.parquet"))
            written = spark.read.parquet(target.as_uri()).count()
            assert written == rows, (mode, written)
            record = dict(rows=rows, buckets=buckets, mode=mode, repeat=repeat, wall_seconds=round(wall, 3),
                          server_cpu_seconds=round(used, 2), cores_busy=round(used / wall, 1), files=len(files),
                          directories=len({f.parent for f in files}), bytes=sum(f.stat().st_size for f in files))
            results.append(record)
            print(json.dumps(record), flush=True)
    spark.stop()
finally:
    server.terminate(); server.wait(timeout=60)
    shutil.rmtree(root, ignore_errors=True)
