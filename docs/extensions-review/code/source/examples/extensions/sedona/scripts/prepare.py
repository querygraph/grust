#!/usr/bin/env python3
"""Fetch a fixed Apache SedonaDB revision and apply the reviewed DF55 port."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".deps" / "sedona-db"
REVISION = "0a1993d9be8bcf52150593ad08fc6a3412d50f29"
PATCH = ROOT / "patches" / "datafusion-55.patch"


def git(*args):
    return subprocess.run(["git", "-C", str(SOURCE), *args], check=True)


if not SOURCE.exists():
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout",
         "https://github.com/apache/sedona-db.git", str(SOURCE)],
        check=True,
    )
    git("checkout", "--detach", REVISION)
else:
    actual = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != REVISION:
        raise SystemExit(f"Expected Apache SedonaDB {REVISION}, found {actual}")

applied = subprocess.run(
    ["git", "-C", str(SOURCE), "apply", "--reverse", "--check", str(PATCH)],
    capture_output=True,
).returncode == 0
if not applied:
    git("apply", "--check", str(PATCH))
    git("apply", str(PATCH))

# A reversible patch alone does not prove that unrelated source was unchanged.
# Construct the expected patched tree with an isolated index, without resetting
# the checkout or touching its own index, and compare every tracked source file.
with tempfile.TemporaryDirectory(prefix="sail-sedona-source-") as temporary:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
    command = ["git", "-C", str(SOURCE)]
    subprocess.run(command + ["read-tree", REVISION], env=env, check=True)
    subprocess.run(command + ["apply", "--cached", str(PATCH)], env=env, check=True)
    expected = subprocess.check_output(command + ["write-tree"], env=env, text=True).strip()
    subprocess.run(command + ["diff", "--exit-code", expected, "--"], check=True)
    extras = subprocess.check_output(
        command + ["ls-files", "--others", "--exclude-standard"], text=True
    ).strip()
    if extras:
        raise SystemExit(f"Unexpected untracked files in pinned SedonaDB source:\n{extras}")
print(f"Apache SedonaDB {REVISION}, DF55 patch ready at {SOURCE}")
