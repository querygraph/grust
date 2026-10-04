"""Package closed C2/D2/C4 observations and original metadata archives."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import stat
import tarfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
ROOT = BASE / "report-prep01" / "C2-D2-C4-final01"
ALLOWED = {
    ".json",
    ".jsonl",
    ".log",
    ".txt",
    ".csv",
    ".py",
    ".md",
    ".ini",
    ".toml",
    ".lock",
    ".yaml",
    ".rs",
}
PRUNED = {
    "venv",
    "raw",
    "raw-results",
    "outputs",
    "fixture",
    "wheels",
    "uv-cache",
    "target",
    "staging",
    "tmp",
    "temporary",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
}
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pin(Record):
    path: str
    bytes: int
    sha256: str


class Member(Pin):
    original: str


class Manifest(Record):
    observed_utc: str
    outcome: Literal["packaged_closed_metadata_only"]
    topic: str
    members: list[Member]
    excluded_payload_pins: list[Pin]
    scope: str


def utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def read(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), f"unsafe metadata: {path}")
    before = path.stat()
    require(
        before.st_size <= 16 * 1024**2 and path.suffix in ALLOWED,
        f"non-metadata/oversized: {path}",
    )
    content = path.read_bytes()
    after = path.stat()
    require(
        (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns),
        f"metadata changed: {path}",
    )
    return content


def object_at(path: Path) -> dict[str, JsonValue]:
    value = JSON.validate_json(read(path))
    require(isinstance(value, dict), f"JSON object required: {path}")
    if not isinstance(value, dict):
        raise TypeError("unreachable non-object")
    return value


def identity(path: Path) -> Pin:
    data = read(path)
    return Pin(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def declared(value: JsonValue) -> list[Pin]:
    found: list[Pin] = []
    if isinstance(value, dict):
        path, size, digest = value.get("path"), value.get("bytes"), value.get("sha256")
        if (
            isinstance(path, str)
            and isinstance(size, int)
            and isinstance(digest, str)
            and len(digest) == 64
        ):
            found.append(Pin(path=path, bytes=size, sha256=digest))
        for child in value.values():
            found.extend(declared(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(declared(child))
    return found


def metadata_tree(path: Path) -> list[Path]:
    found: list[Path] = []
    for directory, children, names in os.walk(path, followlinks=False):
        children[:] = sorted(c for c in children if c not in PRUNED)
        for name in sorted(names):
            candidate = Path(directory) / name
            if candidate.suffix in ALLOWED:
                found.append(candidate)
    return found


def copy(path: Path, destination: Path, relative: Path) -> Member:
    data = read(path)
    require(
        relative.is_absolute() is False and ".." not in relative.parts, "unsafe member"
    )
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    require(target.read_bytes() == data, "metadata copy differs")
    return Member(
        path=relative.as_posix(),
        original=str(path),
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def save(path: Path, value: Record) -> None:
    with path.open("x") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")


class RawMember(Member):
    archive: str


class RawCatalog(Record):
    observed_utc: str
    outcome: Literal["archived_closed_original_metadata"]
    archives: list[Pin]
    members: list[RawMember]
    total_original_bytes: int
    scope: str


def streaming_pin(path: Path) -> Pin:
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and before.st_size <= 512 * 2**20,
        "regular bounded original metadata required",
    )
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require(
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        "original metadata changed while hashing",
    )
    return Pin(path=str(path), bytes=after.st_size, sha256=digest)


def raw_relative(path: Path) -> Path:
    if path.is_relative_to(BASE):
        return Path("evidence") / path.relative_to(BASE)
    ssd = Path("/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003")
    require(
        path.is_relative_to(ssd),
        "original raw metadata outside admitted native run roots",
    )
    return Path("native-records") / path.relative_to(ssd)


def raw_archives(paths: list[Path], directory: Path) -> RawCatalog:
    archives: list[Pin] = []
    members: list[RawMember] = []
    groups: list[list[Path]] = [[]]
    size = 0
    for path in sorted(set(paths)):
        require(
            path.suffix in ALLOWED, "raw archive excludes every Parquet/binary payload"
        )
        actual_size = path.stat().st_size
        if size + actual_size > 160 * 2**20 and groups[-1]:
            groups.append([])
            size = 0
        groups[-1].append(path)
        size += actual_size
    for number, group in enumerate(groups, 1):
        if not group:
            continue
        archive_path = directory / f"raw-{number:02}.tar.gz"
        require(not archive_path.exists(), "fresh raw metadata archive required")
        with tarfile.open(archive_path, "w:gz", compresslevel=1) as output:
            for path in group:
                before = streaming_pin(path)
                relative = raw_relative(path)
                require(
                    not relative.is_absolute() and ".." not in relative.parts,
                    "unsafe raw archive member",
                )
                output.add(path, arcname=relative.as_posix(), recursive=False)
                require(
                    streaming_pin(path) == before,
                    "original raw metadata changed during archive",
                )
                members.append(
                    RawMember(
                        path=relative.as_posix(),
                        original=str(path),
                        bytes=before.bytes,
                        sha256=before.sha256,
                        archive=archive_path.name,
                    )
                )
        observed = streaming_pin(archive_path)
        require(
            observed.bytes <= 64 * 2**20,
            "compressed archive exceeds portable gate admission",
        )
        archives.append(observed)
    return RawCatalog(
        observed_utc=utc(),
        outcome="archived_closed_original_metadata",
        archives=archives,
        members=members,
        total_original_bytes=sum(m.bytes for m in members),
        scope="Complete original producer/action/system JSON, debug logs and private clocks, streamed before/after with exact per-member SHA. Archive content is metadata only; no Parquet/binary/wheel reads, engine/oracle/process probes or source mutation.",
    )


def alias(path: Path) -> str:
    return (Path("evidence") / path.relative_to(BASE)).as_posix()


def descriptive(value: JsonValue) -> JsonValue:
    """Keep counts/ratios; original absolute clocks remain archived verbatim."""
    if isinstance(value, dict):
        return {
            key: descriptive(child)
            for key, child in value.items()
            if key != "seconds" and not key.endswith("_seconds")
        }
    if isinstance(value, list):
        return [descriptive(child) for child in value]
    return value


def main() -> None:
    roots = [
        BASE / n
        for n in (
            "C2-D2-native01",
            "C2-D2-native02",
            "C2-D2-native03",
            "C2-D2-native04",
            "D2-native05",
            "C4-native01",
            "C4-native02",
        )
    ]
    all_files = [p for root in roots for p in metadata_tree(root)]
    small: list[Path] = []
    raw: list[Path] = []
    pins: list[Pin] = []
    for path in all_files:
        if path.suffix in {".log", ".jsonl"} or path.name.startswith("private-"):
            raw.append(path)
        else:
            small.append(path)
            if path.suffix == ".json":
                pins.extend(declared(JSON.validate_json(read(path))))
    specs = [
        (
            "C2",
            BASE / "C2-D2-native04/c2-main01",
            BASE / "C2-D2-native04/review/review.json",
            60,
            120,
        ),
        (
            "D2",
            BASE / "D2-native05/d2-main01",
            BASE / "D2-native05/independent-main-review01.json",
            3,
            420,
        ),
        (
            "C4",
            BASE / "C4-native02/pair03",
            BASE / "C4-native02/pair03/independent-executed-plan-review01.json",
            2,
            4,
        ),
    ]
    summaries: dict[str, dict[str, JsonValue]] = {}
    for topic, run, review_path, count, answers in specs:
        owner = object_at(run / "owner/receipt.json")
        waited = object_at(run / "wait.json")
        calls = owner["calls"]
        require(
            isinstance(calls, list)
            and len(calls) == count
            and owner["outcome"] == "completed_scoped_native_probe_queue"
            and owner["owned_locks_released"] is True
            and owner["errors"] == [],
            "closed positive owner differs",
        )
        require(
            waited["status"] == "actual_owner_wait_passed"
            and waited["returncode"] == 0
            and waited["actual_wait_completed"] is True
            and waited["owner_group_absent"] is True
            and waited["forced_kill"] is False
            and waited["source_before"] == waited["source_after"],
            "actual waited owner/source closure differs",
        )
        if not isinstance(calls, list):
            raise TypeError("calls list required")
        oracle_aliases: list[JsonValue] = []
        producer_aliases: list[JsonValue] = []
        qualified_answers = 0
        for call in calls:
            require(isinstance(call, dict), "call object required")
            if not isinstance(call, dict):
                raise TypeError("call object required")
            require(
                call["returncode"] == call["oracle_returncode"] == 0
                and call["wait_completed"] is True
                and call["oracle_wait_completed"] is True
                and call["child_group_absent"] is True
                and call["oracle_group_absent"] is True
                and call["forced_cleanup"] is False,
                "waited producer/oracle call closure differs",
            )
            producer, oracle = (
                Pin.model_validate(call["producer"]),
                Pin.model_validate(call["oracle"]),
            )
            require(
                streaming_pin(Path(producer.path)) == producer
                and identity(Path(oracle.path)) == oracle,
                "actual closed producer/oracle identity differs",
            )
            checked = object_at(Path(oracle.path))
            require(
                checked["outcome"] == "passed_scoped_native_probe"
                and checked["errors"] == []
                and checked["source_and_input_closure"] is True
                and checked["child_server_closure"] is True
                and checked["receipt"]
                == JSON.validate_json(producer.model_dump_json()),
                "scoped outside oracle differs",
            )
            answer_actions = checked["actions"]
            require(
                isinstance(answer_actions, list),
                "full outside-oracle answer actions required",
            )
            if not isinstance(answer_actions, list):
                raise TypeError("full outside-oracle answer actions required")
            require(
                all(
                    isinstance(a, dict) and a.get("full_answer_passed") is True
                    for a in answer_actions
                ),
                "outside-oracle full answer field differs",
            )
            qualified_answers += len(answer_actions)
            producer_root = Path(producer.path).parent
            raw.extend(metadata_tree(producer_root))
            oracle_aliases.append(alias(Path(oracle.path)))
            producer_aliases.append(raw_relative(Path(producer.path)).as_posix())
        require(
            qualified_answers == answers,
            "actual outside-oracle full answer count differs",
        )
        review = object_at(review_path)
        if topic == "C2":
            require(
                review["status"] == "independent_sixty_pair_scoped_review_passed",
                "C2 independent review differs",
            )
            groups = review["groups"]
            require(isinstance(groups, list), "C2 group summaries required")
            compact_groups: list[JsonValue] = []
            if not isinstance(groups, list):
                raise TypeError("C2 groups list required")
            for group in groups:
                require(isinstance(group, dict), "C2 group object required")
                if not isinstance(group, dict):
                    raise TypeError("C2 group object required")
                quantiles = group["quantiles"]
                require(isinstance(quantiles, dict), "C2 quantile object required")
                if not isinstance(quantiles, dict):
                    raise TypeError("C2 quantile object required")
                compact_groups.append(
                    {k: v for k, v in group.items() if k != "quantiles"}
                    | {"cold_over_warm_quantiles": quantiles["cold_over_warm"]}
                )
            scope: JsonValue = "P4/16/32 each20 fresh servers, cold/warm pair with metadata bootstrap and two-worker readiness separately observed;120 full4096-group answers. Existing system metadata/debug graphs establish declared exchange/task placement only. Full phase attribution and physical memory accounting remain false; shared-host descriptive ratios only."
            facts: JsonValue = {"partition_groups": compact_groups}
            small.remove(review_path)
            raw.append(review_path)
        elif topic == "D2":
            require(
                review["outcome"] == "passed_independent_D2_main_metadata_review"
                and review["all180_rounds_strict_hash_2_1_0"] is True
                and review["full_answer_actions"] == 420,
                "D2 full answer/layout independent review differs",
            )
            scope = review["scope"]
            facts = descriptive(
                {
                    k: v
                    for k, v in review.items()
                    if k not in {"evidence", "observed_utc"}
                }
            )
            small.remove(review_path)
            raw.append(review_path)
        else:
            require(
                review["allocation_factory_qualified"] is False
                and review["generic_struct_min_baseline_measured"] is False,
                "C4 scope was expanded beyond actual qualification",
            )
            scope = review["qualifying_scope"]
            facts = descriptive(
                {k: v for k, v in review.items() if k != "observed_utc"}
            )
            small.remove(review_path)
            raw.append(review_path)
        summaries[topic] = {
            "observed_utc": utc(),
            "outcome": "packaged_closed_scoped_observations",
            "source": "9f0aa7d2a50f1258544d37c05dd19b3ff3d915b3",
            "fresh_producer_cells": count,
            "full_answer_actions": answers,
            "owner_receipt": alias(run / "owner/receipt.json"),
            "actual_wait_receipt": alias(run / "wait.json"),
            "outside_oracle_receipts": oracle_aliases,
            "raw_producer_members": producer_aliases,
            "independent_review": raw_relative(review_path).as_posix(),
            "full_server_phase_attribution": False,
            "physical_memory_accounting_qualified": False,
            "facts": facts,
            "scope": scope,
        }
    # Bind every preserved failed-attempt plan's actual raw output tree, without parsing its large action JSON.
    for path in small:
        if path.suffix == ".json" and path.stat().st_size < 100_000:
            value = JSON.validate_json(read(path))
            if isinstance(value, dict) and value.get("kind") in {
                "c2",
                "d2",
                "stream-logging",
                "c4-tuple-min",
                "c4-min-by",
            }:
                output = value.get("output")
                if isinstance(output, str):
                    actual = Path(output)
                    ssd = Path(
                        "/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003"
                    )
                    if actual.is_relative_to(ssd) and actual.is_dir():
                        raw.extend(metadata_tree(actual))
    ROOT.mkdir(exist_ok=False)
    directory = ROOT / "C2-D2-C4"
    directory.mkdir()
    catalog = raw_archives(raw, directory)
    save(directory / "raw-catalog.json", catalog)
    members: list[Member] = []
    for path in sorted(set(small)):
        relative = Path("evidence") / path.relative_to(BASE)
        members.append(copy(path, directory, relative))
    for name, summary in summaries.items():
        path = directory / f"{name}-summary.json"
        path.write_bytes(JSON.dump_json(summary, indent=2) + b"\n")
    for path in [
        directory / "raw-catalog.json",
        *(directory / f"{n}-summary.json" for n in summaries),
    ]:
        generated_identity = identity(path)
        members.append(
            Member(
                path=path.name,
                original="generated from closed pinned observations",
                bytes=generated_identity.bytes,
                sha256=generated_identity.sha256,
            )
        )
    text = (
        "# C2, D2 and C4 native scoped observations\n\n"
        "C2:60 fresh cold/warm pairs,120 full answers on4096 groups; bootstrap/readiness separate; declared exchange/task layout and sampled process resource evidence. P32 had15 sampled physical observation errors, retained in the compact facts. Detailed server phase/physical allocation accounting is not qualified.\n\n"
        "D2: P4/16/32 x20 rounds,180 exact hash-exchange declarations (2/1/0) and420 full answer actions. This is native9f unsorted RemoteCheckpoint, with actual runtime sort/join choices, not the historical sorted Nutmeg17 scan API.\n\n"
        "C4: two ordered fresh cells, four full4096-group/four-field answers and observed partial/final aggregate factories. This does not qualify allocator state size or a generic struct-MIN baseline. Shared-host diagnostic ratios only, no dedicated-host absolute results.\n\n"
        "Each compact summary has relative aliases to the readable owner/wait/oracle records and archived independent review/producer records. Compact facts contain shared-host descriptive ratios and counts only. `raw-catalog.json` inventories every complete original producer/action/system JSON, independent review, debug log and private clock with per-member SHA and archive alias. Original clocks are archival observations; absolute original pins are preserved verbatim in copied metadata.\n\n"
        "All failed native bootstrap/readiness/D2-sort-merge/C4 tie-sentinel attempts and root manual closures remain included. No engine, numerical oracle, current process probe or binary/Parquet read occurred in packaging.\n"
    )
    (directory / "README.md").write_text(text)
    readme_identity = identity(directory / "README.md")
    members.append(
        Member(
            path="README.md",
            original="generated from closed evidence",
            bytes=readme_identity.bytes,
            sha256=readme_identity.sha256,
        )
    )
    archived = {m.original for m in catalog.members}
    copied = {m.original for m in members}
    excluded = {
        p.path: p for p in pins if p.path not in copied and p.path not in archived
    }
    manifest = Manifest(
        observed_utc=utc(),
        outcome="packaged_closed_metadata_only",
        topic="C2-D2-C4",
        members=members,
        excluded_payload_pins=list(excluded.values()),
        scope="Readable frozen compact/config/helper/wait/outside-oracle/failure metadata identity inventory. Complete original producer/debug metadata is archive-only and separately cataloged; raw clocks remain archival observations. No new code, engine, allocation or numerical verdict.",
    )
    save(directory / "manifest.json", manifest)
    print(identity(directory / "manifest.json").model_dump_json())
    print(
        f"raw_archives={len(catalog.archives)} raw_members={len(catalog.members)} bytes={catalog.total_original_bytes}"
    )


if __name__ == "__main__":
    main()
