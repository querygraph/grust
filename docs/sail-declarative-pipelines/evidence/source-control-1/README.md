# Source-control design evidence

This directory preserves the source-control plans recorded before their dependent
implementation, the initial specialist analyses and the full request with subsequent
clarifications. It is optional implementation evidence, outside the primary design
reading sequence.

The recorded starting source is `b6d73d6a644dc04b1e6749e171100808c874d788`.
`plan-before-code.json` identifies the original plan. The later lifecycle receipt
distinguishes the encoder extraction already begun under that plan from core control
work that had not begun. These are historical records, not claims that no code has
subsequently been written.

Source-control changes remain local, uncommitted and unqualified. The specialist
reports assess the proposed interface and tests; they are not final reviews of a
qualified implementation. A baseline compile does not verify those changes. Replay,
distributed control, transport alignment and durable pipeline recovery remain unbuilt.

The live rate ordinal describes one execution and is not a replay position. The
delivery plan separately proposes a Delta log source for the first real append path.
Its source, authority durability and enforcement still require implementation and
qualification.
