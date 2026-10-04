from datetime import datetime, timezone
import json
from pathlib import Path
import runpy

out = Path(__file__).resolve().parent
receipt = json.loads((out / "receipt.json").read_text())
module = runpy.run_path(str(out / "run_gate.py"))
current = module["snapshot"]()
assert receipt["outcome"] == "passed"
assert receipt["source_unchanged"] is True
assert all(step["returncode"] == 0 for step in receipt["steps"])
assert current == receipt["before"] == receipt["after"]
assert current["tracked_source_sha256"] == "cade42b09fe3ee11f3ee82302eaa82674fb445e592c3bc320383dae49943862e"
assert current["patch_file_sha256"] == "e81b18b2bd076f629a20e8ab6a6889efed3a0af03c32d3da7206cfc3d540ea51"
(out / "commit-guard.json").write_text(json.dumps({"checked_utc": datetime.now(timezone.utc).isoformat(), "verdict": "passed", "snapshot": current}, indent=2) + "\n")
print("CANDIDATE_COMMIT_GUARD PASSED " + current["tracked_source_sha256"])
