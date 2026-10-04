#!/bin/sh
set -C
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
proof_python=/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python
proof_output=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/certificate-parent-witness
run_proof_gate() {
    "$proof_python" -B "$proof_output/run_sql_gate.py" --repo "$1" --output "$proof_output/$2" \
      --head "$3" --tree cd73d093230153857de196abc17ea8e98464149b --mode "$4" --unit --variant candidate \
      --sql-tests "$1/examples/extensions/benchmarks/test_traversal_certificate.py" \
      "$1/examples/extensions/benchmarks/test_traversal_parent_witness.py" \
      "$proof_output/test_baseline.py" "$proof_output/test_preconditions.py" "$proof_output/test_work.py" --expected-sql 71
}
run_proof_gate /private/tmp/sail-certificate-parent-witness-candidate02 candidate-gate02 fc094a0c25a49edeac2f9f0195aa973421a21a43 candidate &&
run_proof_gate /private/tmp/sail-certificate-parent-witness-gate exact-gate02 cab6bacc0ad0d1fc8b3070e9e4267e99751909fe exact
