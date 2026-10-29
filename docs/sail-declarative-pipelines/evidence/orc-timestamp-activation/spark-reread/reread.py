"""Reread unchanged retained ORC fixtures with explicitly pinned JVM defaults."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import traceback
from typing import Any

from pyspark import SparkContext
from pyspark.sql import SparkSession


ROOT = Path(__file__).resolve().parent
REFERENCE = Path('/tmp/sail-sdp-orc-bridge-reference')
NAMES = ['timestamps_utc', 'timestamps_los_angeles', 'nested_timestamp_nulls', 'foreign_submicro']
PINNED = {
    'timestamps_utc': '3acd5455d4585b48358c15c523d408ded4a6a17c3eb5007d34c421d8d68cbaae',
    'timestamps_los_angeles': 'a5b81d62725050485515244d5c9aafb1c82d2520b234a05b8fcfe44ef0a41fcb',
    'nested_timestamp_nulls': '67823c5ec6d968c1ce714c0d42adb278d80615e873dd0c7f433f5abe67c33888',
    'foreign_submicro': 'ea1b4632e1ccab05a903443d83a51b06b428327dcef9bfd73dd993598495b468',
}


def save(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def micros(value: str | None) -> int | None:
    if value is None:
        return None
    date = datetime.fromisoformat(value)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    delta = date - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def nested_expected(case: dict[str, Any]) -> list[dict[str, Any]]:
    columns = case['read_arrow']['value']['columns']

    def structure(value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else {key: micros(item) for key, item in value.items()}

    result = []
    for index, row_id in enumerate(columns['id']['values']):
        row = {'id': row_id, 'st': structure(columns['st']['values'][index])}
        for key in ['nts', 'lts']:
            value = columns[key]['values'][index]
            row[key] = None if value is None else [micros(item) for item in value]
        value = columns['ntm']['values'][index]
        row['ntm'] = None if value is None else {key: micros(item) for key, item in value}
        value = columns['sts']['values'][index]
        row['sts'] = None if value is None else [structure(item) for item in value]
        result.append(row)
    return result


def projection(name: str) -> list[str]:
    epoch = "TIMESTAMP_NTZ'1970-01-01 00:00:00'"
    if name == 'foreign_submicro':
        return ['id', 'unix_micros(ts) AS ts_micros']
    if name != 'nested_timestamp_nulls':
        return ['id', f'timestampdiff(MICROSECOND, {epoch}, ntz) AS ntz_micros',
                'unix_micros(ltz) AS ltz_micros']
    def st(value: str) -> str:
        return (f"IF({value} IS NULL, NULL, named_struct('ntz', "
                f"timestampdiff(MICROSECOND, {epoch}, {value}.ntz), "
                f"'ltz', unix_micros({value}.ltz)))")
    return ['id', st('st') + ' AS st',
            f'transform(nts, x -> timestampdiff(MICROSECOND, {epoch}, x)) AS nts',
            'transform(lts, x -> unix_micros(x)) AS lts',
            f'transform_values(ntm, (k, v) -> timestampdiff(MICROSECOND, {epoch}, v)) AS ntm',
            f'transform(sts, x -> {st("x")}) AS sts']


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--reader', required=True, choices=['America/Los_Angeles', 'UTC'])
    args = parser.parse_args()
    label = 'la' if args.reader == 'America/Los_Angeles' else 'utc'
    output = ROOT / f'{label}.json'
    names = NAMES if label == 'la' else ['foreign_submicro']
    report: dict[str, Any] = {
        'scope': 'Fresh explicit-reader reread; original fixture bytes and expected.json are unchanged',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'python_pid': os.getpid(), 'requested_reader_timezone': args.reader,
        'java_tool_options': os.environ.get('JAVA_TOOL_OPTIONS'),
        'spark_source_pin': '617618396087429b5627a86ce933bb0f5d6645cb',
        'reference_expected_sha256': sha(REFERENCE / 'expected.json'),
        'script_sha256': sha(Path(__file__)), 'status': 'starting', 'cases': [],
    }
    save(output, report)
    reference = {c['name']: c for c in json.loads((REFERENCE / 'expected.json').read_text())['cases']}
    paths = {name: next((REFERENCE / 'data' / name).glob('*.orc')) for name in names}
    for name, path in paths.items():
        assert sha(path) == PINNED[name], (name, 'fixture changed before read')
    # The fresh process must own its local gateway, never attach to another one.
    for key in ['SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED', 'SPARK_LOCAL_REMOTE',
                'PYSPARK_GATEWAY_PORT', 'PYSPARK_GATEWAY_SECRET', 'SPARK_TESTING']:
        os.environ.pop(key, None)
    os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
    os.environ['SPARK_LOCAL_DIRS'] = str(ROOT / f'spark-local-{label}')
    session = None
    gateway = None
    process = None
    try:
        session = (SparkSession.builder.remote('local[1]')
                   .config('spark.ui.enabled', 'false')
                   .config('spark.driver.memory', '512m')
                   .config('spark.sql.warehouse.dir', (ROOT / f'warehouse-{label}').as_uri())
                   .config('spark.sql.session.timeZone', 'UTC').getOrCreate())
        gateway = SparkContext._gateway
        process = gateway.proc
        jvm = SparkContext._jvm
        assert process is not None, 'probe did not own the local JVM'
        java = jvm.java
        runtime = java.lang.management.ManagementFactory.getRuntimeMXBean()
        report['java'] = {
            'gateway_pid': process.pid, 'actual_pid': int(runtime.getPid()),
            'default_timezone_id': java.util.TimeZone.getDefault().getID(),
            'user_timezone_property': java.lang.System.getProperty('user.timezone'),
            'format_locale': java.util.Locale.getDefault(java.util.Locale.Category.FORMAT).toLanguageTag(),
            'runtime_version': java.lang.System.getProperty('java.runtime.version'),
            'vendor': java.lang.System.getProperty('java.vendor'),
            'oldmapping_property': java.lang.System.getProperty('sun.timezone.ids.oldmapping'),
            'tzdb_versions': list(java.time.zone.ZoneRulesProvider.getVersions('UTC').keySet()),
        }
        report['spark_version'] = session.version
        report['status'] = 'reading'
        save(output, report)
        print(json.dumps({'phase': 'started', 'reader': args.reader, 'java': report['java']}), flush=True)
        assert session.version == '4.2.1'
        assert report['java']['default_timezone_id'] == args.reader
        assert report['java']['user_timezone_property'] == args.reader
        assert report['java']['format_locale'] == 'en-US'
        assert report['java']['oldmapping_property'] == 'false'
        assert report['java']['runtime_version'] == '20.0.2+9-78'
        assert report['java']['tzdb_versions'] == ['2023c']
        for name, path in paths.items():
            before = None
            for display in ['UTC', 'America/Los_Angeles']:
                session.conf.set('spark.sql.session.timeZone', display)
                frame = session.read.orc(str(path))
                rows = [row.asDict(recursive=True) for row in frame.selectExpr(*projection(name)).orderBy('id').collect()]
                case = {'name': name, 'fixture': str(path), 'fixture_sha256': sha(path),
                        'reader_timezone': args.reader, 'session_timezone': display,
                        'numeric_projection': projection(name), 'rows': rows,
                        'spark_schema': frame.schema.jsonValue(), 'arrow_schema': str(frame.toArrow().schema)}
                report['cases'].append(case)
                save(output, report)
                if label == 'utc':
                    expected = [{'id': i, 'ts_micros': value} for i, value in enumerate([1577934245123456, -1876544, 0, None])]
                    case['expected_basis'] = 'Recorded physical nanoseconds, UTC reader, Euclidean microsecond truncation'
                elif name == 'nested_timestamp_nulls':
                    expected = nested_expected(reference[name])
                    case['expected_basis'] = 'Original read_arrow nested values, converted with exact integer datetime arithmetic'
                else:
                    numeric = reference[name]['read_numeric']
                    expected = numeric if isinstance(numeric, list) else numeric['value']
                    case['expected_basis'] = 'Original read_numeric values'
                case['expected_rows'] = expected
                assert rows == expected, (name, display, rows, expected)
                assert before is None or rows == before, (name, 'display timezone changed numeric values')
                before = rows
                assert java.util.TimeZone.getDefault().getID() == args.reader
                case['matches_expected'] = True
                save(output, report)
                print(json.dumps({'phase': 'passed', 'name': name, 'display': display}), flush=True)
        for name, path in paths.items():
            assert sha(path) == PINNED[name], (name, 'fixture changed after read')
        assert sha(REFERENCE / 'expected.json') == report['reference_expected_sha256']
        report['status'] = 'passed'
    except BaseException:
        report['status'] = 'failed'
        report['failure'] = traceback.format_exc()
        raise
    finally:
        if session is not None:
            session.stop()
        if gateway is not None:
            gateway.shutdown()
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                # This Popen handle is the JVM started by this script only.
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            report['owned_gateway_exit_code'] = process.returncode
        save(output, report)
        print(json.dumps({'phase': 'finished', 'status': report['status'], 'output': str(output)}), flush=True)


if __name__ == '__main__':
    main()
