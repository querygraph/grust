import json, os, random, shutil, signal, socket, subprocess, sys, time
from pathlib import Path
PY = sys.executable; HERE = Path(__file__).parent
root = Path(sys.argv[1]); seed = int(sys.argv[2]); rounds = int(sys.argv[3]); random.seed(seed)
shutil.rmtree(root, ignore_errors=True); (root / "landing").mkdir(parents=True)
def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def serve():
    p = port()
    proc = subprocess.Popen([PY, "-m", "pysail", "spark", "server", "--port", str(p)], stdout=(root/"server.log").open("ab"), stderr=subprocess.STDOUT)
    for _ in range(800):
        with socket.socket() as c:
            if c.connect_ex(("127.0.0.1", p)) == 0: return proc, p
        time.sleep(.05)
    raise RuntimeError("no server")
expected = {}; seq = 0
def add(n):
    global seq
    lines = []
    for _ in range(50):
        seq += 1; k = random.randrange(40)
        lines.append(json.dumps({"id": k, "name": f"v{seq}", "seq": seq})); expected[str(k)] = [f"v{seq}", seq]
    (root / "landing" / f"{n}.json").write_text("\n".join(lines) + "\n")
outcomes = []
for i in range(rounds):
    for b in range(random.randrange(4, 12)): add(f"{i}-{b}")
    srv, p = serve()
    c = subprocess.Popen([PY, str(HERE/"crash_client.py"), str(root), str(p), "run"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    delay = random.uniform(0.15, 1.1); t = time.monotonic(); done = False
    while time.monotonic() - t < delay:
        if c.poll() is not None: done = True; break
        time.sleep(.02)
    srv.send_signal(signal.SIGKILL); srv.wait()
    if not done:
        try: c.wait(1)
        except subprocess.TimeoutExpired: c.kill(); c.wait()
    outcomes.append("finished" if done and c.returncode == 0 else ("failed" if done else "killed"))
    if done and c.returncode != 0: print("CLIENT", c.stdout.read()[-1500:].replace("\n"," "))
srv, p = serve()
c = subprocess.run([PY, str(HERE/"crash_client.py"), str(root), str(p), "show"], capture_output=True, text=True, timeout=200)
srv.kill(); srv.wait()
line = [l for l in c.stdout.splitlines() if l.startswith("ROWS ")]
if not line:
    print(json.dumps({"seed": seed, "outcomes": outcomes, "error": (c.stdout + c.stderr)[-1800:].replace("\n", " ")})); sys.exit(1)
got = json.loads(line[0][5:])
bad = [k for k in expected if got.get(k) != expected[k]]
print(json.dumps({"seed": seed, "outcomes": outcomes, "match": got == expected and not bad, "rows": len(got), "expected": len(expected), "wrong": bad[:6]}))
