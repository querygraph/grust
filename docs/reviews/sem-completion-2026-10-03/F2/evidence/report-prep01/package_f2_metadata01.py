"""Package closed F2 bridge metadata; never import or run an engine."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import tarfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
ROOT = BASE / "report-prep01" / "F2-final01"
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


def archive(directory: Path) -> Pin:
    path = ROOT / f"{directory.name}-metadata.tar.gz"
    require(not path.exists(), "archive must be fresh")
    with tarfile.open(path, "w:gz") as output:
        for member in sorted(directory.rglob("*")):
            if member.is_file():
                require(
                    not member.is_symlink() and member.suffix in ALLOWED,
                    "archive non-metadata",
                )
                output.add(
                    member,
                    arcname=member.relative_to(directory).as_posix(),
                    recursive=False,
                )
    data = path.read_bytes()
    return Pin(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def package(
    topic: str, files: list[Path], source_pins: list[Pin], text: str
) -> tuple[Pin, Pin]:
    directory = ROOT / topic
    directory.mkdir(exist_ok=False)
    members: list[Member] = []
    included: set[Path] = set()
    for path in sorted(set(files)):
        if path.is_relative_to(BASE):
            relative = Path("evidence") / path.relative_to(BASE)
        else:
            relative = (
                Path("prior-evidence")
                / hashlib.sha256(str(path.parent).encode()).hexdigest()[:16]
                / path.name
            )
        members.append(copy(path, directory, relative))
        included.add(path)
    declared_by_path = {pin.path: pin for pin in source_pins}
    for pin in source_pins:
        path = Path(pin.path)
        if (
            path.suffix in {".py", ".toml", ".lock", ".rs", ".yaml"}
            and pin.bytes <= 1_000_000
            and path not in included
        ):
            require(identity(path) == pin, f"source differs from closed pin: {path}")
            parts = path.parts
            marker = parts.index("examples") if "examples" in parts else len(parts) - 1
            origin = hashlib.sha256(str(path).encode()).hexdigest()[:16]
            relative = Path("pinned-sources") / origin / Path(*parts[marker:])
            members.append(copy(path, directory, relative))
            included.add(path)
    # Read-back pins are observable packaging facts, not additional runtime gates.
    (directory / "README.md").write_text(text)
    generated = identity(directory / "README.md")
    members.append(
        Member(
            path="README.md",
            original="generated from closed evidence",
            bytes=generated.bytes,
            sha256=generated.sha256,
        )
    )
    excluded = [
        p for path, p in sorted(declared_by_path.items()) if Path(path) not in included
    ]
    manifest = Manifest(
        observed_utc=utc(),
        outcome="packaged_closed_metadata_only",
        topic=topic,
        members=members,
        excluded_payload_pins=excluded,
        scope="Full copied metadata/source identity inventory, with declared excluded payload pins retained from closed records. No binary/venv/wheel/Parquet payload reads or rehash; no engines, process probes, builds or validation jobs. Runtime waits/closure and numerical verdicts are preserved producer observations; no current-process or new-oracle claim.",
    )
    save(directory / "manifest.json", manifest)
    return identity(directory / "manifest.json"), archive(directory)


def main() -> None:
    report = BASE / "F2-fourphase-report02"
    receipt = object_at(report / "receipt.json")
    require(
        receipt["outcome"] == "reported_physically_qualified_bridge_execution"
        and receipt["series"] == 4
        and receipt["completed_full_writes"] == 8
        and receipt["full_physical_qualification"] == "eight_main_outputs_passed",
        "qualified four-phase summary required",
    )
    roots = [
        BASE / n
        for n in (
            "F2-fourphase01",
            "F2-fourphase-report01",
            "F2-fourphase-report02",
            "F2-fourphase-smoke01",
            "F2-fourphase-smoke02",
            "F2-fourphase-smoke03",
            "F2-fourphase-main03",
            "F2-fourphase-smoke03-oracle01",
            "F2-fourphase-main03-oracle-cit-Patents-int64-c1-01",
            "F2-fourphase-main03-oracle-cit-Patents-int64-c3-01",
            "F2-fourphase-main03-oracle-graph500-24-int64-c1-01",
            "F2-fourphase-main03-oracle-graph500-24-int64-c3-01",
        )
    ]
    files = [p for root in roots for p in metadata_tree(root)]
    files.append(Path(__file__))
    pins: list[Pin] = []
    for root in roots:
        for p in metadata_tree(root):
            if p.suffix == ".json":
                value = JSON.validate_json(read(p))
                pins.extend(declared(value))
    old = Path(
        "/Volumes/Apo/graph-tests/results/sem-review-20261001/F2a-native-024-run01"
    )
    files.extend(metadata_tree(old / "reports01"))
    for n in (
        "root-audit02/receipt.json",
        "root-audit02/raw-inventory.json",
        "input-admission01.json",
        "source-host-admission01.json",
        "client-admission01.json",
    ):
        files.append(old / n)
    for n in ("F2a-native-024-main-campaign02", "F2a-native-024-smoke-campaign02"):
        root = old.parent / n
        for name in ("receipt.json", "launch-receipt.json"):
            files.append(root / name)
    for name in (
        "plan.json",
        "receipt.json",
        "launch-receipt.json",
        "install01.json",
        "freeze02.json",
    ):
        files.append(old.parent / "F2a-native-int64-build01" / name)
    for expected in pins:
        p = Path(expected.path)
        if (
            p.suffix == ".json"
            and p.is_file()
            and not p.is_symlink()
            and p.stat().st_size < 1_000_000
        ):
            require(identity(p) == expected, "pinned prior metadata changed")
            files.append(p)
    for name in (
        "F2-fourphase-smoke03-oracle01",
        "F2-fourphase-main03-oracle-cit-Patents-int64-c1-01",
        "F2-fourphase-main03-oracle-cit-Patents-int64-c3-01",
        "F2-fourphase-main03-oracle-graph500-24-int64-c1-01",
        "F2-fourphase-main03-oracle-graph500-24-int64-c3-01",
    ):
        oracle = object_at(BASE / name / "receipt.json")
        require(
            oracle["outcome"] == "passed_full_physical_wcc"
            and oracle["errors"] == []
            and oracle["own_identity_closure_passed"] is True
            and oracle["full_output_oracle_passed"] is True,
            "closed full physical oracle required",
        )
        config = oracle["config"]
        require(isinstance(config, dict), "oracle config object required")
        if not isinstance(config, dict):
            raise TypeError("oracle config object required")
        datasets = [config["reference"]]
        outputs = config["outputs"]
        require(isinstance(outputs, list), "oracle outputs list required")
        if not isinstance(outputs, list):
            raise TypeError("oracle outputs list required")
        datasets.extend(outputs)
        for dataset in datasets:
            require(isinstance(dataset, dict), "raw dataset object required")
            if not isinstance(dataset, dict):
                raise TypeError("raw dataset object required")
            directory, members = dataset["directory"], dataset["files"]
            require(
                isinstance(directory, str) and isinstance(members, dict),
                "raw inventory fields required",
            )
            if not isinstance(directory, str) or not isinstance(members, dict):
                raise TypeError("raw inventory fields required")
            for filename, declaration in members.items():
                require(isinstance(declaration, dict), "raw file identity required")
                if not isinstance(declaration, dict):
                    raise TypeError("raw file identity required")
                pins.append(
                    Pin.model_validate(
                        {"path": str(Path(directory) / filename), **declaration}
                    )
                )
    retention = object_at(BASE / "F2-fourphase-main03/raw-archive-verification01.json")
    copied = retention["files"]
    require(isinstance(copied, list), "full retained copies required")
    if not isinstance(copied, list):
        raise TypeError("full retained copies required")
    for item in copied:
        require(isinstance(item, dict), "copy declaration required")
        if not isinstance(item, dict):
            raise TypeError("copy declaration required")
        pins.append(
            Pin.model_validate(
                {
                    "path": item["archive"],
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
            )
        )
    ROOT.mkdir(exist_ok=False)
    manifest, bundle = package(
        "F2",
        files,
        pins,
        "# F2 native client Arrow bridge evidence\n\n"
        "Four int64 conditions, eight full outputs, plus a separate three-output signed tiny control. "
        "All eleven outputs passed the closed full physical original-domain/partition oracle after engine closure. "
        "All eight main Parquets (217948036 bytes) were preserved on Apo with full matching SHA.\n\n"
        "The benchmark JSONs describe chunk_checkpoint_arrow_client_four_phase: full client Parquet-to-Arrow read; "
        "bounded inline IPC, eager unsorted checkpoint, balanced cached-reference unions, asStaged and projectionStats; "
        "all WCC calls with full Arrow result transport; all client Parquet writes. It is a separate profile, "
        "with n1/null standard deviation and raw shared-host phase observations, not a dedicated-host absolute "
        "benchmark or a native CSR-only/kernel-only or Sem resource/work parity claim. Parent Popen-to-wait is distinct.\n\n"
        "Original artifact-status and unset-checkpoint-path failures, original failed receipts and root manual "
        "closure records are included unchanged. Historical report01 was unvalidated when written; qualified "
        "report02 binds the later actual oracle receipts. The prior ordinary native-Parquet Grust0.24 int64/text "
        "one/three-call baseline is retained separately under prior-evidence; its exclusive four Sem phases are "
        "unavailable/null and it is not relabelled as this bridge.\n\n"
        "The manifest inventories every copied JSON/log/helper and declared excluded binary/wheel/venv/Parquet "
        "payload pin. Packaging opens only metadata/source files; it does not rerun numerics, engines or process probes.\n",
    )
    save(
        ROOT / "index.json",
        Manifest(
            observed_utc=utc(),
            outcome="packaged_closed_metadata_only",
            topic="F2-index",
            members=[],
            excluded_payload_pins=[manifest, bundle],
            scope="Manifest and source-only metadata archive identities.",
        ),
    )
    print(bundle.model_dump_json())


if __name__ == "__main__":
    main()
