"""Pinned, isolated Spark test binaries and matching source verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

SPARK_PIN = "617618396087429b5627a86ce933bb0f5d6645cb"
SOURCE_ROOTS = (
    "sql/pipelines/src/test/scala",
    "sql/connect/server/src/test/scala/org/apache/spark/sql/connect/pipelines",
    "sql/hive/src/test/scala/org/apache/spark/sql/hive/pipelines",
)


@dataclass(frozen=True, slots=True)
class Artifact:
    filename: str
    url: str
    bytes: int
    sha256: str
    published_sha1: str
    source_prefix: str


@dataclass(frozen=True, slots=True)
class Binding:
    source: str
    sha256: str
    source_artifact: str


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(source: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *args])


def load_manifest(path: Path) -> list[Artifact]:
    data = json.loads(path.read_text())
    if data["spark_commit"] != SPARK_PIN or data["spark_version"] != "4.2.1":
        raise ValueError("Unexpected artifact source/version pin")
    return [Artifact(**entry) for entry in data["files"]]


def prepare(cache: Path, manifest: list[Artifact]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    expected = {entry.filename for entry in manifest}
    unexpected = {path.name for path in cache.glob("*.jar")} - expected
    if unexpected:
        raise ValueError(f"Unpinned classpath artifacts: {sorted(unexpected)}")
    for entry in manifest:
        if Path(entry.filename).name != entry.filename:
            raise ValueError("Artifact filename must be a single path component")
        path = cache / entry.filename
        if not path.exists():
            with urlopen(entry.url, timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != entry.sha256:
                raise ValueError(f"Downloaded checksum mismatch: {entry.filename}")
            path.write_bytes(data)
        if path.stat().st_size != entry.bytes or digest(path) != entry.sha256:
            raise ValueError(f"Cached artifact differs from pin: {path}")


def bind_sources(source: Path, cache: Path, manifest: list[Artifact]) -> list[Binding]:
    if git(source, "rev-parse", "HEAD").decode().strip() != SPARK_PIN:
        raise ValueError("Spark source checkout must remain at the source pin")
    expected = {
        path
        for path in git(
            source, "ls-tree", "-r", "--name-only", SPARK_PIN, "--", *SOURCE_ROOTS
        )
        .decode()
        .splitlines()
        if path.endswith(".scala")
    }
    bindings = []
    for entry in manifest:
        if not entry.source_prefix:
            continue
        with zipfile.ZipFile(cache / entry.filename) as jar:
            for name in jar.namelist():
                if not name.endswith(".scala") or "/pipelines/" not in name:
                    continue
                path = entry.source_prefix + name
                data = jar.read(name)
                if data != git(source, "show", f"{SPARK_PIN}:{path}"):
                    raise ValueError(f"Published source differs from pin: {path}")
                bindings.append(
                    Binding(path, hashlib.sha256(data).hexdigest(), entry.filename)
                )
    if {binding.source for binding in bindings} != expected:
        raise ValueError(
            "Published SDP test sources do not cover the pinned source tree"
        )
    return sorted(bindings, key=lambda binding: binding.source)
