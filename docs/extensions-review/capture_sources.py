#!/usr/bin/env python3
"""Capture immutable review listings; does not build or run the Sail samples."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

COMMIT = "bd8ce9ae8839477e2c08a0475ab7900b115c5366"
BASE = "a85d912d72ae03a6d97b6a3fd151f5752da636c6"
PLAIN = "4d31e15b350c975aed95c23e6cc7e7c51c59fe52"
ROOT = Path(__file__).resolve().parent


def capture(repo):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    def blob(path, revision=COMMIT):
        return git("show", f"{revision}:{path}")

    entries = []
    sedona = "examples/extensions/sedona/"
    specs = [
        ("sedona-lib", "rust", sedona + "src/lib.rs", "The native scalar adapter"),
        ("sedona-bootstrap", "python", sedona + "python/sail_sedona/__init__.py", "Discovery and binding"),
        ("sedona-cargo", "toml", sedona + "Cargo.toml", "Native package dependencies"),
        ("sedona-pyproject", "toml", sedona + "pyproject.toml", "Python packaging and entry point"),
        ("sedona-tests", "rust", sedona + "src/tests.rs", "Complete native adapter tests"),
        ("sedona-smoke", "python", sedona + "scripts/smoke.py", "Installed-wheel smoke check"),
        ("sedona-prepare", "python", sedona + "scripts/prepare.py", "Pinned dependency preparation"),
        ("sedona-patch", "diff", sedona + "patches/datafusion-55.patch", "Complete SedonaDB compatibility patch"),
        ("build-script", "bash", "examples/extensions/scripts/build.sh", "Original two-wheel build script"),
        ("wheel-check", "python", "examples/extensions/scripts/check_wheel.py", "Native wheel dependency check"),
        ("requirements", "text", "examples/extensions/requirements.lock", "Python dependency lock"),
        ("protocol", "protobuf", "crates/sail-spark-connect/proto/sail/extension/v1/extension.proto", "Complete relation envelope"),
        ("resource-abi", "rust", "crates/sail-native-resource-ffi/src/lib.rs", "Complete optional resource ABI"),
        ("resource-cargo", "toml", "crates/sail-native-resource-ffi/Cargo.toml", "Resource ABI crate manifest"),
    ]

    def save(identifier, language, source, title, data, printed=True, extra=None):
        relative = "code/source/" + source
        if extra:
            relative = "code/extracts/" + identifier + (".py" if language == "python" else ".sh")
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        row = dict(id="listing-" + identifier, language=language, source_path=source,
                   local_path=relative, title=title, sha256=hashlib.sha256(data).hexdigest(),
                   bytes=len(data), lines=len(data.splitlines()), printed=printed)
        row.update(extra or {})
        entries.append(row)

    for identifier, language, source, title in specs[:4]:
        save(identifier, language, source, title, blob(source))
    tutorial_path = "examples/extensions/TUTORIAL.md"
    tutorial = blob(tutorial_path).decode()
    step = tutorial.split("## 6. Sedona review: spatial SQL and a shuffle\n", 1)[1].split("## 7.", 1)[0]
    client = step.split("\n```bash\n", 1)[1].split("\n```", 1)[0]
    client = client.split("<<'PYCODE'\n", 1)[1].removesuffix("\nPYCODE") + "\n"
    first_line = tutorial[:tutorial.index(client)].count("\n") + 1
    save("sedona-client", "python", tutorial_path, "Complete spatial SQL and shuffle client",
         client.encode(), extra={"source_first_line": first_line,
                                 "source_last_line": first_line + len(client.splitlines()) - 1})
    for identifier, language, source, title in specs[4:]:
        save(identifier, language, source, title, blob(source))
    step5 = tutorial.split("## 5. Start a local Sail server\n", 1)[1].split("## 6.", 1)[0]
    startup = step5.split("\n```bash\n", 1)[1].split("\n```", 1)[0] + "\n"
    first_line = tutorial[:tutorial.index(startup)].count("\n") + 1
    save("server-start", "bash", tutorial_path, "Complete local server startup commands", startup.encode(),
         extra={"source_first_line": first_line, "source_last_line": first_line + len(startup.splitlines()) - 1})
    for name in ["Cargo.lock", "LICENSE-SEDONADB", "NOTICE-SEDONADB", "LICENSE-GEOS", "NOTICE", "README.md", "PORTING.md"]:
        save("support-" + name.lower().replace(".", "-"), "text", sedona + name,
             name, blob(sedona + name), printed=False)
    save("sail-license", "text", "LICENSE", "Sail source license", blob("LICENSE"), printed=False)
    manifest = dict(schema_version=1, repository="querygraph/sail", source_commit=COMMIT, files=entries)
    (ROOT / "code/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    main_prose = """# Complete code and reading path {#code-listings}

