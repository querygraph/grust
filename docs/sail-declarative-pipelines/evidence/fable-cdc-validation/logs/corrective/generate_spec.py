"""Designed and seeded schemas for the StructType lookup oracle. Writes spec.txt (probe input)."""
import random, itertools, json
cases = []
def case(fields, queries=None):
    fields = list(fields)
    if queries is None:
        seen = []
        for f in fields + [f.lower() for f in fields] + [f.upper() for f in fields] + [f.swapcase() for f in fields]:
            if f not in seen: seen.append(f)
        queries = seen + ["absent"]
    cases.append((fields, list(queries)))
# Codex's 23 retained observations (seeds)
for f in (["a","A","a"],["a","A"],["A","a"],["a","A","b","c"],["a","A","b","c","d"],["b","c","d","a","A"],["a","b","c","d","e","a"]): case(f)
# four/five distinct boundary; raw length above four with four spellings; duplicate updates before/after
case(["a","A","b","B"]); case(["a","A","b","B","c"]); case(["a","A","b","B","a","A"]); case(["a","A","b","B","a","A","c"]); case(["A","a","A","a","A","a","b","c","d"])
case(["x","X","x","X","x","X","x","X","x","X"]); case(["x","X","y","Y","z","Z","x","X"])
# true full Java hash collisions and case variants
case(["Aa","BB"]); case(["BB","Aa"]); case(["Aa","BB","aa","bb"]); case(["Aa","BB","AaAa","BBBB","AaBB","BBAa"]); case(["aa","AA","Aa","BB","bb","aA","cc","C"]) 
case(["AaAa","BBBB","AaBB","BBAa","aaaa","bbbb","Aa","BB","a","b"])
# shared low-five-bit buckets and deeper prefixes: names whose improved hashes share low bits are found by search below
# permutations of a colliding set
base = ["a","A","b","B","c"]
for p in itertools.permutations(base): case(list(p), ["a","A","b","B","c","C"])
# empty and supplementary names, ROOT mismatch pairs
case(["","a",""]); case(["", "A", "a", "", "b"]); case(["\U00010400","\U00010428","a"]); case(["\U00010570","\U00010597","b","c","d","e"]); case(["Ᲊ","ᲊ","x","y","z","w"])
case(["İ","i","I","ı"]); case(["İ","i̇","I","ı","b"]); case(["Σ","σ","ς","ΟΔΟΣ","οδος","οδοσ"]); case(["ΟΔΟΣ","οδος","οδοσ","a","b","c"])
case(["Name","name","NAME","id","Id","ID","age","AGE"]); case(["name","Name","NAME","id","Id","ID","age","AGE","x"])
# seeded random schemas over a small alphabet of colliding spellings
rng = random.Random(20261030)
alphabet = ["a","A","b","B","c","C","aa","AA","Aa","aA","BB","bb","Bb","id","ID","Id","name","NAME","Name","x","X","y","Y","","Σ","σ","ς","İ","i","I","ı","\U00010400","\U00010428","k","K","z","Z","a1","A1","ab","AB","Ab","aB"]
for _ in range(360):
    n = rng.choice([1,2,3,4,5,5,6,7,8,9,10,12,16,24])
    fields = [rng.choice(alphabet) for _ in range(n)]
    case(fields)
# bucket-sharing probe: find ASCII names whose improved hash shares low 5 bits / low 10 bits with "a"
def jhash(s):
    h = 0
    for u in s.encode('utf-16-be'):
        pass
    units = [int.from_bytes(s.encode('utf-16-be')[i:i+2],'big') for i in range(0,len(s.encode('utf-16-be')),2)]
    for u in units: h = (31*h + u) & 0xFFFFFFFF
    if h >= 1<<31: h -= 1<<32
    return h
def improve(h):
    m = 0xFFFFFFFF
    h = (h + (~(h << 9))) & m
    h ^= (h & m) >> 14
    h = (h + (h << 4)) & m
    h ^= (h & m) >> 10
    return h & m
target = improve(jhash("a"))
share5 = [s for s in ("".join(p) for L in (1,2,3) for p in itertools.product("abcxyz", repeat=L)) if s != "a" and improve(jhash(s)) & 31 == target & 31][:6]
share10 = [s for s in ("".join(p) for L in (2,3,4) for p in itertools.product("abcdefgh", repeat=L)) if improve(jhash(s)) & 1023 == target & 1023][:4]
case(["a","A"] + share5); case(["a","A"] + share10 + ["q"]); case(share5 + ["A","a"]); case(["A"] + share10 + ["a","A","b"])
json.dump({"share5": share5, "share10": share10}, open("buckets.json","w"))
with open("spec.txt","w",encoding="utf-8") as f:
    for fields, queries in cases:
        f.write(f"{len(fields)}\n"); f.writelines(x+"\n" for x in fields); f.write(f"{len(queries)}\n"); f.writelines(x+"\n" for x in queries)
print("cases", len(cases), "queries", sum(len(q) for _, q in cases), "buckets", share5, share10)
