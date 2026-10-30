# Documentation parser correction

The only invalid single-document JSON path within this new packet is `docs/sail-declarative-pipelines/evidence/catalog-empty-schema-read/spark-catalog-reference/inputs/json/part.json`. It is a valid Spark JSON Lines fixture: two 9-byte lines, records `{"id":3}` and `{"id":1}`. Preserve its bytes and manifests.

Use an explicit typed entry in the generic verifier, keyed by the exact repository-relative path. Require nonempty lines and decode each with `json.loads`; assert the two expected records. Continue parsing every other `.json` file as a single document. Do not catch `Extra data` globally, skip fixture validation, or broaden all files under `inputs/json` automatically.

```python
json_lines_fixtures = {
    "docs/sail-declarative-pipelines/evidence/catalog-empty-schema-read/spark-catalog-reference/inputs/json/part.json": [{"id": 3}, {"id": 1}],
}
relative = path.relative_to(repo_root).as_posix()
if relative in json_lines_fixtures:
    lines = path.read_text().splitlines()
    assert lines and all(line.strip() for line in lines), relative
    assert [json.loads(line) for line in lines] == json_lines_fixtures[relative], relative
else:
    json.loads(path.read_text())
```

Read-only specific-verifier execution on detached `f0d5338d9541b1844f00c8b3b9b0acec35e76ec4` passes under `/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python` (Python 3.12). The host default Python 3.15 fails at XML parser import with a libexpat missing-symbol error after all earlier checks pass. Use the existing qualified 3.12 interpreter; do not weaken XML assertions or modify host libraries. Both diagnostic reruns, exact commands, and hashes are retained in `observation.json` and their logs. The original generic-gate failure was reported in the root tool result without a raw log; it is not retroactively represented as a captured raw run.

No Grust or Sail file was edited, no checkout was changed, and no commit was made.
