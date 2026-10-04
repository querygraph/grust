"""Local orchestration checks; these do not launch Sail or containers."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pecan_gate3_cell as gate
import run_pecan_gate3 as runner


class ExperimentTests(unittest.TestCase):
    def test_balanced_order_and_full_gates(self):
        cells = runner.schedule()
        self.assertEqual(len({c["id"] for c in cells}), 14)
        gates = cells[:4]
        self.assertEqual({(c["label"], c["mode"]) for c in gates},
                         {(l, m) for l in ("base", "candidate") for m in ("local", "process-cluster")})
        self.assertTrue(all(c["kind"] == "integration" for c in gates))
        self.assertEqual([c["label"] for c in cells[4:6]], ["base", "candidate"])
        self.assertEqual([c["label"] for c in cells[6:]],
                         ["base", "candidate", "candidate", "base", "candidate", "base", "base", "candidate"])

    def test_pytest_environment_excludes_external_shim_and_selection(self):
        contaminated = {"PYTHONPATH": "/tmp/probe_receipts", "PYTEST_PLUGINS": "probe_receipts",
                        "PYTEST_ADDOPTS": "-k false -p probe_receipts", "PYTHONHOME": "/tmp/bad"}
        with patch.dict(os.environ, contaminated):
            env = gate.clean_test_environment(Path("/clean/repo"), "sc://localhost:123")
        self.assertEqual(env["PYTHONPATH"], "/clean/repo/examples/extensions/graph-algorithms/src")
        self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(env["SAIL_GRAPH_TEST_REMOTE"], "sc://localhost:123")
        for key in ("PYTEST_PLUGINS", "PYTEST_ADDOPTS", "PYTHONHOME"):
            self.assertNotIn(key, env)

    def test_junit_failures_and_skips_remain_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "junit.xml"
            path.write_text('<testsuites><testsuite><testcase classname="C" name="ok"/>'
                '<testcase classname="C" name="broken"><failure/></testcase>'
                '<testcase classname="C" name="unavailable"><skipped/></testcase>'
                '<testcase classname="C" name="exception"><error/></testcase></testsuite></testsuites>')
            self.assertEqual(gate.junit_summary(path), dict(tests=4, failures=1, errors=1,
                skipped=1, failed_cases=["C::broken", "C::exception"]))

    def test_only_controller_source_changes_between_cells(self):
        cfg = runner.config()
        base, candidate = [runner.source_config(cfg, label) for label in ("base", "candidate")]
        changed = {k for k in base if base[k] != candidate[k]}
        self.assertEqual(changed, {"container_repo", "harness_source_sha"})
        self.assertEqual(base["harness_source_sha"], gate.BASE)
        self.assertEqual(candidate["harness_source_sha"], gate.CANDIDATE)


if __name__ == "__main__":
    unittest.main()
