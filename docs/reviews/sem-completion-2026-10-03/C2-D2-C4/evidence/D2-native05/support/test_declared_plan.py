"""Independent physical-plan counterexamples; no server/client imports."""
import unittest

import declared_plan


def logged(exchanges: int, *, join: str = "SortMergeJoin", partitions: int = 4,
           collect: bool = False) -> str:
    children = "".join("      RepartitionExec: partitioning=Hash([key@0], 4)\n"
                       "        DataSourceExec: checkpoint\n" for _ in range(exchanges))
    children += "      SortExec: key@0 ASC\n        DataSourceExec: checkpoint\n" * (2 - exchanges)
    if collect:
        children += "      CoalescePartitionsExec\n        DataSourceExec: checkpoint\n"
    return ("[driver] job 7 execution plan\n"
            "AggregateExec: mode=FinalPartitioned\n"
            "  RepartitionExec: partitioning=Hash([dst@0], 4)\n"
            f"    {join}: on=[(key@0, key@0)]\n{children}\n"
            "[driver] job 7 job graph\n=== stage 0 ===\n"
            f"inputs=[]\npartitions={partitions}\nplacement=Worker\n{join}: on=[(key@0, key@0)]\n"
            "[driver] dispatched tasks\n")


class Controls(unittest.TestCase):
    def test_three_actual_exchange_counts(self) -> None:
        for name, exchanges in (("path-path", 2), ("checkpoint-path", 1), ("checkpoint-checkpoint", 0)):
            result = declared_plan.inspect(logged(exchanges), f"round-{name}-00", 4)
            self.assertEqual(result.join_input_hash_exchanges, exchanges)
            self.assertEqual(result.declared_checkpoint_reuse, exchanges == 0)

    def test_aggregate_exchange_does_not_count_as_join_input_exchange(self) -> None:
        result = declared_plan.inspect(logged(0), "round-checkpoint-checkpoint-00", 4)
        self.assertEqual(result.join_input_hash_exchanges, 0)
        self.assertEqual(result.join_runtime_sorts, 2)

    def test_broadcast_or_collected_join_refused(self) -> None:
        for raw in (logged(0, join="HashJoinExec"), logged(0, collect=True)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                declared_plan.inspect(raw, "round-checkpoint-checkpoint-00", 4)

    def test_extra_input_exchange_and_wrong_partition_count_refused(self) -> None:
        for raw in (logged(1), logged(0, partitions=16)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                declared_plan.inspect(raw, "round-checkpoint-checkpoint-00", 4)

    def test_missing_or_multiple_jobs_refused(self) -> None:
        for raw in ("", logged(0) + logged(0)):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                declared_plan.inspect(raw, "round-checkpoint-checkpoint-00", 4)


if __name__ == "__main__":
    unittest.main()
