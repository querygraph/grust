"""Start one Sail Spark Connect server on an ephemeral port and hand back a PySpark Connect session.

Adapted from docs/reviews/sem-research-2026-10-02/dense-ids/sailserver.py and the `sail()` context
manager of docs/reviews/sail-upstream-reports-2026-10-02/01-checkpoint-after-sort-wrong-results/repro.py:
the embedded Python is pointed at the client's interpreter, extensions are off, the mode is set
through SAIL_MODE, and every other SAIL_* variable of the caller's environment is dropped so that
the recorded settings are the complete set.
"""
import contextlib, os, pathlib, shutil, socket, subprocess, sys, sysconfig, tempfile, threading, time

SAIL = pathlib.Path(os.environ.get(
    "SAIL_BIN", "~/src/sail-pecan-integrated/target/host/release/sail")).expanduser().resolve()
DATA = pathlib.Path("~/src/reference/data").expanduser()
SCRATCH = pathlib.Path(os.environ.get(
    "VIZ_SCRATCH",
    "/private/tmp/claude-501/-Users-alexy-src-grust/508c82ce-25d0-4e06-bb41-a1907715a911/scratchpad/viz"))


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
        while not self._stop.wait(0.05):
            try:
                self._peak = max(self._peak, int(self._ps("rss") or 0))
            except ValueError:
                pass

    def reset_peak(self):
        self._peak = 0

    def peak_rss_mib(self):
        """Peak resident set of the server since reset_peak(), sampled every 0.05 s with ps."""
        return round(self._peak / 1024, 1)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(mode, settings):
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    env = dict(os.environ, PYTHONHOME=sys.base_prefix, PYTHONPATH=sysconfig.get_paths()["purelib"],
               DYLD_LIBRARY_PATH=libdir, LD_LIBRARY_PATH=libdir, SAIL_MODE=mode, RUST_LOG="warn")
    for name in list(env):
        if name.startswith("SAIL_") and name != "SAIL_MODE":
            del env[name]
    env.update(settings)
    return env


@contextlib.contextmanager
def sail(mode="local", settings=None, command=("spark", "server")):
    """Yield (spark, server) for a Spark Connect server, or (port, server) for command=("flight", "server")."""
    settings = dict(settings or {})
    root = pathlib.Path(tempfile.mkdtemp(prefix="sail-viz-"))
    port = _free_port()
    log = open(root / "server.log", "wb")
    process = subprocess.Popen([str(SAIL), *command, "--ip", "127.0.0.1", "--port", str(port)],
                               env=_env(mode, settings), cwd=root, stdout=log, stderr=subprocess.STDOUT)
    server = Server(process, port, root, dict(SAIL_MODE=mode, **settings))
    try:
        while True:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert process.poll() is None, "server exited: " + (root / "server.log").read_text()[-2000:]
            time.sleep(0.05)
        if command[0] != "spark":
            yield port, server
            return
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
        shutil.rmtree(root, ignore_errors=True)


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
                python=sys.version.split()[0], load_average=os.getloadavg(),
                at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
