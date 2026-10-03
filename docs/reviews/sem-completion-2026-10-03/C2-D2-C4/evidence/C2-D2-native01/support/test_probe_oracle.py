"""Independent wrong-answer and task-ownership controls; no engine imports."""
import unittest

import probe_oracle as oracle


class Controls(unittest.TestCase):
    def test_signed_full_answer(self) -> None:
        oracle.verify_rows([[2, 5, 1], [-(1 << 63), -4, 2]],
                           [[-(1 << 63), -4, 2], [2, 5, 1]],
                           [("src", "bigint"), ("minimum", "bigint"), ("count", "bigint")],
                           ["src", "minimum", "count"])

    def test_missing_duplicate_and_wrong_value(self) -> None:
        expected = [[-7, 2], [3, 4]]
        for actual in ([[3, 4]], [[-7, 2], [-7, 2], [3, 4]], [[-7, 2], [3, 5]]):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                oracle.verify_rows(actual, expected, [("id", "bigint"), ("value", "bigint")], ["id", "value"])

    def test_wrong_schema_and_boolean(self) -> None:
        for rows, schema in (([[1, 2]], [("other", "bigint"), ("value", "bigint")]),
                             ([[1, 2]], [("id", "int"), ("value", "bigint")]),
                             ([[1, True]], [("id", "bigint"), ("value", "bigint")])):
            with self.subTest(rows=rows, schema=schema), self.assertRaises(ValueError):
                oracle.verify_rows(rows, [[1, 2]], schema, ["id", "value"])

    def test_job_and_task_worker_binding(self) -> None:
        logs = {8: "job 10 stage 1 partition 0 attempt 0 execution plan\n"
                    "job 99 stage 1 partition 2 attempt 0 execution plan\n",
                9: "job 10 stage 1 partition 1 attempt 0 execution plan\n"}
        self.assertEqual(oracle.task_evidence(logs, {10}), ([8, 9], 2))
        self.assertEqual(oracle.task_evidence(logs, {99}), ([8], 1))
        self.assertEqual(oracle.task_evidence(logs, {20}), ([], 0))

    def test_conflicting_worker_task_attempt(self) -> None:
        text = "job 1 stage 0 partition 0 attempt 0 execution plan\n"
        with self.assertRaises(ValueError):
            oracle.task_evidence({1: text, 2: text}, {1})


if __name__ == "__main__":
    unittest.main()
