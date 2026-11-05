"""Validate this documentation candidate and retained evidence; no engine gate."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
DOCS = EVIDENCE.parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str, cwd: Path = ROOT) -> bytes:
    return subprocess.check_output(["git", *args], cwd=cwd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    candidate = json.loads((EVIDENCE / "candidate-files.json").read_text())
    paths = list(candidate["files"])
    for name, expected in candidate["files"].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
        if args.staged:
            assert sha(git("show", ":" + name)) == expected, name + " staged drift"
    patch = (EVIDENCE / "cumulative-documents.patch").read_bytes()
    assert sha(patch) == candidate["patch_sha256"]
    assert git("diff", "--binary", candidate["baseline"], "--", *paths) == patch
    git("apply", "--reverse", "--check", str(EVIDENCE / "cumulative-documents.patch"))
    git("diff", "--check", "--", ".", ":(exclude)**/*.patch")
    if args.staged:
        staged = git("diff", "--cached", "--name-only").decode().splitlines()
        assert set(paths) <= set(staged)
        assert all(n == "codex-to-fable.md" or n in paths or
                   n.startswith(str(EVIDENCE.relative_to(ROOT)) + "/") for n in staged)
        for name in staged:
            assert git("show", ":" + name) == (ROOT / name).read_bytes(), name
        git("diff", "--cached", "--check", "--", ".", ":(exclude)**/*.patch")
    active = [
        "REDESIGN-REVIEW-PACKET.md", "REDESIGN-PLAN.md", "STREAMING-ON-STREAMSOURCE.md",
        "CHANGE-CAPTURE-ON-STREAMSOURCE.md", "STREAMING-ARCHITECTURE.md",
        "DECISION-NOTES-STREAMING.md", "PROTOTYPE-SPECS.md", "PROTOTYPE-RESULTS-STREAMING.md",
        "STREAMING-REVIEW-AGAINST-RUNTIME.md", "STREAMSOURCE-ENGINEERING-REVIEW.md",
        "CHANGE-CAPTURE-SEMANTICS.md", "FENCED-TABLE-COMMITS.md", "TYPED-PIPELINE-CONFIG.md",
    ]
    counts = {}
    for name in active:
        contents = (DOCS / name).read_text()
        counts[name] = len(contents.split())
        assert counts[name] < 2000, name
        assert not re.search(r"^(<<<<<<<|=======|>>>>>>>)( |$)", contents, re.M), name
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", contents):
            if not re.match(r"[a-z]+://", link):
                assert (DOCS / link.split("#")[0]).exists(), (name, link)
    notes = re.split(r"(?m)^## (S\d+\. .*)$", (DOCS / "DECISION-NOTES-STREAMING.md").read_text())
    note_counts = {notes[i]: len(notes[i + 1].split()) for i in range(1, len(notes), 2)}
    assert len(note_counts) == 13
    assert all(n < 300 for n in note_counts.values())
    for artifact in EVIDENCE.glob("*.json"):
        json.loads(artifact.read_text())
    for artifact in EVIDENCE.glob("*.py"):
        ast.parse(artifact.read_text(), filename=str(artifact))
    model = subprocess.check_output(["python3", str(EVIDENCE / "semantics_model.py")])
    assert json.loads(model) == json.loads((EVIDENCE / "semantics-model.json").read_text())
    receipt = json.loads((EVIDENCE / "marker-run-receipt.json").read_text())
    for name, expected in receipt["files"].items():
        assert sha((EVIDENCE / name).read_bytes()) == expected, name
    assert sha((EVIDENCE / "marker_probe.rs").read_bytes()) == receipt["probe_source_sha256"]
    assert sha((EVIDENCE / "prepare_marker_probe.py").read_bytes()) == receipt["prepare_script_sha256"]
    manifest = json.loads((EVIDENCE / "marker-source-manifest.json").read_text())
    for item in manifest["files"]:
        assert sha((Path(manifest["source_root"]) / item["source"]).read_bytes()) == item["sha256"]
        assert sha((Path(manifest["probe_root"]) / item["destination"]).read_bytes()) == item["sha256"]
    for item in json.loads((EVIDENCE / "fencing-source-hashes.json").read_text())["source_files"]:
        assert sha(Path(item["path"]).read_bytes()) == item["sha256"], item["path"]
    pins = {
        "/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01": "85c6cca01cd521dd778bc200c987a34edf141de1",
        "/Users/alexy/src/sail-pipelines-proposal": "99dc47788941daf28eec847527949a4cadafdbd2",
        "/Users/alexy/src/sail-proto-p4": "4fad33ca531ec44170d0e8d11c794df14835ff37",
        "/Users/alexy/src/sail-proto-p3": "ef5f848a758ed48067a751165d8bf9a756f2c482",
        "/Users/alexy/src/spark-sdp-4.2.1": "617618396087429b5627a86ce933bb0f5d6645cb",
    }
    sources = {}
    for directory, revision in pins.items():
        assert git("rev-parse", "HEAD", cwd=Path(directory)).decode().strip() == revision
        status = git("status", "--porcelain", cwd=Path(directory)).decode()
        assert not status, (directory, status)
        sources[directory] = {"head": revision, "status": status}
    log = (ROOT / "codex-to-fable.md").read_text()
    assert not re.search(r"^(<<<<<<<|=======|>>>>>>>)( |$)", log, re.M)
    result = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS: documentation candidate, retained evidence integrity and source pins",
        "baseline": candidate["baseline"], "patch_sha256": candidate["patch_sha256"],
        "document_count": len(paths), "active_document_words": counts,
        "decision_note_words": note_counts, "source_worktrees": sources,
        "checks": ["Candidate hashes and patch identity", "Reverse patch application",
                   "Whitespace", "Local links", "Document and note lengths", "JSON and Python syntax",
                   "Semantic model output unchanged", "Marker receipt and copied source integrity",
                   "Fencing source hashes", "Source pins and clean worktrees", "Coordination conflict markers"],
        "staged_checked": args.staged,
        "limits": ["No full engine, Spark, broker or storage suites", "No production implementation",
                   "No benchmark", "No Dhall/CUE compilation", "External links not fetched by this validator"],
    }
    if args.write:
        (EVIDENCE / "document-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
