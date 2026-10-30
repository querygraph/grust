"""Bounded two-resource protocol model; not a production/runtime/heap proof."""
from dataclasses import dataclass, replace
from collections import deque
import json

@dataclass(frozen=True)
class State:
    closing: bool = False
    used: int = 0
    resources: tuple = (None, None)  # None or (owned bytes, outcome uncertain)
    terminal: bool = False

    def bytes(self): return sum(r[0] for r in self.resources if r is not None)

    def update(self, i, value):
        values=list(self.resources);values[i]=value
        return replace(self,resources=tuple(values))

def successors(s):
    if s.terminal:return
    if not s.closing:
        for i,r in enumerate(s.resources):
            if not s.used & (1<<i) and s.bytes()<4:
                yield 'register-before-upload',replace(s.update(i,(1,False)),used=s.used|(1<<i))
            if r is not None and not r[1] and s.bytes()<4:
                yield 'reserve-before-allocation',s.update(i,(r[0]+1,False))
    yield 'seal-and-cancel',replace(s,closing=True)
    for i,r in enumerate(s.resources):
        if r is not None:
            if not r[1]:
                yield 'resource-confirmed-and-released',s.update(i,None)
                yield 'completion-response-lost',s.update(i,(r[0],True))
            else:
                # Requires an external confirmed outcome; mere elapsed time has
                # no edge releasing ownership or a resource's reservation.
                yield 'external-outcome-confirmed-and-released',s.update(i,None)
    if s.closing and all(r is None for r in s.resources):
        yield 'report-terminal-after-drain',replace(s,terminal=True)

seen={State()};queue=deque(seen);edges=0
while queue:
    s=queue.popleft()
    assert s.bytes()<=4
    assert not s.terminal or (s.closing and all(r is None for r in s.resources))
    for event,nxt in successors(s):
        edges+=1
        if s.closing:assert event not in ['register-before-upload','reserve-before-allocation']
        if event.endswith('released'):
            changed=[i for i in range(2) if s.resources[i]!=nxt.resources[i]]
            assert len(changed)==1 and nxt.resources[changed[0]] is None
            assert s.bytes()-nxt.bytes()==s.resources[changed[0]][0]
        if nxt not in seen:seen.add(nxt);queue.append(nxt)
old=[{'event':'upload-open','pending':1,'terminal':False},
     {'event':'cancel-select-drops-stream','pending':1,'terminal':False},
     {'event':'report-canceled','pending':1,'terminal':True}]
assert old[-1]['terminal'] and old[-1]['pending']
a=State(closing=True,used=1,resources=((1,False),None));b=State()
assert any(e=='register-before-upload' for e,_ in successors(b))
assert all(e!='register-before-upload' for e,_ in successors(a))
unknown=State(closing=True,used=1,resources=((1,True),None))
assert all(e!='report-terminal-after-drain' for e,_ in successors(unknown))
print(json.dumps({'scope':'Finite model with at most two lifetime resources and four abstract byte units; not runtime/fault-injection/allocator evidence',
 'states':len(seen),'edges':edges,'invariants':'passed','release_ownership':'per-resource',
 'legacy_counterexample':old,'separate_attempt_scopes':'passed',
 'unknown_outcome_requires_external_confirmation':'passed'},indent=2))
