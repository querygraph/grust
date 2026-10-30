from pathlib import Path
import hashlib,json,re,subprocess
label="captured-preparation-explicit-cancel-clean"
c=json.loads(Path("/tmp/sail-sdp-"+label+"-candidate.json").read_text())
g=json.loads(Path("/tmp/sail-sdp-"+label+"-gate.json").read_text())
root="/Users/alexy/src/sail-pipelines-proposal"
def git(*args):return subprocess.check_output(["git","-C",root,*args],text=True).strip()
assert git("rev-parse","HEAD")==c["base"]=="ece5b6aed15462cbc54f18a6f72482f1f5e2ad51"
assert g["sail_commit"]==c["commit"] and g["base"]==c["base"] and g["outcome"]=="passed"
assert [x["name"] for x in g["checks"]]==["fmt","clippy","rust"]
for check in g["checks"]:
 assert check["exit_code"]==0
 assert hashlib.sha256(Path(check["log"]).read_bytes()).hexdigest()==check["sha256"]
s=Path(g["checks"][-1]["log"]).read_text()
assert re.findall(r"test result: ok\. (\d+) passed; 0 failed;",s)==["136","223"]
p=Path("/tmp/sail-sdp-"+label+"-sail-execution-release")
r=json.loads((p/"receipt.json").read_text())
assert r["commit"]==c["commit"] and r["outcome"]=="passed" and r["test_exit"]==0
assert len(r["load_pids"])==r["logical_cpus"]==len(r["load_worker_exit_codes"])
assert all(x is not None for x in r["load_worker_exit_codes"])
assert hashlib.sha256(Path(r["binary"]).read_bytes()).hexdigest()==r["binary_sha256"]
assert "test result: ok. 1 passed; 0 failed;" in (p/"test.log").read_text()
source=git("show",c["commit"]+":crates/sail-common-datafusion/src/session/job.rs")
assert "self.cancel();" in source and "pub trait CapturedJobPreparation: JobPreparation" in source
assert git("diff","--name-only",c["base"],c["commit"]).splitlines()==c["paths"]
print("PASS exact capture contract fmt/strict Clippy/359 libraries/one optimized loaded case "+c["commit"])
