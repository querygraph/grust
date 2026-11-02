from pathlib import Path
import hashlib,json,re,subprocess
label="resolver-typed-analyzer-generated"
c=json.loads(Path("/tmp/sail-sdp-"+label+"-candidate.json").read_text())
g=json.loads(Path("/tmp/sail-sdp-"+label+"-gate.json").read_text())
def git(*args):return subprocess.check_output(["git","-C","/Users/alexy/src/sail-pipelines-proposal",*args],text=True).strip()
assert git("rev-parse","HEAD")==c["base"]=="a74c3f429b092fd5cde6f65d36371760471a07f6"
assert g["sail_commit"]==c["commit"] and g["base"]==c["base"] and g["outcome"]=="passed"
assert [x["name"]for x in g["checks"]]==["fmt","clippy","rust"]
for x in g["checks"]:
 assert x["exit_code"]==0 and hashlib.sha256(Path(x["log"]).read_bytes()).hexdigest()==x["sha256"]
assert re.findall(r"test result: ok\. (\d+) passed; 0 failed;",Path(g["checks"][-1]["log"]).read_text())==["136","78"]
assert set(git("diff","--name-only",c["base"],c["commit"]).splitlines())==set(c["paths"])
ctrl=json.loads(Path("/tmp/sail-sdp-resolver-native-authority-control.json").read_text())
assert ctrl["base"]==c["commit"] and git("diff","--name-only",ctrl["base"],ctrl["control"])==ctrl["path"]
log=Path("/tmp/sail-sdp-resolver-native-authority-control.log").read_text()
assert "test result: FAILED. 2 passed; 5 failed;"in log
for p in c["paths"]:
 if "tests.rs"in p:
  assert git("rev-parse",ctrl["base"]+":"+p)==git("rev-parse",ctrl["control"]+":"+p)
assert "left: 9"in log and "right: 7"in log
print("PASS exact native resolver214 libraries/strict Clippy and unchanged authority control2pass5fail "+c["commit"])
