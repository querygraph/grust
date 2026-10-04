"""Bounded literal protocol and immutable host admission; credentials stay local."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import stat
import subprocess
import sys
import sysconfig
from datetime import UTC, datetime
from pathlib import Path

import x1_models as m

MAXIMUM_REQUEST = 128 * 1024
NATIVE_AUDIT = "native-resource-audit.jsonl"
ENVIRONMENT_KEYS = {
    "AWS_ENDPOINT",
    "AWS_ENDPOINT_URL",
    "AWS_ALLOW_HTTP",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "SAIL_EXPERIMENTAL_EXTENSIONS",
    "SAIL_MODE",
    "SAIL_EXPERIMENTAL_PROCESS_WORKERS",
    "SAIL_EXPERIMENTAL_WORKER_COMMAND",
    "SAIL_EXPERIMENTAL_HTTP2_KEEPALIVE_INTERVAL_SECS",
    "SAIL_EXPERIMENTAL_HTTP2_KEEPALIVE_TIMEOUT_SECS",
    "RUST_LOG",
    "SAIL_ARGENTEA_MEMORY_BYTES",
    "SAIL_NATIVE_RESOURCE_AUDIT",
    "NUTMEG_WORKERS",
    "RAYON_NUM_THREADS",
    "TOKIO_WORKER_THREADS",
    "SAIL_GRAPH_UTILS_ROOT",
    "X1_LOCAL_HOST",
}


def native_audit_path(request: m.Request) -> Path | None:
    configured = request.environment.get("SAIL_NATIVE_RESOURCE_AUDIT")
    if request.role not in ("driver", "worker"):
        require(configured is None, "only owned native processes admit audit paths")
        return None
    expected = request.root / NATIVE_AUDIT
    require(
        configured == str(expected), "native audit must use its exact owned role path"
    )
    return expected


def check_native_audit(request: m.Request) -> None:
    path = native_audit_path(request)
    if path is None:
        return
    metadata = path.lstat()
    require(
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600,
        "native audit must remain a same-UID regular 0600 file",
    )


def prepare_native_audit(request: m.Request) -> None:
    path = native_audit_path(request)
    if path is None:
        return
    metadata = request.root.lstat()
    require(
        stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == os.getuid(),
        "native audit requires its same-UID physical owned directory",
    )
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    check_native_audit(request)


def utc() -> str:
    return datetime.now(UTC).isoformat()


def require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def pin(path: Path) -> m.Pin:
    before = path.lstat()
    require(
        stat.S_ISREG(before.st_mode) and before.st_size <= 2**30,
        "regular bounded immutable file required",
    )
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require(
        (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ),
        "immutable file changed",
    )
    return m.Pin(path=path, bytes=after.st_size, sha256=digest)


def read(expected: m.Pin) -> bytes:
    require(
        expected.bytes <= 16 * 2**20 and pin(expected.path) == expected,
        "bounded metadata pin differs",
    )
    data = expected.path.read_bytes()
    require(pin(expected.path) == expected, "metadata changed while decoding")
    return data


def save(path: Path, value: m.Model) -> None:
    temporary = path.with_suffix(".writing")
    with temporary.open("w") as stream:
        stream.write(value.model_dump_json(indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def fresh_root(root: Path, target: m.Target) -> None:
    real = root.resolve()
    require(
        not root.exists() and not root.is_symlink(), "fresh evidence namespace required"
    )
    require(
        real != target.repo.resolve() and target.repo.resolve() not in real.parents,
        "physical evidence root must be outside source",
    )
    protected = [
        target.environment_file,
        *(item.path for item in target.helpers.values()),
    ]
    require(
        all(
            path.resolve() != real and real not in path.resolve().parents
            for path in protected
        ),
        "physical evidence root must not own helpers or credentials",
    )


def source(target: m.Target) -> dict[str, str]:
    def git(*argv: str) -> str:
        return subprocess.check_output(
            ["/usr/bin/git", "-C", str(target.repo), *argv], text=True, timeout=10
        ).strip()

    result = {
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "status": git("status", "--porcelain"),
    }
    require(
        result == {"head": m.SOURCE, "tree": target.tree, "status": ""},
        "exact clean current source differs",
    )
    return result


def identities(target: m.Target) -> list[m.Pin]:
    expected = [
        target.python_pin,
        target.python_library,
        *target.client_files,
        target.binary,
        target.wheel,
        target.identity_helper,
        target.assembly_receipt,
        *target.provenance,
        *target.helpers.values(),
    ]
    require(
        target.python.resolve() == target.python_pin.path
        and Path(sys.executable).resolve() == target.python_pin.path,
        "actual interpreter differs from admitted executable",
    )
    require(
        Path(__file__) == target.helpers["x1_io.py"].path
        and Path(m.__file__) == target.helpers["x1_models.py"].path,
        "actual loaded supervisor contract differs",
    )
    library = Path(str(sysconfig.get_config_var("LIBDIR"))) / "libpython3.12.dylib"
    require(
        library.resolve() == target.python_library.path,
        "actual CPython dylib differs from admitted physical library",
    )
    require(
        platform.python_version() == target.python_version,
        "actual native CPython patch version differs",
    )
    unique = {item.path: item for item in expected}
    require(
        all(unique[p.path] == p for p in expected),
        "conflicting complete host pins refused",
    )
    require(
        all(pin(p.path) == p for p in expected),
        "host source/artifact/helper identity differs",
    )
    return sorted(unique.values(), key=lambda value: str(value.path))


def assembly(target: m.Target) -> None:
    result = json.loads(read(target.assembly_receipt))
    require(
        result.get("outcome") == "passed_preserved_slice_artifact_assembly_only"
        and result.get("error") == "",
        "admitted preserved-slice assembly must have actually passed",
    )
    slices = result["slices"]
    require(
        len(slices) == 4
        and {(part["architecture"], part["role"]) for part in slices}
        == {
            (architecture, role)
            for architecture in ("x86_64", "arm64")
            for role in ("cli", "wheel")
        }
        and all(
            part["equal"] is True and part["input_sha256"] == part["recovered_sha256"]
            for part in slices
        ),
        "complete exact admitted slices were not preserved",
    )
    values = {(part["bytes"], part["sha256"]) for part in result["artifacts"]}
    require(
        (target.binary.bytes, target.binary.sha256) in values
        and (target.wheel.bytes, target.wheel.sha256) in values,
        "actual fat CLI/wheel differ from admitted assembly outputs",
    )
    entry = result["entry_point_choice"]
    require(
        entry["semantics_equal"] is True and entry["chosen_original_preserved"] is True,
        "original extension entry-point semantics were not preserved",
    )


def environment(target: m.Target, configured: dict[str, str]) -> dict[str, str]:
    require(
        all(
            (
                key in ENVIRONMENT_KEYS
                or key.startswith(
                    ("SAIL_CLUSTER__", "SAIL_EXECUTION__", "SAIL_RUNTIME__")
                )
            )
            and "\0" not in key
            and "\0" not in value
            for key, value in configured.items()
        ),
        "unadmitted nonsecret environment key",
    )
    # This trusted host-local file is neither copied, hashed nor serialized.
    metadata = target.environment_file.lstat()
    require(
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == os.getuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600,
        "owned 0600 private storage settings required",
    )
    with target.environment_file.open("rb") as stream:
        data = stream.read(MAXIMUM_REQUEST + 1)
    require(len(data) <= MAXIMUM_REQUEST, "bounded storage settings required")
    storage = json.loads(data)
    if isinstance(storage, dict) and set(storage) == {"access_key", "secret_key"}:
        storage = {
            "AWS_ACCESS_KEY_ID": storage["access_key"],
            "AWS_SECRET_ACCESS_KEY": storage["secret_key"],
        }
    require(
        isinstance(storage, dict)
        and all(
            isinstance(k, str)
            and isinstance(v, str)
            and (k.startswith("AWS_") or k == "SAIL_GRAPH_UTILS_ROOT")
            and "\0" not in k + v
            for k, v in storage.items()
        ),
        "storage file contains unadmitted settings",
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("SAIL_", "NUTMEG_", "AWS_", "PYTHON", "DYLD_", "LD_LIBRARY_")
        )
    }
    env.update(storage)
    env.update(configured)
    env.update(
        PYTHONHOME=sys.base_prefix,
        PYTHONPATH=sysconfig.get_paths()["purelib"],
        DYLD_LIBRARY_PATH=str(sysconfig.get_config_var("LIBDIR") or ""),
        X1_LOCAL_HOST=target.name,
    )
    return env


def command(target: m.Target, name: str, *argv: str) -> list[str]:
    native = native_command(target, name, *argv)
    if platform.machine() == target.architecture:
        return native
    ssh = target.ssh
    require(pin(ssh.admission.path) == ssh.admission, "actual route admission changed")
    host_options: list[str] = []
    if ssh.known_hosts is not None:
        require(
            pin(ssh.known_hosts.path) == ssh.known_hosts,
            "public known-host inventory changed",
        )
        host_options = [
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(ssh.known_hosts.path),
            "-o",
            "GlobalKnownHostsFile=/dev/null",
        ]
    return [
        "ssh",
        "-4",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "HostKeyAlias=" + ssh.host_key_alias,
        "-i",
        str(ssh.identity_file),
        *host_options,
        ssh.host,
        shlex.join(
            [
                "env",
                "-u",
                "PYTHONHOME",
                "-u",
                "PYTHONPATH",
                "-u",
                "DYLD_LIBRARY_PATH",
                *native,
            ]
        ),
    ]


def native_command(target: m.Target, name: str, *argv: str) -> list[str]:
    helper = target.helpers[name].path
    bootstrap = "import runpy,sys;sys.path[:0]=sys.argv[1:4];sys.argv=sys.argv[4:];runpy.run_path(sys.argv[0],run_name='__main__')"
    return [
        str(target.python),
        "-I",
        "-B",
        "-c",
        bootstrap,
        str(helper.parent),
        str(target.repo / "examples/extensions/argentea/python"),
        str(target.repo / "examples/extensions/graph-algorithms/src"),
        str(helper),
        *argv,
    ]


def process_rows() -> list[tuple[int, int, int]]:
    raw = subprocess.check_output(
        ["/bin/ps", "-axo", "pid=,pgid=,uid="], text=True, timeout=5
    )
    return [
        (int(v[0]), int(v[1]), int(v[2]))
        for line in raw.splitlines()
        if len(v := line.split()) == 3
    ]


def group_absent(pgid: int) -> bool:
    return not any(group == pgid for _, group, _ in process_rows())


def same_uid_group(pgid: int) -> list[int]:
    rows = [(pid, uid) for pid, group, uid in process_rows() if group == pgid]
    require(
        all(uid == os.getuid() for _, uid in rows),
        "foreign UID in recorded group; refuse signals",
    )
    require(pgid > 1 and pgid != os.getpgrp(), "refuse unrelated/self group")
    return [pid for pid, _ in rows]
