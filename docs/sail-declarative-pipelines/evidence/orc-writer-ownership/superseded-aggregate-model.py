"""Finite protocol model, not Sail/ORC/runtime or allocator qualification."""
from dataclasses import dataclass, replace
from collections import deque
import json

@dataclass(frozen=True)
class State:
    closing: bool = False
    pending: int = 0
    reserved: int = 0
    terminal: bool = False


def successors(s):
    if not s.closing and not s.terminal and s.pending < 2 and s.reserved < 4:
        yield 'register-before-upload', replace(s, pending=s.pending+1, reserved=s.reserved+1)
    if not s.terminal and s.pending and s.reserved < 4:
        yield 'reserve-before-allocation', replace(s, reserved=s.reserved+1)
    if not s.terminal:
        yield 'seal-and-cancel', replace(s, closing=True)
    if s.pending and not s.terminal:
        # Models a confirmed completed/aborted effect. Unknown outcomes cannot
        # take this edge. Keep one reservation for every remaining resource.
        yield 'resource-confirmed-and-released', replace(s, pending=s.pending-1, reserved=s.pending-1)
    if s.closing and not s.pending and not s.reserved:
        yield 'report-terminal-after-drain', replace(s, terminal=True)

seen={State()}; queue=deque(seen); edges=0
while queue:
    current=queue.popleft()
    assert 0 <= current.pending <= 2 and current.pending <= current.reserved <= 4
    assert not current.terminal or (current.closing and current.pending==current.reserved==0)
    for event,nxt in successors(current):
        edges+=1
        assert not current.closing or event!='register-before-upload'
        if nxt not in seen:seen.add(nxt);queue.append(nxt)
# Source-supported counterexample to interpreting dropped execution as cleanup.
old=[{'event':'upload-open','pending':1,'terminal':False},
     {'event':'cancel-select-drops-stream','pending':1,'terminal':False},
     {'event':'report-canceled','pending':1,'terminal':True}]
assert old[-1]['terminal'] and old[-1]['pending']
# Two independent attempt scopes: cancelling A cannot seal B.
a=replace(State(pending=1,reserved=1),closing=True);b=State()
assert any(event=='register-before-upload' for event,_ in successors(b))
assert all(event!='register-before-upload' for event,_ in successors(a))
# An unknown remote completion retains ownership; elapsed time is not an ack.
unknown=State(closing=True,pending=1,reserved=1)
assert not any(event=='report-terminal-after-drain' for event,_ in successors(unknown))
print(json.dumps({'scope':'Finite abstract protocol only; no runtime/fault-injection/heap guarantee',
                  'states':len(seen),'edges':edges,'invariants':'passed',
                  'legacy_counterexample':old,'separate_attempt_scopes':'passed',
                  'unknown_outcome_blocks_clean_terminal':'passed'},indent=2))
