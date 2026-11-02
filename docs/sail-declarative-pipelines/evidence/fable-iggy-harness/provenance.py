"""Record the unit-6 provenance: pinned Iggy objects, server binary hash, toolchain, commands, observation
and log hashes. Usage: provenance.py <log dir> (logs are copied into ./logs)."""
import hashlib, json, subprocess, sys, datetime, platform, shutil
from pathlib import Path
here = Path(__file__).resolve().parent
pin = Path("/Users/alexy/src/iggy-fable-pin")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args, cwd=None): return subprocess.run(args, capture_output=True, text=True, cwd=cwd).stdout.strip()
logs = here / "logs"; logs.mkdir(exist_ok=True)
for f in Path(sys.argv[1]).glob("iggy-*.log"):
    shutil.copy(f, logs / f.name)
server = Path("/Users/alexy/src/iggy-fable-pin-target/release/iggy-server")
prov = {
  "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "host": platform.node(), "os": platform.platform(),
  "iggy_pin": {"commit": run(["git", "rev-parse", "HEAD"], pin), "worktree": str(pin), "target_dir": "/Users/alexy/src/iggy-fable-pin-target",
               "sdk_version": run(["grep", "-m1", "^version", str(pin / "core/sdk/Cargo.toml")]), "server_binary_sha256": sha(server) if server.exists() else None},
  "sail_iggy_pin": {"commit": run(["git", "rev-parse", "HEAD"], "/Users/alexy/src/sail-iggy-sdp-review"), "role": "reference for the range checks (sail-iggy-mirror model.rs MirrorBatch::try_new); not linked"},
  "toolchain": {"rustc": run(["rustc", "+1.99.1", "--version"]), "hwloc": run(["brew", "list", "--versions", "hwloc"])},
  "commands": [
    "git -C /Users/alexy/src/iggy worktree add --detach /Users/alexy/src/iggy-fable-pin 153fdf466aea94b7bcb90681ee7274f9f76ec00d",
    "brew install hwloc  (macOS build dependency of iggy-server via hwlocality)",
    "PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/Users/alexy/src/iggy-fable-pin-target cargo build --release --bin iggy-server",
    "./run.sh  (cargo test --release -- --test-threads=1 --nocapture, in this directory, same target dir)",
    "cargo test --release -p integration --test mod consumer_group_membership -- --test-threads=1  (in the pin worktree)",
    "cargo test --release -p integration --test mod message_cleanup -- --test-threads=1  (in the pin worktree)",
  ],
  "observations_sha256": {p.name: sha(p) for p in sorted((here / "observations").glob("*.json"))},
  "logs_sha256": {p.name: sha(p) for p in sorted(logs.glob("*.log"))},
  "harness_sources_sha256": {str(p.relative_to(here)): sha(p) for p in [here / "Cargo.toml", here / "src/lib.rs", here / "tests/scenarios.rs", here / "run.sh"]},
}
(here / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
print(json.dumps({k: prov[k] for k in ("iggy_pin", "toolchain")}, indent=1))
