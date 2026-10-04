"""Admit a closed actual standalone Rust gate before committing its unchanged source."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
sys.path[:0] = [str(BASE / "C4-allocation-owner02"), str(BASE / "C2-observer-build01")]
import allocator_models as m
import allocator_owner as owner
import gate_owner as groups

TREE = "268779f765b88813ec737beb1b30442eb30a5e72"
EXPECTED = [
    "rustc-version",
    "cargo-version",
    "fmt",
    "clippy",
    "test",
    "release",
    "probe-01-4096-tuple-min",
    "probe-02-4096-min-by",
    "probe-03-100000-tuple-min",
    "probe-04-100000-min-by",
    "probe-05-100000-min-by",
    "probe-06-100000-tuple-min",
]


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["/usr/bin/git", "-C", str(repo), *args], text=True
    ).strip()


def check(root: Path, head: str, mode: str) -> None:
    receipt = m.Receipt.model_validate_json((root / "receipt.json").read_bytes())
    waited = m.Launch.model_validate_json((root / "launch-receipt.json").read_bytes())
    plan = m.Plan.model_validate_json(receipt.configuration.path.read_bytes())
    require(plan.root == root, "actual attempt root differs")
    require(
        receipt.outcome == "passed_native_factory_allocation_controls"
        and not receipt.errors
        and receipt.finished_utc is not None
        and receipt.immutable_source_tool_helper_closure
        and receipt.all_owned_groups_absent
        and receipt.locks_released,
        "actual complete owner gate required",
    )
    require(
        waited.outcome == "passed_waited_native_factory_controls"
        and not waited.errors
        and waited.returncode == 0
        and waited.waited
        and waited.owner_group_absent
        and waited.owner_pid == receipt.owner_pid
        and waited.configuration == receipt.configuration
        and waited.owner_receipt == owner.pin(root / "receipt.json"),
        "actual owner wait differs",
    )
    require(
        [step.name for step in receipt.steps] == EXPECTED,
        "complete twelve-step schedule required",
    )
    require(
        all(
            step.returncode == 0
            and step.waited
            and step.group_absent
            and not step.forced_cleanup
            and not groups.members(step.pgid)
            for step in receipt.steps
        ),
        "step lifecycle remains unqualified",
    )
    require(
        not groups.members(receipt.owner_pid)
        and not groups.members(waited.launcher_pid),
        "owner/supervisor still present",
    )
    owner.immutable(plan, receipt.configuration)
    require(
        receipt.binary is not None and owner.pin(receipt.binary.path) == receipt.binary,
        "actual optimized artifact differs",
    )
    for step in receipt.steps:
        require(
            step.log is not None and owner.pin(step.log.path) == step.log,
            "closed log differs",
        )
    require(
        all(
            not path.exists()
            for path in [
                Path("/tmp/morrobay-sem-completion-heavy.lock"),
                *[
                    BASE.parent / "sem-review-20261001" / name
                    for name in ("gate.lock", "serial-queue.lock")
                ],
                *[BASE / name for name in ("gate.lock", "serial-queue.lock")],
            ]
        ),
        "another graph job or retained owner lock exists",
    )
    repo = plan.source.parent
    require(
        git(repo, "rev-parse", "HEAD") == head and git(repo, "write-tree") == TREE,
        "actual Git source closure differs",
    )
    require(
        set(git(repo, "ls-files").splitlines())
        == {"probe/" + name for name in plan.source_files},
        "complete committed/staged source set differs",
    )
    status = git(repo, "status", "--porcelain=v1")
    if mode == "clean":
        require(
            not status and git(repo, "rev-parse", "HEAD^{tree}") == TREE,
            "clean committed source required",
        )
    else:
        require(
            all(line.startswith("A  probe/") for line in status.splitlines())
            and len(status.splitlines()) == len(plan.source_files),
            "candidate staged source differs",
        )
    print(
        "PASS actual Rust gates, six complete allocator controls, source/artifact/wait/group/lock closure"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--mode", choices=["candidate", "clean"], required=True)
    args = parser.parse_args()
    check(args.root, args.head, args.mode)
