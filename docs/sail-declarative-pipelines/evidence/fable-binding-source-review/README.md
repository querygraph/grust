# Initial bounded-read binding source review

Offer `ebf631edd3b41b288a2c4d899a7a82dd658582e1`, not integrated. CF-0140
records source-derived counterexamples: expression subqueries are ignored by the
QueryNode-only pre-walk, so unbound reads/helpers can reach resolution; duplicate
CTE precedence differs from the actual resolver; duplicate/ambiguous binding names
are collapsed into membership sets. See review.md for the exact requests.
No independent runtime verdict is claimed by this packet; the peer's gate is not
an integration verdict. The mixed batch/stream read rejection remains an explicit
first-component gap, not a permanent selected restriction. SHA256.json covers
packet files except itself. Keep later corrections separate from this offer.
