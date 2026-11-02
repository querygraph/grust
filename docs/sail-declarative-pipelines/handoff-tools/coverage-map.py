"""Map Spark's SDP test declarations to Sail tests, by suite citation and by name.

Usage: coverage-map.py SPARK_CHECKOUT SAIL_CHECKOUT OUT_JSON. A suite counts as cited when a Sail
test file names it. A case counts as named when a Sail test function has its normalized name.
Both are static: neither proves a port is faithful or that the original test ran.
"""
import collections, json, re, subprocess, sys
from pathlib import Path

spark, sail, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
here = Path(__file__).resolve().parent.parent
cases = json.loads((here / "spark-4.2.1-inventory.json").read_text())["cases"]
tests = sail / "python/pysail/tests/spark"
files = list(tests.rglob("*.py")) + list(tests.rglob("*.feature"))
rust = list((sail / "crates").rglob("*.rs"))
text = {f: f.read_text(errors="replace") for f in files + rust if "target" not in f.parts}
functions = set()
for f, body in text.items():
    if f.suffix == ".py":
        functions |= set(re.findall(r"def (test_\w+)", body))
    elif f.suffix == ".rs":
        functions |= set(re.findall(r"fn (\w+)", body))
functions = {x.removeprefix("test_") for x in functions}


def norm(name):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def source(path):
    return subprocess.check_output(["git", "-C", str(spark), "show", f"HEAD:{path}"], text=True).split("\n")


cache, result = {}, []
for case in cases:
    path = case["source"]
    lines = cache.setdefault(path, source(path))
    head = " ".join(lines[case["line"] - 1 : case["line"] + 2])
    literal = re.search(r'(?:test|gridTest|ignore)\(\s*"((?:[^"\\]|\\.)*)"', head)
    name = literal.group(1) if literal else None
    suite = path.split("/")[-1].removesuffix(".scala")
    cited = sorted({f.name for f, body in text.items() if suite in body})
    named = bool(name) and any(norm(name) == f or (len(norm(name)) > 24 and norm(name) in f) for f in functions)
    result.append({"id": case["id"], "suite": suite, "name": name, "cited_by": cited, "named": named})
summary = collections.OrderedDict()
for suite in sorted({r["suite"] for r in result}):
    rows = [r for r in result if r["suite"] == suite]
    summary[suite] = {
        "declarations": len(rows),
        "named": sum(r["named"] for r in rows),
        "cited_by": rows[0]["cited_by"][:4],
    }
out.write_text(json.dumps({"summary": summary, "cases": result}, indent=1) + "\n")
cited = sum(1 for r in result if r["cited_by"])
print(len(result), "declarations,", cited, "in a cited suite,", sum(r["named"] for r in result), "named")
for suite, row in summary.items():
    print(f'{row["declarations"]:4} {row["named"]:4} {suite:52} {",".join(row["cited_by"])[:60]}')
