from pathlib import Path
import hashlib,json,re,subprocess
label="local-captured-execution"
c=json.loads(Path("/tmp/sail-sdp-"+label+"-candidate.json").read_text())
g=json.loads(Path("/tmp/sail-sdp-"+label+"-gate.json").read_text())
def git(*args):return subprocess.check_output(["git","-C","/Users/alexy/src/sail-pipelines-proposal",*args],text=True).strip()
assert git("rev-parse","HEAD")==c["base"]=="16c43aa290026e8057952e3f2ae3826d4c81948b"
assert g["sail_commit"]==c["commit"] and g["outcome"]=="passed"
assert [x["name"]for x in g["checks"]]==["fmt","clippy","rust"]
for x in g["checks"]:
 assert x["exit_code"]==0 and hashlib.sha256(Path(x["log"]).read_bytes()).hexdigest()==x["sha256"]
assert re.findall(r"test result: ok\. (\d+) passed; 0 failed;",Path(g["checks"][-1]["log"]).read_text())==["136","228"]
for label,count in [("local-captured-execution",6),("local-capture-all-transitions",9)]:
 d=Path("/tmp/sail-sdp-"+label+"-sail-execution-release")
 r=json.loads((d/"receipt.json").read_text())
 assert r["commit"]==c["commit"] and r["outcome"]=="passed" and r["test_exit"]==0
 assert len(r["load_pids"])==r["logical_cpus"]==len(r["load_worker_exit_codes"])
 assert all(x is not None for x in r["load_worker_exit_codes"])
 assert hashlib.sha256(Path(r["binary"]).read_bytes()).hexdigest()==r["binary_sha256"]
 assert f"test result: ok. {count} passed; 0 failed;" in (d/"test.log").read_text()
assert set(git("diff","--name-only",c["base"],c["commit"]).splitlines())==set(c["paths"])
print("PASS exact local capture364 libraries, optimized6+9 cases, workers joined "+c["commit"])
