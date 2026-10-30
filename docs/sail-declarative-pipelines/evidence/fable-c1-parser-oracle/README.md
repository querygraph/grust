# Independent C1 attribute parser oracle

Fable's Sail commit `49f32b65d438e7115fd5918f7398611ec6154f7a` corrects
CDC source and attribute identifiers. This packet independently checks only its
attribute parser helper against the installed Spark 4.2.1 JVM implementation.

All **9,338 comparisons pass**: every string of length zero through five over
`a`, dot, backtick, space, é and a supplementary character, plus seven explicit
newline, carriage-return, tab, NUL and quoted-name cases. Each comparison checks
acceptance/rejection and every resulting name part using UTF-8 hex encoding.
The complete ordered inputs and both raw outputs are retained.

The Rust probe embeds the exact offered parser function, replacing Sail's result
and error construction with a unit-error stub. It uses Rust 1.98.1. The JVM probe
calls Spark's actual AttributeNameParser singleton on JDK17.0.8. All classpath jar
hashes match the earlier pinned [Spark helper oracle](../fable-column-oracles/README.md),
which records the Spark4.2.1 build revision `617618396087429b5627a86ce933bb0f5d6645cb`.
Source comparison also found the same control transitions as that pinned parser.

This supports accepting the parser helper correction. It does not check error
class/message/SQLSTATE, four-part SQL source parsing, handler precedence, full
Connect behavior, or the complete offered CDC unit. Those remain separate review
and integration gates. Fable's original working-worktree test results are not
upgraded to detached combined-tree gates by these probes.

[run_probe.py](run_probe.py) preserves the historical command harness and absolute
paths; its output/build directories must be fresh. [receipt.json](receipt.json)
records commands, versions, all jar hashes and the result. The offered source,
extracted Rust probe, JVM probe, compile logs and raw outputs are retained.
`provenance.json` hashes all packet files except itself. No server was started.
