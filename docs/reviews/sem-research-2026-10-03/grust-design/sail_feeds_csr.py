"""The engine half of "Sail feeds the CSR": dense ids, mapped edges, sorted edges, and mapping back.

    python sail_feeds_csr.py <sail binary> <graph> <out dir> [pool type] [pool GiB]

Starts a release Sail server in local mode (10 partitions), and for one LDBC graph:
1. the dense-id mapping: row_number() over (order by id) - 1, written to Parquet;
2. the edges with both endpoints mapped by two joins, written unsorted;
3. the same edges sorted by (s, d) into one file;
4. mapping a dense result back to the original ids: one join of n rows.
Times each step and samples the server's resident memory. Prints JSON lines.
"""
import contextlib, json, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, threading, time

binary, graph, out = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
pool_type = sys.argv[4] if len(sys.argv) > 4 else "greedy"
pool_gib = int(sys.argv[5]) if len(sys.argv) > 5 else 30
data = pathlib.Path.home() / "src/reference/data" / graph
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
           DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE="local",
           SAIL_EXECUTION__DEFAULT_PARALLELISM="10", SAIL_RUNTIME__MEMORY_POOL__TYPE=pool_type,
           SAIL_RUNTIME__MEMORY_POOL__GREEDY__MAX_SIZE=str(pool_gib * 2**30),
           SAIL_RUNTIME__MEMORY_POOL__FAIR__MAX_SIZE=str(pool_gib * 2**30), RUST_LOG="warn")
for name in list(env):
    if name.startswith("SAIL_") and name not in ("SAIL_MODE", "SAIL_EXECUTION__DEFAULT_PARALLELISM") \
            and not name.startswith("SAIL_RUNTIME__MEMORY_POOL"):
        del env[name]
server = subprocess.Popen([binary, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                          cwd=out, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


class Peak:
    """Samples the server's resident set every 0.2 s while a step runs."""
    def __init__(self):
        self.peak, self.running = 0, True
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while self.running:
            text = subprocess.run(["ps", "-o", "rss=", "-p", str(server.pid)], capture_output=True, text=True).stdout.strip()
            if text:
                self.peak = max(self.peak, int(text) * 1024)
            time.sleep(0.2)

    def stop(self):
        self.running = False
        self.thread.join()
        return self.peak


def step(name, action, **extra):
    peak = Peak()
    started = time.perf_counter()
    value, error = None, None
    try:
        value = action()
    except Exception as failure:  # record the failure and go on to the next step
        error = str(failure).strip().splitlines()[0][:400]
    seconds = time.perf_counter() - started
    record = dict(graph=graph, step=name, seconds=round(seconds, 3), server_peak_rss_gib=round(peak.stop() / 2**30, 2),
                  pool=f"{pool_type} {pool_gib} GiB", **extra)
    if error:
        record["error"] = error
    print(json.dumps(record), flush=True)
    return value


try:
    while True:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        assert server.poll() is None, "server exited"
        time.sleep(0.05)
    from pyspark.sql.connect import functions as F
    from pyspark.sql.connect.session import SparkSession

    spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
    spark.read.parquet(str(data / f"{graph}-v.parquet")).createOrReplaceTempView("v")
    spark.read.parquet(str(data / f"{graph}-e.parquet")).createOrReplaceTempView("e")
    uri = lambda name: (out / name).as_uri()

    step("1 dense ids: row_number over id, write", lambda: spark.sql(
        "SELECT id, CAST(row_number() OVER (ORDER BY id) - 1 AS BIGINT) AS dense FROM v").write.parquet(uri("map")))
    spark.read.parquet(uri("map")).createOrReplaceTempView("map")
    n = spark.sql("SELECT count(*) AS n, min(dense) AS lo, max(dense) AS hi, count(DISTINCT dense) AS k FROM map").first()
    assert (n.lo, n.hi, n.k) == (0, n.n - 1, n.n), n
    step("2 map both endpoints: two joins, write unsorted", lambda: spark.sql(
        "SELECT ms.dense AS s, md.dense AS d FROM e JOIN map ms ON e.source = ms.id JOIN map md ON e.target = md.id"
    ).write.parquet(uri("edges-dense")))
    spark.sql("SET datafusion.execution.minimum_parallel_output_files = 1")
    step("3 sort by (s, d), write one file", lambda: spark.read.parquet(uri("edges-dense")).orderBy("s", "d")
         .write.parquet(uri("edges-sorted")))
    step("2+3 map and sort in one job, write one file", lambda: spark.sql(
        "SELECT ms.dense AS s, md.dense AS d FROM e JOIN map ms ON e.source = ms.id JOIN map md ON e.target = md.id"
    ).orderBy("s", "d").write.parquet(uri("edges-mapped-sorted")))
    # A dense result of n rows, as a kernel would return it, mapped back to the original ids.
    step("4 map a dense result back: one join of n rows, write", lambda: spark.read.parquet(uri("map")).select(
        "dense", (F.col("dense") % 7).alias("value")).join(spark.read.parquet(uri("map")), "dense")
        .select("id", "value").write.parquet(uri("result-mapped-back")))
    files = {name: len(list((out / name).glob("*.parquet"))) for name in ("map", "edges-dense", "edges-sorted", "edges-mapped-sorted") if (out / name).exists()}
    print(json.dumps(dict(graph=graph, step="summary", vertices=n.n, files=files,
                          bytes={k: sum(p.stat().st_size for p in (out / k).glob("*.parquet")) for k in files})), flush=True)
    spark.stop()
finally:
    server.terminate()
    server.wait()
