"""No remote execution: verify reuse and isolation of the two follow-up cells."""
from pathlib import Path
import unittest

import run_grenada_gate3 as runner
import run_pecan_gate3 as shared


class Matrix:
    def cell_command(self, config, cell):
        return [config["container_repo"] + "/graph_cell.py", "--engine", cell["engine"],
                "--dataset", config["container_root"] + "/datasets/weighted16k", "--output",
                config["container_root"] + "/cells/" + cell["cell_id"]]


class GrenadaTests(unittest.TestCase):
    def test_same_sources_resources_fixture_and_new_outputs(self):
        prior = shared.config()
        for cell in runner.schedule():
            cfg = runner.cell_config(prior, cell, "/targets/new", Path("/host/new"))
            self.assertEqual(cfg["container_repo"], shared.source_config(prior, cell["label"])["container_repo"])
            for key in ("limits", "defaults", "container_sail_binary", "native_source_sha", "runtime_source_sha"):
                self.assertEqual(cfg[key], prior[key])
            cmd = runner.command(Matrix(), prior, cell, "/targets/new", Path("/host/new"))
            self.assertEqual(cmd[cmd.index("--dataset") + 1], prior["container_root"] + "/datasets/weighted16k")
            self.assertEqual(cmd[cmd.index("--engine") + 1], "nutmeg-datafusion")
            self.assertTrue(cmd[cmd.index("--output") + 1].startswith("/targets/new/cells/"))
        self.assertEqual(prior, shared.config(), "building follow-up cells must not mutate prior config")

    def test_all_terminal_outcomes_required_but_failure_not_hidden(self):
        cells = [dict(c, outcome="passed") for c in shared.schedule()]
        self.assertTrue(runner.completed_suite(dict(cells=cells)))
        self.assertFalse(runner.completed_suite(dict(cells=cells[:-1])))
        cells[-1]["outcome"] = "started"
        self.assertFalse(runner.completed_suite(dict(cells=cells)))
        cells[-1]["outcome"] = "error"
        self.assertTrue(runner.completed_suite(dict(cells=cells)))
        self.assertEqual(cells[-1]["outcome"], "error")


if __name__ == "__main__":
    unittest.main()
