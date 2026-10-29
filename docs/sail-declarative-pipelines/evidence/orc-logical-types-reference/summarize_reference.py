from pathlib import Path
import hashlib, json, subprocess, pyspark

root = Path('/tmp/sail-sdp-orc-bridge-reference')
cp = str(Path(pyspark.__file__).parent / 'jars/*')
p = subprocess.run(['java', '--class-path', cp, str(root / 'InspectOrc.java'), str(root / 'data')], capture_output=True, text=True, check=True)
(root / 'physical-type-attributes.json').write_text(p.stdout)
report = json.loads((root / 'expected.json').read_text())
cases = {c['name']: c for c in report['cases']}
assert report['spark_version'] == '4.2.1'
for name in ('time_precisions', 'time_cast_precisions', 'intervals', 'nested_time_intervals', 'daytime_time_nested'):
    case = cases[name]
    assert case['source_strings']['value'] == case['read_strings']['value'], name
# Map stringification order can differ across write/read without changing map values.
case = cases['nested_timestamp_nulls']
assert case['source_collect']['value'] == case['read_collect']['value']
assert cases['time_cast_precisions']['physical_arrow']['value'][0]['integer_storage']['t3'] == [0, 45296123000000, 86399999000000, None]
assert cases['timestamps_utc']['source_numeric']['value'][2]['ltz_micros'] == -1
assert cases['timestamps_utc']['read_numeric']['value'][2]['ltz_micros'] == 999999
assert cases['timestamps_utc']['read_numeric']['value'][2]['ntz_micros'] == -1
assert cases['timestamps_los_angeles']['source_numeric'] == cases['timestamps_los_angeles']['read_numeric']
assert all(cases['intervals'][stage]['outcome'] == 'failed' for stage in ('source_collect', 'source_arrow', 'read_collect', 'read_arrow'))
assert cases['foreign_char_varchar_default_timestamp_ntz']['read_schema']['fields'][-1]['type'] == 'timestamp'
assert cases['foreign_char_varchar_default_timestamp_ntz']['read_collect']['value'][0]['c'] == 'a    '
assert cases['foreign_submicro']['physical_arrow_ts_nanos'] == [1577934245123456789, -1876543211, 1, None]
manifest = []
for file in sorted((root / 'data').rglob('*.orc')):
    manifest.append({'path': str(file), 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
validation = {
    'outcome': 'passed', 'fixture_count': len(manifest), 'case_count': len(cases),
    'checks': ['Spark4.2.1', 'Five scalar/nested string projection roundtrips', 'Nested timestamp values with map-order-insensitive equality', 'TIME3 nanosecond storage', 'Retained Spark negative LTZ defect', 'Los Angeles LTZ/NTZ epoch roundtrip', 'Retained unsupported PySpark year-month Arrow conversions', 'Foreign timestamp stays LTZ under NTZ default', 'Foreign CHAR padding', 'Foreign submicrosecond physical nanos'],
    'fixtures': manifest,
}
(root / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n')
refs = [
    ('spark', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala', 132, 182),
    ('spark', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala', 331, 388),
    ('spark', 'sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcSerializer.scala', 98, 116),
    ('spark', 'sql/api/src/main/scala/org/apache/spark/sql/util/ArrowUtils.scala', 64, 74),
    ('spark', 'sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst/expressions/Cast.scala', 828, 838),
    ('spark', 'sql/catalyst/src/main/scala/org/apache/spark/sql/internal/SQLConf.scala', 7435, 7443),
    ('spark', 'sql/core/src/main/java/org/apache/spark/sql/execution/datasources/orc/OrcColumnarBatchReader.java', 130, 143),
    ('spark', 'sql/core/src/main/java/org/apache/spark/sql/execution/datasources/orc/OrcAtomicColumnVector.java', 102, 111),
    ('orc', 'src/array_decoder/timestamp.rs', 127, 190),
    ('orc', 'src/array_decoder/timestamp.rs', 234, 289),
    ('orc', 'src/encoding/timestamp.rs', 225, 276),
    ('orc', 'src/schema.rs', 540, 578),
    ('orc', 'src/array_decoder/list.rs', 62, 87),
    ('orc', 'src/array_decoder/struct_decoder.rs', 58, 78),
    ('orc', 'src/array_decoder/map.rs', 73, 104),
]
locations = {
    'spark': ('/Users/alexy/src/spark-sdp-4.2.1', report['spark_source_pin']),
    'orc': ('/Users/alexy/src/orc-rust-sdp', report['orc_rust_source_pin']),
}
sources = []
for repo, path, start, end in refs:
    checkout, pin = locations[repo]
    content = subprocess.check_output(['git', '-C', checkout, 'show', pin + ':' + path], text=True)
    sources.append({'repository': checkout, 'pin': pin, 'path': path, 'start_line': start, 'end_line': end, 'excerpt': '\n'.join(content.splitlines()[start-1:end])})
evidence = {
    'sources': sources,
    'observed_pitfalls': [
        'TIME(0..6) is physical ORC LONG nanoseconds, Arrow Time64(Nanosecond); precision does not rescale bits. Spark requires spark.sql.timeType.enabled=true.',
        'String-to-TIME(0/3) can retain six fractional digits; Time-to-Time casts truncate. Preserve declared precision metadata separately from raw nanoseconds.',
        'Year-month interval is physical INT total months, JVM Arrow Interval(YearMonth); day-time is physical LONG microseconds, Arrow Duration(Microsecond). PySpark cannot collect/convert year-month interval; string and numeric projections succeed.',
        'NTZ is physical LONG microseconds. Physical TIMESTAMP yields naive writer wallclock from native default decoder. Both UTC and LA SQL fixtures were written by JVM America/Los_Angeles, confirmed in stripe footers.',
        'Spark reader uses plain ORC ReaderOptions with useUTCTimestamp=false, so ORC Java reads wallclock using reader JVM TimeZone.getDefault; session timezone does not configure the ORC reader. Installed ORC exact bytecode is retained in OrcFile_ReaderOptions-javap.txt and TreeReaderFactory_TimestampTreeReader-javap.txt.',
        'UTC SQL Spark-written LTZ -1us reads back +999999us in Spark itself; NTZ -1us stays correct. Source and file-read expected values are separate.',
        'Foreign TIMESTAMP without attribute stays Spark LTZ under TIMESTAMP_NTZ config. Foreign CHAR/VARCHAR become String, retain __CHAR_VARCHAR_TYPE_STRING metadata; CHAR padding is preserved.',
        'Foreign UTC-writer TIMESTAMP is interpreted by Spark reader JVM LA: 2020-01-02 03:04:05.123456789 reads 11:04:05.123456 UTC. Writer-based instant semantics do not automatically match Spark across reader JVM timezones.',
        'Native microsecond timestamp decode rejects submicrosecond nanos; Spark truncates. Default nanosecond decode has narrower date range. Native microsecond mode is source-reviewed, not executed by existing probe.',
        'Rebuild nested Struct/List/Map arrays recursively preserving offsets/null buffers and field metadata. Parent struct null, all-null fields, null container, empty container, null element are distinct. Native map child names keys/values differ from Spark Arrow key/value. Map stringification order is not semantic equality.',
        'Changing Arrow schema alone cannot decode physical LONG as Timestamp/Time/Duration; native hints must match decoder-supported physical types before a separate array bridge.',
        'Post-hoc naive wallclock conversion loses DST-fold information; ORC Java preserves original instant when writer and reader timezone rules match, otherwise applies writer-to-reader timezone conversion before exposing instant.',
    ],
    'limitations': [
        'Focused local fixtures, not full Spark ORC conformance or benchmarks.',
        'Retained default-TIME rejection, PySpark interval conversion failures, initial SQL typo log and map-key JSON serializer failure log.',
        'Existing bounded native executable used for default nanosecond reads only; no builds or repository modifications during reference collection.',
    ],
}
(root / 'source-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'validation': 'passed', 'fixtures': len(manifest), 'cases': len(cases)}))
