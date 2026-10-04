from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

out = Path(__file__).resolve().parent
module = runpy.run_path(str(out / "run_gate.py"))
source = module["ROOT"]
receipt = json.loads((out / "receipt.json").read_text())
assert receipt["outcome"] == "passed" and receipt["source_unchanged"]
assert all(step["returncode"] == 0 for step in receipt["steps"])
assert module["snapshot"]() == receipt["after"]
sha = "56194b170155301ba91077f0ba3df31fe2c78b6b"
base = "ffcfbd5690e3f3681ef9ac18ba959bc231cf9f73"
integration = "2894a962076d3cc404dd72ec736ebeb9239901f6"
bundle = Path("/private/tmp/sail-compact-struct-min-56194b170.bundle")
assert not bundle.exists()
for ancestor in (base, integration):
    subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, sha], cwd=source, check=True)
subprocess.run(["git", "bundle", "create", str(bundle), "work/compact-struct-min", "^" + base], cwd=source, check=True)
verified = subprocess.run(["git", "bundle", "verify", str(bundle)], cwd=source, check=True, text=True, capture_output=True)
heads = subprocess.check_output(["git", "bundle", "list-heads", str(bundle)], cwd=source, text=True)
assert heads.strip() == sha + " refs/heads/work/compact-struct-min"
record = {"created_utc": datetime.now(timezone.utc).isoformat(), "commit": sha, "prerequisite": base,
          "includes_integration": integration, "path": str(bundle), "bytes": bundle.stat().st_size,
          "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(), "heads": heads,
          "verification": verified.stdout + verified.stderr, "source_unchanged": module["snapshot"]() == receipt["after"]}
assert record["source_unchanged"]
(out / "bundle.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
