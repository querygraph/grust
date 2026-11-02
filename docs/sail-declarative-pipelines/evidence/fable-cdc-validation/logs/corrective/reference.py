"""Python reference of the CF-0007 traversal, checked against lookup-oracle.json. ROOT lowercase here is
Python's str.lower(), adequate only because the oracle's non-ASCII names avoid the known JDK differences
except where noted; the Rust test uses the pinned JDK port."""
import json, sys
def jhash(s):
    b = s.encode('utf-16-be'); h = 0
    for i in range(0, len(b), 2):
        h = (31 * h + int.from_bytes(b[i:i+2], 'big')) & 0xFFFFFFFF
    return h
def improve(h):
    m = 0xFFFFFFFF
    h = (h + ((~(h << 9)) & m)) & m
    h ^= h >> 14
    h = (h + (h << 4)) & m
    h ^= h >> 10
    return h
def java_lower(s):
    # JDK ROOT: İ -> i̇ ; final sigma handled crudely (word of letters only)
    out = []
    for i, c in enumerate(s):
        if c == 'İ': out.append('i̇')
        elif c == 'Σ':
            before = any(x.isalpha() for x in s[:i]); after = any(x.isalpha() for x in s[i+1:])
            out.append('ς' if before and not after else 'σ')
        elif c in ('\U00010570', '\u1C89'): out.append(c)  # JDK 17 leaves these
        else: out.append(c.lower())
    return ''.join(out)
def traversal(records):
    # records: list of (name, last_index) in first-insertion order
    if len(records) <= 4: return list(records)
    hashed = [(improve(jhash(n)), n, i) for n, i in records]
    out = []
    def visit(items, shift):
        if shift >= 32:
            out.extend((n, i) for _, n, i in items); return
        groups = {}
        for h, n, i in items: groups.setdefault((h >> shift) & 31, []).append((h, n, i))
        for b in sorted(groups):
            if len(groups[b]) == 1: out.append((groups[b][0][1], groups[b][0][2]))
        for b in sorted(groups):
            if len(groups[b]) > 1: visit(groups[b], shift + 5)
    visit(hashed, 0)
    return out
def build(fields):
    records = []; pos = {}
    for i, f in enumerate(fields):
        if f in pos: records[pos[f]] = (f, i)
        else: pos[f] = len(records); records.append((f, i))
    exact = {n: i for n, i in records}
    insens = {}
    for n, i in traversal(records): insens[java_lower(n)] = i
    return exact, insens
d = json.load(open(sys.argv[1]))
bad = 0; total = 0
for c in d['cases']:
    exact, insens = build(c['fields'])
    for q in c['queries']:
        total += 1
        e = exact.get(q['name'], -1); s = insens.get(java_lower(q['name']), -1)
        if (e, s) != (q['exact'], q['insensitive']):
            bad += 1
            if bad <= 15: print('MISMATCH', c['fields'], q, 'model', (e, s))
print('queries', total, 'mismatches', bad)
