"""A CASE over two arrays of structs panics when only a later branch has a NULL item.

    python repro.py /path/to/release/sail

Needs pyspark[connect] 4.x and pyarrow. Starts and stops its own server.
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


def attempt(label, sql):
    """Run `sql`; print its rows or the panic message."""
    try:
        print(f"{label}: {[tuple(r) for r in spark.sql(sql).collect()]}")
    except Exception as error:  # the reproducer reports any failure as text
        text = str(error)
        start = text.find("panicked")
        print(f"{label}: ERROR: {text[start:start + 160] if start >= 0 else text.splitlines()[0][:160]}")


CASES = {
    "struct, non-null array first": """
        SELECT CASE WHEN x = 1 THEN array(named_struct('a', 1))
                    ELSE array(CAST(NULL AS STRUCT<a: INT>)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
    "struct, nullable array first": """
        SELECT CASE WHEN x <> 1 THEN array(CAST(NULL AS STRUCT<a: INT>))
                    ELSE array(named_struct('a', 1)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
    "int, non-null array first   ": """
        SELECT CASE WHEN x = 1 THEN array(1)
                    ELSE array(CAST(NULL AS INT)) END AS v
        FROM VALUES (1), (2) AS t(x)""",
}

with sail(sys.argv[1]) as (spark, root):
    for label, sql in CASES.items():
        attempt(label, sql)
