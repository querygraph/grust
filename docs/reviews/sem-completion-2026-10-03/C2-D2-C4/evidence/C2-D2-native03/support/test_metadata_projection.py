"""Exercise the actual pure SQL projection function without importing Spark."""
import ast
import unittest
from pathlib import Path
from typing import Any


class ProjectionControl(unittest.TestCase):
    def test_post_action_projection_preserves_all_unsigned_id_fields(self) -> None:
        path = Path(__file__).with_name("native_probe.py")
        tree = ast.parse(path.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "metadata_queries")
        namespace: dict[str, Any] = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)  # noqa: S102 - trusted pure function, without Spark/native imports
        queries: dict[str, str] = namespace["metadata_queries"]()
        for table, fields in {
            "execution.jobs": ["job_id"], "execution.stages": ["job_id", "stage", "partitions"],
            "execution.tasks": ["job_id", "stage", "partition", "attempt"], "cluster.workers": ["worker_id"],
        }.items():
            for field in fields:
                self.assertIn(f"CAST({field} AS BIGINT) AS {field}", queries[table])
        self.assertIn("CAST(inputs AS ARRAY<STRUCT<stage: BIGINT, mode: STRING>>) AS inputs", queries["execution.stages"])
        self.assertIn("CAST(port AS INT) AS port", queries["cluster.workers"])
        self.assertIn("to_json(value) AS value_json", queries["telemetry.metrics"])
        for table, query in queries.items():
            self.assertTrue(query.endswith(f"FROM system.{table}"))
            self.assertNotIn("SELECT *", query)


if __name__ == "__main__":
    unittest.main()
