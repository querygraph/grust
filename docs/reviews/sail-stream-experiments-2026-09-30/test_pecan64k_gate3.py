"""Local checks of actual matrix commands and bounded fixture generation; no Docker."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.environ["PECAN_MATRIX_DIR"])
import run_matrix as matrix
import traversal_fixture
import run_pecan64k_gate3 as runner
import run_pecan_gate3 as shared


class LargerControllerTests(unittest.TestCase):
    def test_warmups_excluded_and_measured_order_balanced(self):
        cells = runner.schedule()
        self.assertEqual(len({c["id"] for c in cells}), 6)
        self.assertEqual([c["label"] for c in cells[:2]], ["base", "candidate"])
        self.assertTrue(all(c["kind"] == "warmup" for c in cells[:2]))
        self.assertEqual([c["label"] for c in cells[2:]], ["base", "candidate", "candidate", "base"])
        self.assertTrue(all(c["kind"] == "measured" for c in cells[2:]))

    def test_actual_commands_hold_sources_envelope_and_new_fixture(self):
        prior = shared.config()
        originals = copy.deepcopy(prior)
        configs = [runner.cell_config(prior, label, "/targets/fresh", "/host/fresh")
                   for label in ("base", "candidate")]
        self.assertEqual({k for k in configs[0] if configs[0][k] != configs[1][k]},
                         {"container_repo", "harness_source_sha"})
        self.assertEqual(configs[1]["container_repo"], prior["container_root"] + "/source-edc2c7c8")
        for cell in runner.schedule():
            cmd = runner.command(matrix, prior, cell, "/targets/fresh", "/host/fresh")
            for name, value in dict(engine="pecan", algorithm="sssp", variant="frontier",
                mode="process-cluster", expected_vertices="65536", max_iterations="100",
                partitions="4", threads="4", worker_task_slots="16", sail_pool_bytes=str(3*1024**3),
                timeout="600", source="0", seed="42", http2_keepalive_timeout="120").items():
                self.assertEqual(cmd[cmd.index("--" + name.replace("_", "-")) + 1], value)
            self.assertIn("--directed", cmd)
            self.assertEqual(cmd[cmd.index("--dataset") + 1], "/targets/fresh/datasets/weighted64k")
            self.assertEqual(cmd[cmd.index("--output") + 1], "/targets/fresh/cells/" + cell["id"])
            self.assertEqual(cmd[cmd.index("--sail-binary") + 1], prior["container_sail_binary"])
        self.assertEqual(prior, originals)
        self.assertEqual(configs[0]["limits"], dict(cpus=8, cpuset_cpus="0-7", memory_gib=12, outer_timeout_seconds=1350))

    def test_changed_runtime_or_envelope_is_rejected(self):
        for key, value in (("runtime_source_sha", "different"), ("container_sail_binary", "/targets/new-binary"),
                           ("defaults", {}), ("limits", {})):
            prior = shared.config()
            prior[key] = value
            with self.assertRaisesRegex(ValueError, key):
                runner.cell_config(prior, "base", "/targets/fresh", "/host/fresh")

    def test_fixture_bound_and_edge_formula_against_real_generator(self):
        prior = shared.config()
        cfg = runner.cell_config(prior, "base", "/targets/fresh", "/host/fresh")
        dataset = cfg["datasets"][runner.DATASET]
        self.assertLessEqual(dataset["vertices"], 100000)
        self.assertLessEqual(dataset["degree"], 64)
        self.assertEqual(runner.expected_edges(dataset["vertices"], dataset["degree"]), 4216091)
        cmd = matrix.dataset_command(cfg, runner.DATASET)
        self.assertEqual(cmd[cmd.index("--vertices") + 1], "65536")
        self.assertEqual(cmd[cmd.index("--degree") + 1], "64")
        with tempfile.TemporaryDirectory() as root:
            fixture = traversal_fixture.prepare(Path(root) / "tiny", vertices=8, degree=64, seed=42)
        self.assertEqual(fixture["counts"]["edges"], runner.expected_edges(8, 64))

    def test_candidate_gate_required_and_prior_failures_remain_visible(self):
        cells = [dict(c, outcome="passed") for c in shared.schedule()]
        cells[0]["outcome"] = "test_failure"
        self.assertTrue(runner.prior_ready(dict(cells=cells)))
        self.assertEqual(cells[0]["outcome"], "test_failure")
        cells[1]["outcome"] = "test_failure"
        self.assertFalse(runner.prior_ready(dict(cells=cells)))
        self.assertFalse(runner.prior_ready(dict(cells=cells[:-1])))

    def test_existing_successful_runtime_identity_must_be_uniform(self):
        cells = [dict(c, outcome="passed", binary_sha256="binary", native_identity_sha256="native")
                 for c in shared.schedule()]
        self.assertEqual(runner.identities(dict(cells=cells)),
                         dict(binary_sha256="binary", native_identity_sha256="native"))
        cells[-1]["binary_sha256"] = "changed"
        with self.assertRaisesRegex(AssertionError, "binary_sha256"):
            runner.identities(dict(cells=cells))


if __name__ == "__main__":
    unittest.main()
