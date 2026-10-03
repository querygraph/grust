"""Actual registration syntax and admission failures, without a native import."""
import unittest

import worker_ready


class RegistrationControl(unittest.TestCase):
    def test_starting_is_not_registered(self) -> None:
        self.assertEqual(worker_ready.registered_ids("starting worker 1\nstarting worker 2\n"), set())
        self.assertEqual(worker_ready.registered_ids("worker 1 is available at 127.0.0.1:1\n"), {1})

    def test_distinct_registered_ids(self) -> None:
        raw = "worker 1 is available at 127.0.0.1:1\nworker 1 is available at 127.0.0.1:1\n"
        self.assertEqual(worker_ready.registered_ids(raw), {1})
        self.assertEqual(worker_ready.registered_ids(raw + "worker 2 is available at 127.0.0.1:2\n"), {1, 2})

    def test_preceding_data_job_refused(self) -> None:
        with self.assertRaises(ValueError):
            worker_ready.registered_ids("job 1 execution plan\nworker 1 is available at 127.0.0.1:1\n")


if __name__ == "__main__":
    unittest.main()
