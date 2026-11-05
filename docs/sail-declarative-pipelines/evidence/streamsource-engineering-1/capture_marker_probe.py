"""Retain the isolated probe's logs, lockfile and provenance without overwrites."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tomllib


PROBE = Path("/Users/alexy/src/sail/tmp/streamsource-probes-20261105")
SOURCE = Path("/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01")
EVIDENCE = Path(__file__).resolve().parent


def command_output(command: list[str], directory: Path) -> str:
    return subprocess.check_output(command, cwd=directory, text=True).strip()


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((PROBE / "SOURCE-MANIFEST.json").read_text())
    for item in manifest["files"]:
        assert digest(SOURCE / item["source"]) == item["sha256"]
        assert digest(PROBE / item["destination"]) == item["sha256"]
    assert (PROBE / "src/main.rs").read_bytes() == (EVIDENCE / "marker_probe.rs").read_bytes()
    source_packages = {
        (p["name"], p["version"], p.get("source"))
        for p in tomllib.loads((SOURCE / "Cargo.lock").read_text())["package"]
    }
    probe_packages = {
        (p["name"], p["version"], p.get("source"))
        for p in tomllib.loads((PROBE / "Cargo.lock").read_text())["package"]
    }
    assert probe_packages - source_packages == {("streamsource-marker-probe", "0.1.0", None)}
    retained_files: dict[str, str] = {}
    for name in ["Cargo.toml", "Cargo.lock", "Cargo.run-1.toml", "run-1.stderr.log", "run-2.stderr.log", "run-3.stderr.log", "run-3.stdout.json"]:
        destination = EVIDENCE / ("marker-" + name)
        assert not destination.exists(), destination
        shutil.copyfile(PROBE / name, destination)
        retained_files[destination.name] = digest(destination)
    results = json.loads((PROBE / "run-3.stdout.json").read_text())
    expected_failures = [item for item in results["observations"] if item.get("outcome") == "expected failure reproduced"]
    assert len(expected_failures) == 29
    source_status = command_output(["git", "status", "--porcelain"], SOURCE)
    assert not source_status
    receipt = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": command_output(["git", "rev-parse", "HEAD"], SOURCE),
        "source_worktree_status": source_status,
        "rustc": command_output(["rustc", "--version"], PROBE),
        "cargo": command_output(["cargo", "--version"], PROBE),
        "protoc": command_output(["protoc", "--version"], PROBE),
        "platform": command_output(["uname", "-sm"], PROBE),
        "environment": {"CARGO_INCREMENTAL": "0", "CARGO_TARGET_DIR": str(PROBE / "target")},
        "command_working_directory": str(PROBE),
        "runs": [
            {"command": "cargo run --offline > run-1.stdout.json 2> run-1.stderr.log", "exit_code": 101, "outcome": "Setup failure: manifest requested pre-lockfile dependency versions; no probe ran"},
            {"command": "cargo run --offline > run-2.stdout.json 2> run-2.stderr.log", "exit_code": 101, "outcome": "Setup failure: locked log 0.4.35 missing from local cache; no probe ran"},
            {"command": "cargo run --locked > run-3.stdout.json 2> run-3.stderr.log", "exit_code": 0, "outcome": "29 expected error cases reproduced, named success controls passed, schema metadata loss asserted"},
        ],
        "dependency_check": "Every dependency name/version/source triple in probe Cargo.lock occurs in the reviewed Sail Cargo.lock; only harness root differs",
        "source_copy_check": "All 8 copied source/build/proto files byte-identical before and after execution",
        "binary_sha256": digest(PROBE / "target/debug/streamsource-marker-probe"),
        "probe_source_sha256": digest(EVIDENCE / "marker_probe.rs"),
        "prepare_script_sha256": digest(EVIDENCE / "prepare_marker_probe.py"),
        "files": retained_files,
        "limits": ["No production fix", "No SQL planning or full Sail runtime execution", "No distributed execution", "No Spark/broker/storage suite", "No full Arrow type sweep", "No performance claim"],
    }
    destination = EVIDENCE / "marker-run-receipt.json"
    assert not destination.exists(), destination
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"receipt": str(destination), "expected_error_cases": len(expected_failures), "source_unchanged": True}, indent=2))


if __name__ == "__main__":
    main()
