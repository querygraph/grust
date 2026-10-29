"""Verify archived bytes and pinned excerpts without running an ORC engine."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    root = Path(__file__).parent
    provenance = read_json(root / "provenance.json")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spark-repo", default=provenance["source_repositories"]["spark"]["original_path"])
    parser.add_argument("--orc-repo", default=provenance["source_repositories"]["orc_rust"]["original_path"])
    args = parser.parse_args()
    problems: list[str] = []
    entries = read_json(root / "files.json")["files"]
    path_map = {entry["original_absolute_path"]: entry["relative_path"] for entry in entries}
    for entry in entries + provenance["archive_index_hashes"]:
        path = root / entry["relative_path"]
        if not path.is_file():
            problems.append(f"Missing archived file: {entry['relative_path']}")
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
            problems.append(f"Archived file differs: {entry['relative_path']}")

    original = read_json(root / "validation.json")
    fixture_paths = set()
    for fixture in original["fixtures"]:
        relative = path_map.get(fixture["path"])
        if relative is None:
            problems.append(f"Fixture has no archive path mapping: {fixture['path']}")
            continue
        fixture_paths.add(relative)
        data = (root / relative).read_bytes()
        if len(data) != fixture["bytes"] or sha256(data) != fixture["sha256"]:
            problems.append(f"Fixture differs from original manifest: {relative}")
    if fixture_paths != {path.relative_to(root).as_posix() for path in (root / "data").rglob("*.orc")}:
        problems.append("Archived ORC fixture set differs from the original manifest")
    cases = read_json(root / "expected.json")["cases"]
    if len(fixture_paths) != original["fixture_count"] or len(cases) != original["case_count"]:
        problems.append("Original fixture/case counts do not match archived contents")

    sources = read_json(root / "source-evidence.json")["sources"]
    for source in sources:
        name = "spark" if source["repository"] == provenance["source_repositories"]["spark"]["original_path"] else "orc_rust"
        if source["pin"] != provenance["source_repositories"][name]["commit"]:
            problems.append(f"Unexpected source pin: {source['path']}")
            continue
        repository = args.spark_repo if name == "spark" else args.orc_repo
        command = ["git", "-C", repository, "show", f"{source['pin']}:{source['path']}"]
        result = subprocess.run(command, capture_output=True, check=False)
        if result.returncode:
            problems.append(f"Cannot read pinned source {source['path']}: {result.stderr.decode().strip()}")
            continue
        actual = "\n".join(result.stdout.decode().splitlines()[source["start_line"] - 1:source["end_line"]])
        if actual != source["excerpt"]:
            problems.append(f"Pinned excerpt differs: {source['path']}:{source['start_line']}")
    print(json.dumps({
        "outcome": "failed" if problems else "passed",
        "archived_original_files": len(entries),
        "fixtures": len(fixture_paths),
        "cases": len(cases),
        "source_excerpts": len(sources),
        "mismatches": problems,
        "runtime_runs": 0,
        "sail_runtime_qualification": False,
    }, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
