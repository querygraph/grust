# Java-normalized ORC timezone profile evidence

This packet qualifies a complete portable profile for the selected Java baseline.
It does not claim a completed Sail runtime provider or universal Spark/JVM
timezone equivalence. Repository implementation, compilation and commits are
outside this evidence unit.

The selected artifact is [data/java-timezone-profiles.json](data/java-timezone-profiles.json):
**1,541,175 bytes**, SHA-256
`1f90695f80f862138bf1635b8727281eb7b0a76d838513eaf09675cb6ee7212b`.
It contains 631 exact names, 349 normalized profiles, 36 future cycles derived
from 37 distinct Java recurring-rule shapes, and 268 alias provenance entries.
There are 25,619 historical rows and 28,836 cycle rows, including cycle prefixes.
These are artifact sizes/counts, not runtime memory or performance measurements.

## Exact qualification

The profile pins Oracle Java `20.0.2+9-78`, tzdb `2023c`,
`sun.timezone.ids.oldmapping=false`, FORMAT locale `en-US`,
`java.util.GregorianCalendar`, and the ORC epoch text `2015-01-01 00:00:00`.
The corresponding UTC epoch is 1420070400 seconds. These are explicit exporter
inputs/provenance; Spark 4.2.1 alone does not determine the JVM's locale,
calendar, legacy-ID setting, rules database, or default timezone.

The generator accepts explicit locale and legacy-ID parameters so alternative
settings can produce separately identified profiles. Only the configuration
above is qualified by this packet. No runtime process should infer those
settings from its own environment. Driver and worker must agree on the exact
compiled profile identity, separately from the captured reader-zone name and
the SQL/Arrow display timezone.

The offset query domain is
`[-9223380626789368, 9223380626789367]` epoch milliseconds. It is
`floor(i64 microsecond endpoint / 1000)`, expanded by `4 * 2^31` milliseconds
on each side. A difference between two i32 offsets has magnitude less than
`2 * 2^31` milliseconds. One such difference relates original and final
instants; the second covers Java ORC's candidate re-query `t + w - r`.
The envelope therefore covers all offset queries needed for a representable
microsecond result. Queries outside it require an explicit unsupported-domain
error. This is not a promise about all i64-millisecond inputs.

## Mechanism and verification

[ExportJavaTimezoneProfiles.java](sources/ExportJavaTimezoneProfiles.java)
exports the pinned runtime's normalized historical tables and raw-prefix
offsets. Future cycles come from the actual `SimpleTimeZone.getStart/getEnd`
evaluators, including adjacent years for UTC year-boundary crossings. All
exported rules have `startYear=0`. Each evaluator boundary repeats exactly
146,097 days later when its year is advanced by 400. This establishes the
finite recurring transition set; daily sampling is not used as a completeness
argument. The offline exporter uses narrowly named JDK private fields/methods
and fails if the expected layout or invariants differ.

The public-oracle gate passed:

- **830,644 offset comparisons**, including every named historical transition
  at -1/0/+1 millisecond and interval midpoints, future cycle boundaries and
  midpoints, wide-year blocks, pre-1900 dates, Gregorian-cutover dates, year
  9999/10000, microsecond endpoints, and the expanded query-domain endpoints.
- **35,336 ORC conversion comparisons** against Java ORC 2.3.0's actual
  `SerializationUtils.convertBetweenTimezones`, in both directions with UTC.
- **315,351 resolver cases**, covering every valid compact and colon custom-GMT
  spelling under the documented grammar, invalid compact widths/values,
  malformed field boundaries, exact names, case variants and unknown names.
- Every exported Java `hasSameRules` group has identical normalized profile
  content in this baseline; no hidden distinct-offset group was observed.

[The independent verifier](sources/verify_java_timezone_profiles.py) uses only
integer arithmetic, binary search and a separately written name parser. It
does not use Java, Python `datetime`/`zoneinfo`, Jiff or Chrono. It reproduced all
three public-oracle digests and checked every profile/cycle content identity.
[The result](evidence/independent-verification.json) records zero failures.

Two complete generator runs produced identical bytes for all four exported
JSON artifacts. [repeatability.json](evidence/repeatability.json) records both
hashes; the duplicate artifact copies are intentionally not retained here.
The generator/verification command and all primary input/output hashes are in
[generation-manifest.json](evidence/generation-manifest.json) and
[ARCHIVE-MANIFEST.json](ARCHIVE-MANIFEST.json).

## Runtime data contract

The file is canonical UTF-8 JSON v1: sorted object keys, compact separators,
one trailing newline. Profile and cycle IDs are SHA-256 of their canonical
object bytes **without** newline. Worker identity is SHA-256 of the entire
artifact **including** its newline.

| Object | Fields |
| --- | --- |
| `configuration` | Explicit JVM/rules/locale/epoch settings and query domain |
| `zones[name]` | `{profile, resolved_id, available}`; exact spelling lookup |
| `profiles[id]` | `{raw_prefix_offset_millis:i32, orc_epoch_seconds:i64, transitions:[[utc_millis:i64, offset_millis:i32]], future}` |
| `future` | `{kind:"fixed", offset_millis:i32}` or `{kind:"cycle", id}` |
| `cycles[id]` | `{anchor_millis:i64, period_millis:12622780800000, rows:[[position_millis:i64, offset_millis:i32]]}` |
| `java_aliases` | Provenance mapping; runtime names already resolve directly to profiles |