## The small author sample {#sample-path}

Read the first five listings consecutively: the native adapter, its Python
bootstrap, the two package manifests, and the spatial SQL/shuffle client.
The first four total 246 lines. The client is copied verbatim from the pinned
tutorial; its import of `functions as F` is retained even though this example
uses SQL strings. Expected assertions are distance 5.0 and distances 0 through
16 after repartition. These are expectations in the existing example, not a
new execution result from this documentation build.

Every printed source file below is complete. The client is the complete Python body of the tutorial example; server
startup is its complete shell block. Their source line intervals are recorded. Rust, Python, TOML, shell, protobuf and patch listings have
language tags for color syntax rendering. Long lines may wrap in exported
editions; the source bytes are preserved in the Markdown and code bundle.

## Running the sample {#running-the-sample}

Use a dedicated checkout with Rust 1.97.1, shared-library Python 3.12, uv,
protoc and a C/C++ toolchain; Sedona also needs GEOS 3.12 or newer. The pinned
tutorial describes platform setup. Review these commands before running them:
the original build script synchronizes its virtual environment and builds both
Sedona and Nutmeg. This document does not run it.

```bash
git clone https://github.com/querygraph/sail.git sail-extension-review
cd sail-extension-review
git checkout --detach bd8ce9ae8839477e2c08a0475ab7900b115c5366
bash examples/extensions/scripts/build.sh
.venv/bin/python examples/extensions/sedona/scripts/smoke.py
```

