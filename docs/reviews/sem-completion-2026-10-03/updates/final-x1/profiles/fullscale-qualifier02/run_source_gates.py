"""Only offline Python style/types/synthetic metadata controls; no engines."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / (sys.argv[1] if len(sys.argv) == 2 else "source-gates01")
if OUT.parent != ROOT or not OUT.name.startswith("source-gates"):
    raise ValueError("fresh direct source-gate child required")
OUT.mkdir(exist_ok=False)


def identity(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


source = {p.name: identity(p) for p in ROOT.glob("*.py")}
firstparty = [
    "control_io",
    "control_models",
    "control_logs",
    "owner_models",
    "oracle_models",
    "full_models",
    "full_admission",
    "full_native",
    "full_certificate",
    "qualify_fullscale",
]
commands = [
    [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--config",
        "lint.isort.known-first-party = " + json.dumps(firstparty),
        str(ROOT),
    ],
    [sys.executable, "-m", "ruff", "format", "--check", str(ROOT)],
    [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        *[str(p) for p in sorted(ROOT.glob("*.py")) if p.name != "run_source_gates.py"],
    ],
    [
        sys.executable,
        "-I",
        "-B",
        "-c",
        f"import sys,runpy;sys.path.insert(0,{str(ROOT)!r});runpy.run_path({str(ROOT / 'test_fullscale.py')!r},run_name='__main__')",
    ],
]
steps = []
for i, argv in enumerate(commands):
    log = OUT / f"{i + 1:02}-source-gate.log"
    with log.open("xb") as stream:
        process = subprocess.Popen(
            argv, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
        )
        rc = process.wait(timeout=120)
    steps.append(
        {
            "argv": argv,
            "pid": process.pid,
            "actual_direct_wait_completed": True,
            "returncode": rc,
            "log": {"path": str(log), **identity(log)},
            "group_absence_not_probed": True,
        }
    )
    if rc:
        break
unchanged = source == {p.name: identity(p) for p in ROOT.glob("*.py")}
passed = unchanged and len(steps) == 4 and all(s["returncode"] == 0 for s in steps)
(OUT / "receipt.json").write_text(
    json.dumps(
        {
            "outcome": "passed_offline_source_gates"
            if passed
            else "failed_offline_source_gates",
            "observed_utc": datetime.now(UTC).isoformat(),
            "source_before": source,
            "source_after": {p.name: identity(p) for p in ROOT.glob("*.py")},
            "steps": steps,
            "scope": "Offline source style/types and18 synthetic metadata controls only. No engine, FFI, SSH, dataset payload, live full02 or native process/lock observation.",
        },
        indent=2,
    )
    + "\n"
)
raise SystemExit(0 if passed else 1)