With no historical rows, use the raw prefix throughout the supported domain;
the exporter requires a matching fixed future and prohibits a cycle. Before
the first historical row, also use the raw prefix. Through the exact last row,
use the greatest transition instant at or before the query. Strictly afterward,
use the explicit future policy. Cycle lookup uses checked wide arithmetic:
`(query - anchor).rem_euclid(period)`, then the greatest cycle row position at or
before that result. Every cycle starts at position zero. Never reconstruct a
local datetime or use host timezone data.

Return the stored ORC 2015 epoch for named zones. It cannot be derived from the
raw-prefix offset: Windhoek's raw prefix is +01:00, while its stored 2015 epoch
uses +02:00. The artifact deliberately retains Java's other normalization
choices, including pre-1900 raw offsets and the future Windhoek/Morocco behavior
that differs from an unmodified IANA TZif reader.

## Exact name behavior

Resolve an exact exported name first, then try the custom GMT grammar, otherwise
return the exported GMT profile as Java's explicit unknown-name fallback.
Do not trim, case-fold, reinterpret bare offsets or run Sail's SQL timezone
normalizer. Alias resolution need not traverse `java_aliases`; preserve the
exported resolved ID, such as Java's `PST` spelling.

Custom GMT uses ASCII `GMT`, a sign, and one of these forms:

- One/two compact digits mean hours; three/four digits mean HHMM.
- One colon requires hour width 1..2 and minute width exactly 2.
- Two colons require hour width 1..2, minute width 1..2 and second width exactly 2.
- Hours must be <=23; minutes and seconds <=59. Other characters or trailing
  input fail to GMT. Normalize to `GMT[sign]HH:MM`, adding `:SS` only for nonzero
  seconds; signed zero remains `GMT+00:00` or `GMT-00:00`.

Thus `GMT+1:2:03` is valid while `GMT+1:2` is not. Seconds support extends the
earlier retained name probe; that earlier evidence was not modified.
For custom fixed offsets only, the epoch is `utc_epoch_seconds - offset_seconds`.
Null/empty writer metadata is handled by native reader inheritance before this
resolver. Direct Java empty-string lookup itself returns GMT; null string input
throws. [Representative outcomes](evidence/java-timezone-resolver-oracle.json)
include the grammar boundaries.

## Reproduce and archive safely

Run the original generator with the recorded Java/JAR inputs (the paths below
are installation-specific, while the hashes are recorded):

```sh
python3 sources/run_java_timezone_export.py \
  --java-home /path/to/jdk-20.0.2 \
  --classpath '/path/to/pyspark/jars/*' \
  --format-locale en-US --oldmapping false \
  --output /tmp/orc-timezone-profile-regeneration --repeat
```

The runner caps the exporter heap at 256 MiB. It requires Java only for offline
generation/oracle checking; profile consumers require no JVM or new timezone
engine. `sources/verify_java_timezone_profiles.py` can also independently verify
co-located exported JSON files without Java. The root gate's external archive
verifier copies the required inputs to a temporary directory and compares the
new result to the retained result, without writing inside this archive.

The code here is original exporter/verifier glue. No JDK implementation source,
JDK distribution, or dependency JAR is included. The installed Oracle source
extracts used for local inspection are deliberately excluded. Runtime class,
tzdb and relevant JAR hashes are retained in the manifests. Public reference
implementations at the matching OpenJDK tag document the inspected mechanisms:
[SimpleTimeZone](https://github.com/openjdk/jdk20u/blob/jdk-20.0.2%2B9/src/java.base/share/classes/java/util/SimpleTimeZone.java),
[TimeZone](https://github.com/openjdk/jdk20u/blob/jdk-20.0.2%2B9/src/java.base/share/classes/java/util/TimeZone.java),
[ZoneInfo](https://github.com/openjdk/jdk20u/blob/jdk-20.0.2%2B9/src/java.base/share/classes/sun/util/calendar/ZoneInfo.java),
and [ZoneInfoFile](https://github.com/openjdk/jdk20u/blob/jdk-20.0.2%2B9/src/java.base/share/classes/sun/util/calendar/ZoneInfoFile.java).

## Proposed runtime snapshots

[RUNTIME-PROVIDER-HANDOFF.md](proposed-runtime/RUNTIME-PROVIDER-HANDOFF.md) and
[source-audit.json](proposed-runtime/source-audit.json) are preserved read-only
design/review snapshots, not an implemented Sail API or a Rust gate result.
Their statement that independent/repeatability checks were pending describes
their preparation time; the completed exporter checks above supersede that
status. Their proposed runtime and bridge work remains a separate implementation
unit. This packet does not qualify Sail file/stripe pruning, worker integration,
calendar rebasing, or runtime memory/performance.
