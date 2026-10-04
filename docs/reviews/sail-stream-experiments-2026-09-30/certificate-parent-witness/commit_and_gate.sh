#!/bin/sh
set -C
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
proof_python=/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python
proof_output=/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30/certificate-parent-witness
proof_gate=/private/tmp/sail-certificate-parent-witness-gate
proof_repo=/private/tmp/sail-certificate-parent-witness
run_proof_gate() {
    "$proof_python" -B "$proof_output/run_sql_gate.py" --repo "$proof_gate" --output "$proof_output/$1" \
      --head "$2" --tree cd73d093230153857de196abc17ea8e98464149b --mode "$3" --unit --variant candidate \
      --sql-tests "$proof_gate/examples/extensions/benchmarks/test_traversal_certificate.py" \
      "$proof_gate/examples/extensions/benchmarks/test_traversal_parent_witness.py" \
      "$proof_output/test_baseline.py" "$proof_output/test_preconditions.py" "$proof_output/test_work.py" --expected-sql 71
}
run_proof_gate candidate-gate fc094a0c25a49edeac2f9f0195aa973421a21a43 candidate &&
"$proof_python" -B "$proof_output/guard_candidate.py" &&
git -C "$proof_repo" commit -F "$proof_output/commit-message.txt" &&
proof_commit=$(git -C "$proof_repo" rev-parse HEAD) &&
git -C "$proof_gate" checkout --detach "$proof_commit" &&
run_proof_gate exact-gate "$proof_commit" exact
