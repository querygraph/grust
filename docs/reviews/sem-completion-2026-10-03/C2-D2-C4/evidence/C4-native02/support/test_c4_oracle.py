"""Independent signed tuple fixtures and negative full-output controls."""
import unittest

import probe_oracle as oracle

FIELDS = [("src", "bigint"), ("distance", "double"), ("hops", "bigint"), ("parent", "bigint")]


class C4Control(unittest.TestCase):
    def test_all_fields_and_signed_ties(self) -> None:
        # Same distance, then same hops: the signed parent breaks the final tie.
        edges = [[-2**63, 2**63 - 1, 7], [-2**63, -2**63, 28],
                 [-2**63, -3, 49], [2**53 + 1, -7, 14], [2**53 + 1, 9, 8]]
        expected: list[list[int | float]] = [[-2**63, 0.0, 1, -2**63], [2**53 + 1, 0.0, 2, -7]]
        self.assertEqual(oracle.reference_rows(edges), expected)
        oracle.verify_c4_rows(expected, expected, FIELDS)

    def test_missing_or_duplicate_group(self) -> None:
        expected: list[list[int | float]] = [[-3, 1.0, 2, -7], [2**53 + 1, 2.0, 1, -2**63]]
        for rows in (expected[:1], [expected[0], expected[0]]):
            with self.assertRaises(ValueError):
                oracle.verify_c4_rows(rows, expected, FIELDS)

    def test_raw_double_is_not_an_integer_adapter(self) -> None:
        expected: list[list[int | float]] = [[-3, 1.0, 2, -7]]
        with self.assertRaises(ValueError):
            oracle.verify_c4_rows([[-3, 1, 2, -7]], expected, FIELDS)

    def test_signed_parent_requires_exact_bigint(self) -> None:
        expected: list[list[int | float]] = [[-3, 1.0, 2, 2**53 + 1]]
        for row in ([[-3, 1.0, 2, float(2**53 + 1)]], [[-3, 1.0, 2, 2**53]]):
            with self.assertRaises(ValueError):
                oracle.verify_c4_rows(row, expected, FIELDS)

    def test_nonfinite_or_wrong_field(self) -> None:
        expected: list[list[int | float]] = [[-3, 1.0, 2, -7]]
        for rows in ([[-3, float("nan"), 2, -7]], [[-3, 1.0, 3, -7]]):
            with self.assertRaises(ValueError):
                oracle.verify_c4_rows(rows, expected, FIELDS)
        with self.assertRaises(ValueError):
            oracle.verify_c4_rows(expected, expected, FIELDS[:3])

    def test_source_total_keys_must_be_unique(self) -> None:
        with self.assertRaises(ValueError):
            oracle.reference_rows([[-3, -7, 14], [-3, -7, 35]])


if __name__ == "__main__":
    unittest.main()
