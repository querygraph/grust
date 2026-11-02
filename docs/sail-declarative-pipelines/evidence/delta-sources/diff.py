import json,re,sys
def load(p): return {c['label']:c for c in json.load(open(p))}
a=load(sys.argv[1]); b=load(sys.argv[2]); same=0; diffs=[]
def inner(r):
    m=re.findall(r'\[([A-Z][A-Z_0-9.]+)\]',r.get('message') or '')
    return m[-1] if 0 else (m[1] if len(m)>1 and m[0]=='STREAM_FAILED' else (m[0] if m else None))
def norm(x): return re.sub(r"datetime\.datetime\([^)]*\)","TS",x)
for k in a:
    if k not in b: diffs.append((k,'missing')); continue
    ra=[x for x in a[k]['log'] if 'run' in x]; rb=[x for x in b[k]['log'] if 'run' in x]
    sa=[(r['outcome'],r.get('condition'),inner(r),[norm(x) for x in r['rows']] if r['rows'] is not None else None,r.get('columns')) for r in ra]
    sb=[(r['outcome'],r.get('condition'),inner(r),[norm(x) for x in r['rows']] if r['rows'] is not None else None,r.get('columns')) for r in rb]
    ea=[x.get('condition') for x in a[k]['log'] if 'sql' in x and 'error' in x]; eb=[(x.get('condition') or x['message'][:90]) for x in b[k]['log'] if 'sql' in x and 'error' in x]
    if sa==sb and not eb: same+=1
    else:
        diffs.append((k,sa,sb,eb))
print('same',same,'different',len(diffs),'of',len(a))
for d in diffs:
    print('##',d[0])
    if len(d)==2: continue
    for x,y in zip(d[1],d[2]):
        if x!=y: print('  spark',str(x)[:230]); print('  sail ',str(y)[:230])
    if len(d[1])!=len(d[2]): print('  runs',len(d[1]),len(d[2]))
    if d[3]: print('  sailsql',str(d[3])[:300])