In terminal A use the complete [server startup](#listing-server-start) listing.
In terminal B save the [client](#listing-sedona-client) as a Python file and run
it with `SPARK_CONNECT_MODE_ENABLED=1 .venv/bin/python <client-file.py>` from
the checkout. Stop the server before changing execution modes. To exercise
separate workers, retain the startup exports and change its final launch to
`SAIL_MODE=local-cluster SAIL_EXPERIMENTAL_PROCESS_WORKERS=1` followed by the
same executable and arguments. A local shuffle alone does not prove remote
worker execution; placement must be observed in the selected deployment.

The code bundle preserves the original file paths, complete Cargo lockfile,
licenses and notices, and a SHA-256 manifest. Third-party library implementations
are pinned dependencies, not reprinted here. The much larger Sail integration
is documented separately in the [host implementation companion](../extensions-host-review/manuscript.md).
That companion includes the complete historical host patch, with a comparison
against the separately pinned plain-Sail revision.

## Listings {#sample-listings}

"""
    out = [main_prose]
    for row in entries:
        if not row["printed"]:
            continue
        data = (ROOT / row["local_path"]).read_text()
        url = f"https://github.com/querygraph/sail/blob/{COMMIT}/{row['source_path']}"
        if "source_first_line" in row:
            url += f"#L{row['source_first_line']}-L{row['source_last_line']}"
        out.append(f"### {row['title']} {{#{row['id']}}}\n\n")
        label = row['source_path'].replace('_', r'\_')
        out.append(f"Source: [{label}]({url}). {row['lines']} lines.\n\n")
        out.append(f"```{row['language']}\n{data}```\n\n")
    (ROOT / "code-listings.md").write_text("".join(out))

    host = ROOT.parent / "extensions-host-review"
    host.mkdir(exist_ok=True)
    patch = git("diff", "--no-ext-diff", "--full-index", BASE, COMMIT, "--", "crates", "Cargo.toml", "Cargo.lock")
    changed = git("diff", "--name-only", BASE, COMMIT, "--", "crates", "Cargo.toml", "Cargo.lock").decode().splitlines()
    chunks = re.split(rb"(?=^diff --git )", patch, flags=re.M)
    chunks = [part for part in chunks if part]
    assert len(chunks) == len(changed)
    host_entries = []
    host_text = ["""# Complete host integration patch {#host-code}

This appendix contains every changed line, with unified context, under `crates/`
and the workspace Cargo manifests/lockfile between the fork's actual upstream
base and the reviewed prototype. It includes generic integration, domain-specific
GraphUtils helpers, tests and dependency changes; inclusion is not a proposal
that every file belongs in the minimum extension API.

Patch base: `a85d912d72ae03a6d97b6a3fd151f5752da636c6`.
Patch result: `bd8ce9ae8839477e2c08a0475ab7900b115c5366`.
Present plain-Sail comparison: `4d31e15b350c975aed95c23e6cc7e7c51c59fe52`.

This is a complete historical integration patch, not a patch against present
plain Sail. It has not been rebased or qualified against that newer revision.
The source bundle also contains the complete affected files at each of those
three revisions when the file exists. Tests in this appendix are source
evidence; this document build does not rerun their historical runtime gates.

"""]
    for number, (source, chunk) in enumerate(zip(changed, chunks), 1):
        identifier = f"host-patch-{number:02d}"
        relative = f"code/patches/{number:02d}-{Path(source).name}.diff"
        target = host / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(chunk)
        row = dict(id=identifier, language="diff", source_path=source, local_path=relative,
                   title=source, sha256=hashlib.sha256(chunk).hexdigest(), bytes=len(chunk),
                   lines=len(chunk.splitlines()), printed=True)
        host_entries.append(row)
        host_text.append(f"## {number:02d}. {source} {{#{identifier}}}\n\n```diff\n{chunk.decode()}```\n\n")
        for label, revision in [("base", BASE), ("prototype", COMMIT), ("plain", PLAIN)]:
            if subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{revision}:{source}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                continue
            data = blob(source, revision)
            relative = f"code/{label}/{source}"
            target = host / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            host_entries.append(dict(id=f"{identifier}-{label}", language="text", source_path=source,
                                     local_path=relative, source_commit=revision,
                                     sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                                     lines=len(data.splitlines()), printed=False))
    license_data = blob("LICENSE")
    (host / "code/LICENSE").write_bytes(license_data)
    host_entries.append(dict(id="sail-license", language="text", source_path="LICENSE",
                             local_path="code/LICENSE", source_commit=COMMIT,
                             sha256=hashlib.sha256(license_data).hexdigest(), bytes=len(license_data),
                             lines=len(license_data.splitlines()), printed=False))
    (host / "code/host-integration.patch").write_bytes(patch)
    (host / "code/manifest.json").write_text(json.dumps(dict(
        schema_version=1, repository="querygraph/sail", source_commit=COMMIT,
        patch_base=BASE, plain_sail_commit=PLAIN, patch_files=len(changed), files=host_entries), indent=2) + "\n")
    (host / "host-code-listings.md").write_text("".join(host_text))
    for directory, name in [(ROOT, "sail-extensions-sample-code.zip"), (host, "sail-extensions-host-code.zip")]:
        (directory / "dist").mkdir(exist_ok=True)
        with zipfile.ZipFile(directory / "dist" / name, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted((directory / "code").rglob("*")):
                if file.is_file():
                    info = zipfile.ZipInfo(str(file.relative_to(directory)), (2026, 9, 30, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, file.read_bytes())
    print(json.dumps({"sample_files": len(entries), "sample_printed_lines": sum(r["lines"] for r in entries if r["printed"]),
                      "client_lines": next(r["lines"] for r in entries if r["id"] == "listing-sedona-client"),
                      "host_patch_files": len(changed), "host_patch_lines": len(patch.splitlines())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sail_repo", type=Path)
    capture(parser.parse_args().sail_repo)
