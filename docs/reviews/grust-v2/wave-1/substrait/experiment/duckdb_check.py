"""Feed the experiment's Substrait plans to DuckDB's community substrait extension.

Usage: python3 duckdb_check.py <data dir> <raw dir> <scratch db path>
Needs the `duckdb` CLI on PATH. Standard library only.
For each plan: run it through from_substrait_json and compare row count and an
order-independent sum with DuckDB's own SQL for the same query.
"""
import json
import subprocess
import sys
from pathlib import Path

data, raw, db = sys.argv[1], Path(sys.argv[2]), sys.argv[3]


def duck(sql: str) -> tuple[bool, str]:
    p = subprocess.run(
        ["duckdb", "-list", "-noheader", db, "-c", sql],
        capture_output=True,
        text=True,
    )
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0 and "Error" not in out, out


setup = f"""
CREATE OR REPLACE TABLE v AS SELECT * FROM read_parquet('{data}/cit-Patents-v.parquet');
CREATE OR REPLACE TABLE e AS SELECT * FROM read_parquet('{data}/cit-Patents-e.parquet');
CREATE OR REPLACE TABLE np AS SELECT * FROM (VALUES
  (1, 'Person', '{{"name":"alice"}}'), (2, 'Person', '{{"name":"bob"}}'),
  (3, 'City', '{{"name":"rome"}}')) AS t(id, label, props);
CREATE OR REPLACE TABLE npm AS SELECT id, map(['name'], [name]) AS m FROM (VALUES
  (1, 'alice'), (2, 'bob')) AS t(id, name);
"""
ok, out = duck(setup)
assert ok, out

lines = []


def say(s: str) -> None:
    print(s)
    lines.append(s)


_, ver = duck("SELECT version()")
_, ext = duck(
    "LOAD substrait; SELECT extension_version || ' ' || installed_from "
    "FROM duckdb_extensions() WHERE extension_name = 'substrait'"
)
say(f"duckdb {ver}; substrait extension {ext}")


def via_substrait(plan_json: str, select: str = "count(*)") -> tuple[bool, str]:
    lit = plan_json.replace("'", "''")
    return duck(f"LOAD substrait; SELECT {select} FROM from_substrait_json('{lit}')")


# Hand-built plans (Substrait spec v0.85.0, URN-declared standard functions).
for name, sql in [
    (
        "handbuilt-two-hop-rows",
        "SELECT count(*) FROM v n0 JOIN e e0 ON e0.source = n0.id JOIN v n1 ON n1.id = e0.target "
        "JOIN e e1 ON e1.source = n1.id JOIN v n2 ON n2.id = e1.target "
        "WHERE n0.id >= 4000000 AND n0.id < 4002000",
    ),
    (
        "handbuilt-two-hop-aggregate",
        "SELECT COUNT(*), SUM(n0.id), SUM(n1.id), SUM(n2.id) FROM v n0 JOIN e e0 ON e0.source = n0.id "
        "JOIN v n1 ON n1.id = e0.target JOIN e e1 ON e1.source = n1.id JOIN v n2 ON n2.id = e1.target",
    ),
]:
    plan = (raw / f"{name}.json").read_text()
    ok, out = via_substrait(plan, "count(*)" if name.endswith("rows") else "*")
    ok2, ref = duck(sql)
    say(f"{name}: from_substrait_json -> {'ok' if ok else 'ERROR'}: {out[:300]!r}; duckdb SQL: {ref}")

# Plans produced by datafusion-substrait 55.1.0.
for rec in map(json.loads, (raw / "coverage.jsonl").read_text().splitlines()):
    path = raw / "df-produced" / f"{rec['id']}.json"
    if not path.exists():
        say(f"{rec['id']}: no DataFusion-produced plan ({rec.get('produce_error', rec.get('plan_error', ''))[:80]})")
        continue
    ok, out = via_substrait(path.read_text())
    say(
        f"{rec['id']}: DataFusion plan -> DuckDB {'ok' if ok else 'ERROR'}: "
        f"{out.splitlines()[0][:200] if out else ''!r} (DataFusion SQL rows {rec['sql_rows']})"
    )

# DuckDB's own producer, then DataFusion-compatible check of what it emits.
ok, out = duck(
    "LOAD substrait; CALL get_substrait_json('SELECT n0.id AS a, n1.id AS b, n2.id AS c FROM v n0 "
    "JOIN e e0 ON e0.source = n0.id JOIN v n1 ON n1.id = e0.target JOIN e e1 ON e1.source = n1.id "
    "JOIN v n2 ON n2.id = e1.target WHERE n0.id >= 4000000 AND n0.id < 4002000')"
)
(raw / "duckdb-produced-two-hop.json").write_text(out + "\n")
ok2, back = via_substrait(out)
say(f"duckdb get_substrait_json(two-hop) -> {'ok' if ok else 'ERROR'}; round trip through from_substrait_json: {back[:200]!r}")

(raw / "duckdb-check.txt").write_text("\n".join(lines) + "\n")
