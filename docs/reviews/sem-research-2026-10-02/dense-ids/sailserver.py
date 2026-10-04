"""Start one Sail Spark Connect server on an ephemeral port and hand back a PySpark Connect session.

Server start-up follows docs/reviews/sail-partitionby-write-2026-10-02/partitionby_probe.py:
the embedded Python is pointed at the client's interpreter, extensions are off, and the
mode is set through SAIL_MODE. Extra SAIL_* settings are passed as a dict and recorded.
"""
import contextlib, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, threading, time

SAIL = pathlib.Path(os.environ.get(
    "SAIL_BIN", "~/src/sail-pecan-integrated/target/host/release/sail")).expanduser().resolve()
DATA = pathlib.Path("~/src/reference/data/cit-Patents").expanduser()
VERTICES = DATA / "cit-Patents-v.parquet"
EDGES = DATA / "cit-Patents-e.parquet"


class Server:
    def __init__(self, process, port, root, settings):
        self.process, self.port, self.root, self.settings = process, port, root, settings
        self._peak, self._stop = 0, threading.Event()
        self._sampler = threading.Thread(target=self._sample, daemon=True)
        self._sampler.start()

    def _ps(self, field):
        return subprocess.run(["ps", "-o", f"{field}=", "-p", str(self.process.pid)],
                              capture_output=True, text=True).stdout.strip()

    def _sample(self):
        while not self._stop.wait(0.02):
            try:
                self._peak = max(self._peak, int(self._ps("rss") or 0))
            except ValueError:
                pass

    def cpu_seconds(self):
        days, _, clock = self._ps("cputime").rpartition("-")
        parts = [float(p) for p in clock.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return (int(days) if days else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]

    def rss_mib(self):
        return round(int(self._ps("rss") or 0) / 1024, 1)

    def reset_peak(self):
        self._peak = 0

    def peak_rss_mib(self):
        """Peak resident set of the server since reset_peak(), sampled every 0.02 s with ps."""
        return round(self._peak / 1024, 1)


@contextlib.contextmanager
def sail(mode="local", settings=None):
    """Yield (spark, server). settings: {"SAIL_EXECUTION__DEFAULT_PARALLELISM": "10", ...}."""
    settings = dict(settings or {})
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-dense-ids-", dir=os.environ.get("PROBE_TMP")))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=libdir, LD_LIBRARY_PATH=libdir, SAIL_MODE=mode, RUST_LOG="warn")
    env.pop("SAIL_EXPERIMENTAL_EXTENSIONS", None)
    env.update(settings)
    log = open(root / "server.log", "wb")
    process = subprocess.Popen([str(SAIL), "spark", "server", "--ip", "127.0.0.1", "--port", str(port)],
                               env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT)
    server = Server(process, port, root, dict(SAIL_MODE=mode, **settings))
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert process.poll() is None, "server exited: " + (root / "server.log").read_text()[-2000:]
            time.sleep(0.05)
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.remote(f"sc://127.0.0.1:{port}").getOrCreate()
        try:
            yield spark, server
        finally:
            with contextlib.suppress(Exception):
                spark.stop()
    finally:
        server._stop.set()
        process.terminate()
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
        if not os.environ.get("KEEP_ROOT"):
            shutil.rmtree(root, ignore_errors=True)


def bucket_of(column, bounds, F):
    """Index of the range bucket of `column`: the number of bounds <= value, as a binary search in CASE."""
    def search(lo, hi):          # the answer lies in [lo, hi]
        if lo == hi:
            return F.lit(lo)
        middle = (lo + hi) // 2  # bounds[middle] <= value  means  answer > middle
        return F.when(column >= F.lit(bounds[middle]), search(middle + 1, hi)).otherwise(search(lo, middle))
    return search(0, len(bounds))


def host_facts():
    def sysctl(name):
        return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True).stdout.strip()
    worktree = next((d for d in SAIL.parents if (d / ".git").exists()), SAIL.parent)
    rev = subprocess.run(["git", "-C", str(worktree), "rev-parse", "--short=9", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    import pyspark, pyarrow
    return dict(cpu=sysctl("machdep.cpu.brand_string"), cores=int(sysctl("hw.ncpu")),
                memory_gib=round(int(sysctl("hw.memsize")) / 2**30), sail_binary=str(SAIL),
                sail_binary_mtime=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(SAIL.stat().st_mtime)),
                sail_worktree_head=rev, pyspark=pyspark.__version__, pyarrow=pyarrow.__version__,
                python=sys.version.split()[0])
