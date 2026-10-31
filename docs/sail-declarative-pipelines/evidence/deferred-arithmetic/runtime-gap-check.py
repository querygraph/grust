"""Fail until all retained NULL/window/volatile/pmod runtime observations match Spark."""
from pathlib import Path
import json,sys
HERE=Path(__file__).resolve().parent
r=json.loads((HERE/'comparison.json').read_text())['after_runtime12']
failed=[c['name'] for c in r['cases'] if not c['behavior_matched'] or c['schema_matched'] is False or not c['metadata_matched']]
print(json.dumps({'scope':'required runtime semantics, includes schema/error metadata; failures remain required work','passed':len(r['cases'])-len(failed),'failed':len(failed),'failures':failed},indent=2))
raise SystemExit(bool(failed))
