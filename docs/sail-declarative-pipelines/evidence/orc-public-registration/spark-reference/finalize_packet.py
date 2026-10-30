"""Freeze this completed reference packet; never starts Spark or rewrites raw results."""
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

root = Path(__file__).resolve().parent
results = json.loads((root / 'results.json').read_text())
assert results['status'] == 'completed' and results['summary'] == {'failed': 0, 'passed': 10}
assert results['owned_gateway_exit_code'] == 0
check = subprocess.run(['ps', '-p', '56186,56197', '-o', 'pid=,ppid=,lstart=,command='], text=True, capture_output=True)
assert check.returncode == 1 and not check.stdout.strip()
(root / 'terminal-process-check.json').write_text(json.dumps({
    'observed_at_utc': datetime.now(timezone.utc).isoformat(),
    'command': check.args, 'exit_code': check.returncode, 'stdout': check.stdout,
    'stderr': check.stderr, 'owned_python_pid': 56186, 'owned_jvm_pid': 56197,
    'exec_session_id': 92378, 'exec_terminal_exit_code': 0,
}, indent=2) + '\n')
(root / 'README.md').write_text('''# Spark 4.2.1 public ORC read reference

The exact frozen public test source passed all ten cases on 2026-10-30 UTC. This is a Spark Connect reference run, not Sail runtime qualification and not a pytest-runner result. `run.py` directly invokes the unchanged five test functions with the original `orc_spark` fixture generator; the partition test expands to six cases. Each case receives a fresh temporary input directory where required. `source/test_orc.py` has SHA256 `c8e73063a7aeb9085b7e801ac67561747cb67d545f60974d092f9f982e879f2c` and matches the frozen repository source exactly.

The cases exercise DataFrame/SQL path reads, an external catalog table, an eleven-file merge through operation and session settings, supplied partition aliases/omissions/empty schemas under both case policies, and retained Spark TIME fields including requested-schema precision reinterpretation. All assertions, expected schemas, row values, and raw nanosecond expectations are unchanged. The retained TIME fixture is checked by its original SHA256. Generated PyArrow ORC files are retained under `inputs/`.

`results.json` retains exact schemas, collected rows/counts, SQL text, Arrow schemas and raw TIME integer storage observed from the original methods. The harness wraps methods only to record returned values; it adds no query actions and returns the original objects. There were no failed cases or retries. `probe.log` retains initial startup warnings, including Connect attempts to reapply immutable startup settings. The actual SparkContext master and driver memory were read from the JVM and checked as `local[1]` and `512m`.

The runtime is installed PySpark/Spark 4.2.1, Java 20.0.2+9-78, UTC, en-US, with `sun.timezone.ids.oldmapping=false`. Runtime JAR hashes are retained; the pinned source reference is `617618396087429b5627a86ce933bb0f5d6645cb`. This does not attest that the installed JARs were built from that local Git checkout. The session class is `pyspark.sql.connect.session.SparkSession`.

Configuration snapshots named `config` are taken after the fixture is entered and before the test body. Tests themselves then set the per-case case policy and session merge override as shown in the exact retained source and parameters; those mutations were not individually intercepted. `config_after_restore` confirms fixture restoration. TIME is disabled in the initial/default session and explicitly enabled by the fixture. The fresh session has no `orc.force.positional.evolution` override; the harness checks that before testing. Recorded vectorization settings do not independently prove the selected physical path for every successful query.

One owned JVM was started (PID 56197, Python parent 56186). Session and gateway shutdown completed, the JVM exited 0, and both owned PIDs were independently absent afterward. `terminal-process-check.json` records the second process check and exec session 92378 exit 0. No external JVM or service was stopped. No Cargo build, Sail process, or repository edit was performed by this run.

Run invocation was `PYTHONDONTWRITEBYTECODE=1 JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-20.jdk/Contents/Home JAVA_TOOL_OPTIONS='-Duser.timezone=UTC -Dsun.timezone.ids.oldmapping=false -Duser.language=en -Duser.country=US' /Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /tmp/sail-sdp-orc-public-reference/run.py > /tmp/sail-sdp-orc-public-reference/probe.log 2>&1`, with the packet directory as working directory. The script bounds execution to 600 seconds and cleans up only its owned gateway.

`MANIFEST.json` inventories every retained file except itself. Empty Spark scratch/warehouse directories contain no evidence and are not inventoried. No nonempty log or failure artifact was excluded. `validate_evidence.py` is an offline read-only validator; it does not start Spark. The run script intentionally refuses to reuse its existing output directories, so do not rerun it in this frozen packet.
''')
original = Path('/Users/alexy/src/sail-pipelines-proposal/python/pysail/tests/spark/datasource')
provenance = {
    'kind': 'Spark Connect reference of unchanged public ORC tests',
    'sail_runtime_qualification': False, 'pytest_runner': False,
    'spark_source_pin': results['spark_source_pin'],
    'sail_head_at_freeze': '26b9461b93092ab99f1d5718fa82c73327970a27',
    'test_sources_were_uncommitted_candidate': True,
    'source_mapping': [
        {'original': str(original / 'test_orc.py'), 'retained': 'source/test_orc.py'},
        {'original': str(original / 'orc_data/time_precisions.orc'), 'retained': 'source/orc_data/time_precisions.orc'},
        {'original': str(original / 'orc_data/spark-reference.json'), 'retained': 'source/orc_data/spark-reference.json'},
        {'original': results['sql_helper']['path'], 'retained': 'source/sql_helpers.py'},
    ],
    'outcomes': results['summary'], 'attempts': 1, 'exclusions': ['empty directories only'],
}
for item in provenance['source_mapping']:
    retained = root / item['retained']
    assert retained.read_bytes() == Path(item['original']).read_bytes()
    item['sha256'] = hashlib.sha256(retained.read_bytes()).hexdigest()
(root / 'provenance.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
files = [{'path': str(p.relative_to(root)), 'size': p.stat().st_size,
          'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json']
(root / 'MANIFEST.json').write_text(json.dumps({'files': files}, indent=2, sort_keys=True) + '\n')
print(json.dumps({'files': len(files), 'manifest_sha256': hashlib.sha256((root / 'MANIFEST.json').read_bytes()).hexdigest()}))
