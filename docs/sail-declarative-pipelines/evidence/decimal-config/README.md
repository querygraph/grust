# Decimal policy capture and SET validation

Sail `226b0c1cfc9ac72dadc3ec8a81667f7acc3aacec`, parentb48162de9.
PlanConfig captures legacy_allow_negative_scale_of_decimal with defaultfalse.
SparkRuntimeConfig validates the known key before SET mutates the stored map,
retains the raw accepted string, and parses the same string into typed snapshots.
Overrides use the existing clone-and-apply path and leave the session untouched.

The pure Java-trim/strict-boolean step was extracted from the ORC path for reuse;
ORC's existing error mapping remains unchanged. The new key reports structured
INVALID_CONF_VALUE.TYPE_MISMATCH/22022 with original confName/confValue/confType
and SparkIllegalArgumentException's full parent chain for PySpark conversion.
A dev-only sail-function edge enables captured-settings→callable-caster tests;
Cargo.lock changes by one dependency-list entry, with no production dependency
or version changes. No cast routing, negative-target guard, folding, worker
codec or streaming snapshot interfaces changed.

## Qualification

Exact detached gates pass117 plan +183 Connect libraries, formatting and strict
Clippy. Native tests force4.2 metadata for default/syntax, preserve raw strings,
cover Java control trim/Unicode long-s and reset, and use actual session/override
snapshots to construct the callable decimal caster. Captured flagtrue changes
positive-target1e39 from unsupported-range to target-overflow; an old snapshot
retains its original behavior after SET/UNSET and an ANSI-off override returns
NULL. Invalid SET and overrides retain the parent value and all typed metadata.

Four production-only controls disable capture, pre-SET validation, Java trim
and exception hierarchy. Each fails0/1 with unchanged test bytes. Fresh exact CLI
build passes300 selected public tests +67 upstream Python tests. Independent
Spark4.2.1 Connect12 and Sail SDK12 agree on default/resetfalse, accepted strings,
raw returns, rejection rollback, exception type, condition, state and parameters.
A SELECT1 after every setting verifies the resulting config can still build a
query. All probes completed with no remaining recorded listeners.

## Failed evidence and environment correction

The initial test draft failed compilation on two Arc borrow/coercion expressions.
After fixing those test calls, the exact final candidate passed native181/183
Connect tests but two existing ORC default assertions saw Snappy instead of Zstd.
The invoking command omitted documented PYTHONPATH/VIRTUAL_ENV settings:
PYO3_PYTHON chooses the build interpreter but does not add virtualenv modules to
embedded Python, so version lookup fell back to Spark3.5 metadata. An env-only
control on the same commit and binary passes the affected test1/1; the complete
same-source gate then passes117+183 with the pinned Python3.12 site path. No
production code or expected values changed to fix this failure.

The operational library-gates helper now supplies and records all three Python
environment values, matching that passing gate's environment. Its old snapshot,
update hashes and the env-only control are retained. The durable helper manifest
is updated separately from the product source, preventing the same caller error.

Fable independently [accepts this unit](peer-review.md). Existing other boolean
settings still use older parsing paths; their NBSP/long-s differences are a
separate parity item. This unit's parser can be reused for those future changes.

verify.py checks immutable source/log/control hashes, the failed attempts and
env control, dev-only dependency delta, all public artifacts and SDK12 parity.
This is policy capture and SET behavior, not decimal SQL activation. The next
part of the flagged checkpoint is exact source/conditional folding and target-
type policy before resolver routing; prior folding/decimal conformance failures,
streaming/CDC and full original Spark SDP acceptance remain required.

Archived scripts use original absolute worktrees and /tmp paths. Read before
reuse. No push, release, provider/ownership or streaming activation was performed.
