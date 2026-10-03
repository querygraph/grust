"""The remote shape over Arrow Flight SQL: `sail flight server`, a pyarrow.flight client, the same expand query.

    python flight_probe.py <graph> <layout> <frontier_level> <cell>

Flight SQL commands are protobuf `Any` messages. pyarrow ships a Flight client but no Flight SQL
messages, so the two needed here are encoded by hand (CommandStatementQuery, field 1 = query).
The ticket the server returns is passed back unchanged. One JSON line per measurement goes to
raw/flight-<graph>-<layout>.jsonl.
"""
import json, pathlib, statistics, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pyarrow.flight as fl
from vizserver import sail, SCRATCH, host_facts
from quadsql import key_range, shift

graph, layout, lf, c = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
root = SCRATCH / graph / layout
raw = pathlib.Path(__file__).parent / "raw" / f"flight-{graph}-{layout}.jsonl"


def varint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(number, payload):
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def statement(sql):
    inner = field(1, sql.encode())
    return field(1, b"type.googleapis.com/arrow.flight.protocol.sql.CommandStatementQuery") + field(2, inner)


def run(client, sql):
    info = client.get_flight_info(fl.FlightDescriptor.for_command(statement(sql)))
    return client.do_get(info.endpoints[0].ticket).read_all()


def log(**record):
    record = {"graph": graph, "layout": layout, **record}
    print(json.dumps(record), flush=True)
    with raw.open("a") as f:
        f.write(json.dumps(record) + "\n")


lc1 = lf + 1
lo, hi = key_range(c, lf)
s1 = shift(lc1)
QUERIES = {
    "children-precomputed": f"SELECT * FROM levels{lc1} WHERE cell BETWEEN {4 * c} AND {4 * c + 3}",
    "expand-pe-precomputed-sorted": f"""
        SELECT src_cell, CASE WHEN dst_cell >> 2 = {c} THEN {lc1} ELSE {lf} END AS dst_level,
               CASE WHEN dst_cell >> 2 = {c} THEN dst_cell ELSE dst_cell >> 2 END AS dst_cell2, sum(w) AS w
        FROM pe{lc1} WHERE src_cell BETWEEN {4 * c} AND {4 * c + 3} GROUP BY 1, 2, 3""",
    "expand-pe-on-demand-sorted": f"""
        SELECT src_key >> {s1} AS src_cell,
               CASE WHEN dst_key >> {s1 + 2} = {c} THEN {lc1} ELSE {lf} END AS dst_level,
               CASE WHEN dst_key >> {s1 + 2} = {c} THEN dst_key >> {s1} ELSE dst_key >> {s1 + 2} END AS dst_cell,
               count(*) AS w
        FROM ek WHERE src_key >= {lo} AND src_key < {hi} GROUP BY 1, 2, 3""",
}
TABLES = {f"levels{lc1}": root / f"levels/level={lc1}", f"pe{lc1}": root / f"pe-sorted/level={lc1}",
          "ek": root / "ek-sorted"}

with sail(command=("flight", "server")) as (port, server):
    log(measure="start", settings=server.settings, host=host_facts(), frontier=lf, cell=c)
    client = fl.FlightClient(f"grpc://127.0.0.1:{port}")
    for name, path in TABLES.items():
        run(client, f"CREATE TABLE {name} USING parquet LOCATION '{path}'")
    run(client, "SELECT 1")
    times = []
    for _ in range(3):
        t = time.perf_counter(); run(client, "SELECT 1"); times.append(time.perf_counter() - t)
    log(measure="flight-trivial-query", median=round(statistics.median(times), 4), min=round(min(times), 4),
        max=round(max(times), 4), runs=[round(x, 4) for x in times])
    for name, sql in QUERIES.items():
        t = time.perf_counter(); table = run(client, sql); first = time.perf_counter() - t
        times = []
        for _ in range(3):
            t = time.perf_counter(); table = run(client, sql); times.append(time.perf_counter() - t)
        log(measure=f"flight-{name}", median=round(statistics.median(times), 4), min=round(min(times), 4),
            max=round(max(times), 4), runs=[round(x, 4) for x in times], first=round(first, 4),
            result={"rows": table.num_rows, "arrow_bytes": table.nbytes})
