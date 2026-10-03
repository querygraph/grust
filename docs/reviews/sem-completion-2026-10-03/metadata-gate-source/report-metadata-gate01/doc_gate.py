"""Bounded root-run report metadata gate; no Rust, engine or process probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import JsonValue, TypeAdapter

from doc_models import (
    REPO,
    REPORT,
    Check,
    Identity,
    Pin,
    Plan,
    Receipt,
    Record,
    State,
    safe,
)

HELPERS = Path(__file__).parent
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
CONFLICT = re.compile(r"^(<<<<<<<|=======|>>>>>>>)( |$)", re.MULTILINE)
LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)")


class Member(Identity):
    path: str
    original: str


class Manifest(Record):
    observed_utc: str
    outcome: Literal["packaged_closed_metadata_only"]
    topic: str
    members: list[Member]
    excluded_payload_pins: list[Pin]
    scope: str


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pin(path: Path) -> Pin:
    require(
        path.is_file() and not path.is_symlink(),
        "regular physical metadata required: " + str(path),
    )
    require(
        path.stat().st_size <= 64 * 2**20, "metadata/archive exceeds 64 MiB admission"
    )
    before = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "metadata changed while hashing",
    )
    return Pin(path=path, bytes=after.st_size, sha256=digest)


def reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant: " + value)


def decoded(path: Path) -> JsonValue:
    require(path.stat().st_size <= 16 * 2**20, "bounded JSON metadata required")
    return JSON.validate_python(
        json.loads(path.read_text(), parse_constant=reject_constant)
    )


def git(*argv: str, code: int = 0) -> str:
    done = subprocess.run(
        ["/usr/bin/git", "-c", "core.quotepath=false", *argv],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    require(
        done.returncode == code and len(done.stdout) <= 4 * 2**20,
        "Git metadata command failed: " + " ".join(argv),
    )
    return done.stdout.strip()


def source(plan: Plan) -> State:
    git("symbolic-ref", "--quiet", "HEAD", code=1)
    head, head_tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    require(head == plan.commit, "documentation gate HEAD differs")
    require(git("cat-file", "-t", plan.tree) == "tree", "admitted report tree absent")
    git("diff", "--quiet", plan.tree, "--")
    git("diff", "--cached", "--quiet", plan.tree, "--")
    require(
        not git("ls-files", "--others", "--exclude-standard"),
        "untracked report source is not admitted",
    )
    status = git("status", "--porcelain=v1")
    if plan.mode == "committed":
        require(
            head_tree == plan.tree and not status,
            "final gate requires exact clean committed report tree",
        )
    else:
        require(
            plan.commit == plan.base_commit and head_tree != plan.tree and bool(status),
            "candidate qualifies actual base plus changed staged tree only",
        )
    changed = set(
        git("diff", "--name-only", plan.base_commit, plan.tree, "--").splitlines()
    )
    require(
        changed == set(plan.changed_files),
        "actual documentation changed-file set differs",
    )
    return State(
        head=head,
        head_tree=head_tree,
        admitted_tree=plan.tree,
        detached=True,
        status=status,
    )


def identity_files(plan: Plan) -> list[Pin]:
    observed: list[Pin] = []
    for name, expected in plan.changed_files.items():
        path = REPO / name
        if expected is None:
            require(
                not path.exists() and not path.is_symlink(),
                "declared deletion still exists",
            )
        else:
            actual = pin(path)
            require(
                (actual.bytes, actual.sha256) == (expected.bytes, expected.sha256),
                "changed-file identity differs: " + name,
            )
            observed.append(actual)
    return observed


def check_json_and_conflicts(files: list[Pin]) -> int:
    parsed = 0
    for observed in files:
        path = observed.path
        if path.suffix == ".json":
            decoded(path)
            parsed += 1
        elif path.suffix == ".jsonl":
            require(
                path.stat().st_size <= 16 * 2**20, "bounded JSONL metadata required"
            )
            for line in path.read_text().splitlines():
                if line.strip():
                    JSON.validate_python(
                        json.loads(line, parse_constant=reject_constant)
                    )
        if path.suffix in {".md", ".json", ".py", ".rs", ".toml", ".yaml", ".yml"}:
            require(
                not CONFLICT.search(path.read_text()),
                "conflict marker in portable source: " + str(path),
            )
    return parsed


def check_manifests(plan: Plan) -> list[Pin]:
    files: dict[Path, Pin] = {}
    report_root = REPO / REPORT
    for expected in plan.manifests:
        require(
            pin(expected.path) == expected
            and expected.path.is_relative_to(report_root),
            "manifest pin/root differs",
        )
        manifest = Manifest.model_validate_json(expected.path.read_bytes())
        require(
            len({m.path for m in manifest.members}) == len(manifest.members),
            "duplicate manifest members",
        )
        for member in manifest.members:
            require(safe(member.path), "unsafe portable manifest member")
            path = expected.path.parent / member.path
            require(
                path.resolve().is_relative_to(expected.path.parent.resolve()),
                "manifest member escapes its directory",
            )
            actual = pin(path)
            require(
                (actual.bytes, actual.sha256) == (member.bytes, member.sha256),
                "portable manifest member SHA/bytes differ",
            )
            files[path] = actual
        files[expected.path] = expected
    for expected in plan.archives:
        require(
            expected.path.is_relative_to(report_root)
            and expected.path.name.endswith(".tar.gz")
            and pin(expected.path) == expected,
            "archive identity/root differs",
        )
        files[expected.path] = expected
    return list(files.values())


def markdown(plan: Plan) -> int:
    checked = 0
    for name in plan.primary_markdown:
        path = REPO / name
        require(path.is_file() and not path.is_symlink(), "primary Markdown absent")
        text = path.read_text()
        require(not CONFLICT.search(text), "primary Markdown conflict markers")
        for match in LINK.finditer(text):
            destination = match.group(1) or match.group(2)
            parts = urlsplit(destination)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            target = unquote(parts.path)
            target = re.sub(r":\d+$", "", target)
            resolved = (path.parent / target).resolve()
            require(
                resolved.is_relative_to(REPO.resolve()) and resolved.exists(),
                "primary Markdown local link missing or outside portable repo: "
                + destination,
            )
            checked += 1
    return checked


def field(value: JsonValue, dotted: str) -> JsonValue:
    current = value
    for key in dotted.split("."):
        require(
            isinstance(current, dict) and key in current,
            "observed claim field missing: " + dotted,
        )
        if not isinstance(current, dict):
            raise TypeError("observed claim field missing")
        current = current[key]
    return current


def claims(plan: Plan) -> list[Pin]:
    result: list[Pin] = []
    for claim in plan.observed_claims:
        require(
            pin(claim.evidence.path) == claim.evidence,
            "linked observed claim evidence changed",
        )
        value = decoded(claim.evidence.path)
        for name, expected in claim.expected_fields.items():
            actual = field(value, name)
            require(
                type(actual) is type(expected) and actual == expected,
                "observed claim contradicts linked evidence: "
                + claim.name
                + "/"
                + name,
            )
        result.append(claim.evidence)
    return result


def save(path: Path, receipt: Receipt) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x") as stream:
        stream.write(receipt.model_dump_json(indent=2) + "\n")
    temporary.replace(path)


def run(configuration: Path) -> int:
    configuration_pin = pin(configuration)
    plan = Plan.model_validate_json(configuration.read_bytes())
    require(not plan.output.exists(), "fresh metadata verdict root required")
    helpers = [pin(HELPERS / n) for n in plan.helpers]
    require(
        all(
            (p.bytes, p.sha256)
            == (plan.helpers[p.path.name].bytes, plan.helpers[p.path.name].sha256)
            for p in helpers
        ),
        "frozen documentation helpers differ",
    )
    plan.output.mkdir(exist_ok=False)
    receipt = Receipt(
        observed_utc=utc(),
        outcome="checking",
        mode=plan.mode,
        repo=REPO,
        actual_commit=plan.commit,
        admitted_tree=plan.tree,
        configuration=configuration_pin,
        helpers=helpers,
    )
    destination = plan.output / "receipt.json"
    save(destination, receipt)
    try:
        receipt.source_before = source(plan)
        receipt.detached = True
        receipt.checks.append(
            Check(
                name="exact_source_tree",
                passed=True,
                detail="Actual detached HEAD, staged/working tree and docs-only changed-file scope admitted.",
            )
        )
        git("diff", "--check", plan.base_commit, plan.tree, "--")
        git("diff", "--check")
        git("diff", "--cached", "--check")
        receipt.checks.append(
            Check(
                name="diff_check", passed=True, detail="Actual Git diff checks passed."
            )
        )
        changed = identity_files(plan)
        members = check_manifests(plan)
        parsed = check_json_and_conflicts(
            list({p.path: p for p in [*changed, *members]}.values())
        )
        codex = REPO / "codex-to-codex.md"
        require(not CONFLICT.search(codex.read_text()), "coordination conflict markers")
        receipt.checks.append(
            Check(
                name="portable_json_members_archives",
                passed=True,
                detail=f"{len(members)} manifest/archive identities checked; {parsed} JSON members parsed; source/coordination conflict checks passed.",
            )
        )
        count = markdown(plan)
        linked = claims(plan)
        receipt.checks.append(
            Check(
                name="primary_links_observed_claims",
                passed=True,
                detail=f"{count} local primary Markdown links and {len(linked)} explicitly pinned observed claims checked; archived Markdown sketches were not interpreted.",
            )
        )
        receipt.files = list(
            {p.path: p for p in [*changed, *members, *linked]}.values()
        )
        require(
            all(
                pin(p.path) == p for p in [configuration_pin, *helpers, *receipt.files]
            ),
            "final metadata/helper/configuration identity closure differs",
        )
        receipt.source_after = source(plan)
        require(
            receipt.source_after == receipt.source_before,
            "documentation source changed during gate",
        )
        receipt.checks.append(
            Check(
                name="final_identity_closure",
                passed=True,
                detail="Exact source and all checked file identities remained unchanged.",
            )
        )
        receipt.outcome = (
            "passed_candidate_documentation_metadata"
            if plan.mode == "candidate"
            else "passed_committed_documentation_metadata"
        )
    except BaseException as error:  # noqa: BLE001 - every actual metadata/source failure is retained as failure.
        receipt.outcome = "error"
        receipt.errors.append(f"{type(error).__name__}: {error}")
        receipt.checks.append(
            Check(name="failed_qualification", passed=False, detail=str(error))
        )
    receipt.observed_utc = utc()
    save(destination, receipt)
    print(receipt.outcome + " " + str(destination))
    return 0 if receipt.outcome.startswith("passed_") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    return run(parser.parse_args().plan)


if __name__ == "__main__":
    raise SystemExit(main())
