#!/usr/bin/env python3
"""Require the Sedona wheel's GEOS dependencies to resolve inside the wheel."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile


def check(wheel):
    with tempfile.TemporaryDirectory(prefix="sail-wheel-check-") as temporary:
        root = Path(temporary).resolve()
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)
        libraries = [path for path in root.rglob("*") if path.is_file() and
                     (path.name.endswith((".so", ".dylib")) or ".so." in path.name)]
        geos = [path for path in libraries if "geos" in path.name.lower()]
        if len(geos) < 2:
            raise RuntimeError("Sedona wheel must contain both GEOS C and C++ shared libraries")
        links = {}
        for library in libraries:
            if platform.system() == "Darwin":
                output = subprocess.check_output(["otool", "-L", str(library)], text=True)
                dependencies = [line.strip().split(" (", 1)[0] for line in output.splitlines()[1:]]
                # A dylib's own install ID appears in -L output but is not a dependency.
                ids = subprocess.check_output(["otool", "-D", str(library)], text=True).splitlines()[1:]
                dependencies = [name for name in dependencies if name not in ids]
                for name in dependencies:
                    if name.startswith(("/usr/lib/", "/System/Library/")):
                        continue
                    if not name.startswith("@loader_path/"):
                        raise RuntimeError(f"external native dependency in {library.name}: {name}")
                    resolved = (library.parent / name.removeprefix("@loader_path/")).resolve()
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        raise RuntimeError(f"unresolved bundled dependency: {name}")
            elif platform.system() == "Linux":
                output = subprocess.check_output(["patchelf", "--print-needed", str(library)], text=True)
                dependencies = output.splitlines()
                bundled = {path.name for path in libraries}
                for name in dependencies:
                    if "geos" in name.lower() and name not in bundled:
                        raise RuntimeError(f"external GEOS dependency in {library.name}: {name}")
                if library.name.startswith("_native"):
                    rpath = subprocess.check_output(["patchelf", "--print-rpath", str(library)], text=True)
                    if "$ORIGIN" not in rpath:
                        raise RuntimeError("native module lacks a wheel-relative library search path")
            else:
                raise RuntimeError("wheel dependency check supports macOS and Linux")
            links[str(library.relative_to(root))] = dependencies
        return {"wheel": wheel.name, "bundled_geos": [str(path.relative_to(root)) for path in geos],
                "dependencies": links}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(check(args.wheel), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    print(result, end="")
