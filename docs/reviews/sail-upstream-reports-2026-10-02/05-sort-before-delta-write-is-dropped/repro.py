"""A sort before a Delta write is removed: the Delta files are unsorted where the Parquet files are sorted.

    python repro.py /path/to/release/sail

Needs pyspark[connect] 4.0 and pyarrow. Starts and stops its own server.
"""
import contextlib, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, time


@contextlib.contextmanager
def sail(binary, mode="local", **settings):
    """A Sail server in `mode` with the given environment settings, a Spark Connect session, a scratch directory."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-repro-"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # The server embeds Python; point it at this interpreter's environment.
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "",
               LD_LIBRARY_PATH=sysconfig.get_config_var("LIBDIR") or "", SAIL_MODE=mode, **settings)
    for name in list(env):
        if name.startswith("SAIL_") and name != "SAIL_MODE" and name not in settings:
            del env[name]
    server = subprocess.Popen([binary, "spark", "server", "--ip", "127.0.0.1", "--port", str(port)], env=env,
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert server.poll() is None, "the server exited"
            time.sleep(0.05)
        from pyspark.sql.connect.session import SparkSession
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").create()
        yield spark, root
        spark.stop()
    finally:
        server.terminate()
        server.wait()
        shutil.rmtree(root, ignore_errors=True)


def attempt(label, action):
    """Run `action`; print its value or the first line of its error."""
    try:
        print(f"{label}: {action()}")
    except Exception as error:  # the reproducer reports any failure as text
        print(f"{label}: ERROR: {str(error).strip().splitlines()[0][:300]}")


def plan_lines(frame, *needles):
    """The physical plan lines that mention any of `needles`."""
    text = frame._explain_string()
    return [line.strip()[:170] for line in text.splitlines() if any(n in line for n in needles)]


def sorted_files(directory, column):
    """How many Parquet files under `directory` are sorted ascending by `column`."""
    import glob
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    flags = []
    for path in sorted(glob.glob(str(directory / "**" / "*.parquet"), recursive=True)):
        values = pq.read_table(path, columns=[column]).column(0)
        flags.append(len(values) < 2 or bool(pc.all(pc.greater_equal(values[1:], values[:-1])).as_py()))
    return f"{sum(flags)} of {len(flags)} files sorted by {column}"


from pyspark.sql.connect import functions as F

with sail(sys.argv[1]) as (spark, root):
    rows = spark.range(1_000_000).select(((F.col("id") * 2654435761) % 1_000_003).alias("k"), F.col("id").alias("v"))
    for fmt in ("parquet", "delta"):
        rows.orderBy("k").write.format(fmt).save((root / f"{fmt}-orderBy").as_uri())
        rows.repartition(4, "k").sortWithinPartitions("k").write.format(fmt).save((root / f"{fmt}-sortWithin").as_uri())
        print(f"{fmt:8} orderBy(k).write:                              {sorted_files(root / f'{fmt}-orderBy', 'k')}")
        print(f"{fmt:8} repartition(4, k).sortWithinPartitions(k).write: {sorted_files(root / f'{fmt}-sortWithin', 'k')}")
