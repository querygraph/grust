# Delta replay source design evidence

The [design plan](../../DELTA-REPLAY-SOURCE.md) separates descriptor admission,
manifest capture and continuous reader/control integration. None is implemented
or qualified by this record. The earlier bounded Delta reader remains a reference.

`plan-before-code.json` pins the preceding plan. `source-inspection.md` identifies
inspected source revisions and reuse points; it reports no executed runtime tests.
The current request and constraints are retained in [the request record](REQUEST.txt)
and its linked predecessors. `descriptor-plan-before-code.json` pins the descriptor
admission and timestamp clarification before its implementation. These requirements
add no claim that a reader or recovery protocol has been built.

The design keeps descriptor and progress identities separate, uses existing storage
and resource interfaces, and states the limits of incarnation observations. Target
fencing and integrated recovery remain distinct qualification requirements.
