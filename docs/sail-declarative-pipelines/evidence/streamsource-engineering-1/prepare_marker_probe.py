"""Create an isolated harness with byte-identical pinned Sail source files.

No reviewed source file is changed. The harness is not a Sail workspace gate.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil


SOURCE = Path("/Users/alexy/src/sail/tmp/streamsource-review-20261105-85c6cca01")
PROBE = Path("/Users/alexy/src/sail/tmp/streamsource-probes-20261105")
EVIDENCE = Path(__file__).resolve().parent
REVISION = "85c6cca01cd521dd778bc200c987a34edf141de1"


@dataclass(frozen=True, slots=True)
class SourceFile:
    source: str
    destination: str
    sha256: str
    credit: str


def main() -> None:
    PROBE.mkdir(exist_ok=False)
    relative_files = [
        "src/array/placeholder.rs",
        "src/streaming/event/mod.rs",
        "src/streaming/event/encoding.rs",
        "src/streaming/event/marker.rs",
        "src/streaming/event/schema.rs",
        "src/streaming/event/stream.rs",
        "proto/sail/streaming/marker.proto",
        "build.rs",
    ]
    records: list[SourceFile] = []
    for relative in relative_files:
        source_relative = "crates/sail-common-datafusion/" + relative
        source = SOURCE / source_relative
        destination = PROBE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append(SourceFile(
            source_relative,
            relative,
            sha256(source.read_bytes()).hexdigest(),
            f"[CREDIT] https://github.com/lakehq/sail/blob/{REVISION}/{source_relative}",
        ))
        assert source.read_bytes() == destination.read_bytes()
    shutil.copyfile(SOURCE / "Cargo.lock", PROBE / "Cargo.lock")
    shutil.copyfile(EVIDENCE / "marker_probe.rs", PROBE / "src/main.rs")
    (PROBE / "src/lib.rs").write_text(
        "// Source files are copied unchanged; see SOURCE-MANIFEST.json for [CREDIT].\n"
        "pub mod array { pub mod placeholder; }\n"
        "pub mod streaming { pub mod event; }\n"
    )
    (PROBE / "Cargo.toml").write_text('''[package]
name = "streamsource-marker-probe"
version = "0.1.0"
edition = "2024"

[workspace]

[dependencies]
datafusion = { version = "=55.2.0", default-features = false }
datafusion-common = "=55.2.0"
datafusion-expr = { version = "=55.2.0", default-features = false }
datafusion-physical-expr = "=55.2.0"
datafusion-physical-plan = "=55.2.0"
arrow = "=59.2.0"
chrono = "=0.4.45"
futures = "=0.3.34"
pin-project-lite = "=0.2.17"
prost = "=0.14.4"
tonic = { version = "=0.14.9", default-features = false, features = ["codegen"] }
serde_json = "=1.0.154"

[build-dependencies]
tonic-prost-build = "=0.14.9"

[profile.dev]
debug = 0
incremental = false
''')
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision": REVISION,
        "source_root": str(SOURCE),
        "probe_root": str(PROBE),
        "files": [asdict(item) for item in records],
        "source_cargo_lock_sha256": sha256((SOURCE / "Cargo.lock").read_bytes()).hexdigest(),
        "scope": "Unchanged event/placeholder modules compiled in a minimal standalone crate; not the Sail planner or runtime",
    }
    (PROBE / "SOURCE-MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (EVIDENCE / "marker-source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(PROBE)


if __name__ == "__main__":
    main()
