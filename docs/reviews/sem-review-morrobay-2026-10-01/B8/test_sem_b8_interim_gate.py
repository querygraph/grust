"""Bounded report/source guard controls; no engines, Docker or Git mutations."""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sem_b8_interim_gate as gate
from pydantic import ValidationError


def cell(sequence: int, variant: gate.Variant, seconds: float, *, warmup: bool = False) -> gate.Cell:
    return gate.Cell(run_id=f"fixture-{sequence}", shape="adjacency", variant=variant,
                     role="warmup" if warmup else "measured", measured_block=None if warmup else 1 if sequence<7 else 2,
                     sequence=sequence, rows=1, engine_child_launch_to_exit_seconds=seconds,
                     host_driver_launch_to_exit_seconds=seconds+10, oracle_seconds_outside_engine_boundary=5,
                     sampled_engine_pss_peak_bytes=1, guest_steal_fraction=0, evidence_keys=())


def cells() -> tuple[gate.Cell, ...]:
    return (cell(1,"union",100000,warmup=True), cell(2,"array-explode",1,warmup=True),
            cell(3,"union",2),cell(4,"array-explode",4),cell(5,"array-explode",8),cell(6,"union",4),
            cell(7,"union",4),cell(8,"array-explode",8),cell(9,"array-explode",16),cell(10,"union",8))


class InterimControls(unittest.TestCase):
    def test_boundaries_and_summary_formulas_are_distinct(self) -> None:
        result=gate.summarize(cells(),"adjacency")
        self.assertEqual(result.engine_child_ratio_of_medians,2)
        self.assertEqual(result.host_driver_ratio_of_medians,18/14)
        # Each exact mathematical ratio is2. exp/mean/log can round at the
        # final binary64 bit; this fixed fixture admits only one ulp at2.
        for ratio in result.engine_child_block_ratios_of_geometric_means:
            self.assertLessEqual(abs(ratio-2.0),math.ulp(2.0))
        self.assertEqual(result.engine_child_block_ratios_of_medians,(2,2))

    def test_warmups_are_excluded_from_medians(self) -> None:
        self.assertEqual(gate.summarize(cells(),"adjacency"),gate.summarize(cells()[2:],"adjacency"))

    def test_missing_measured_cell_is_not_a_complete_contrast(self) -> None:
        with self.assertRaisesRegex(ValueError,"four measured"):
            gate.summarize(cells()[:-1],"adjacency")

    def test_exact_original_plan_preserves_all_pending_graph_steps(self) -> None:
        steps=gate.expected_steps("graph500-24")
        self.assertEqual(len(steps),30)
        self.assertEqual(steps[0]["run_id"],gate.OOM)
        self.assertEqual([item["role"] for item in steps[:3]],["warmup","warmup","measured"])
        self.assertEqual([item["variant"] for item in steps[2:6]],["union","array-explode","array-explode","union"])
        self.assertEqual([item["measured_block"] for item in steps[6:10]],[2]*4)

    def test_payload_pin_is_refused_before_read(self) -> None:
        index=gate.Index(base=Path('/tmp'),observed_utc='fixture',payload_scope='historical metadata/source only; no Parquet, i64, native binary or raw archive rehash',files={'payload':gate.Evidence(path=Path('/tmp/never-open.parquet'),kind='text',bytes=1,sha256='0'*64)})
        with patch.object(gate,'bounded') as reader:
            with self.assertRaisesRegex(ValueError,'payload reads prohibited'):
                gate.load(index,'payload')
            reader.assert_not_called()

    def test_changed_metadata_bytes_or_schema_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json'
            original=b'{"outcome":"passed"}'
            path.write_bytes(original)
            evidence=gate.Evidence(path=path,kind='json',json_keys=('outcome',),**gate.identity(original).model_dump())
            index=gate.Index(base=path.parent,observed_utc='fixture',files={'receipt':evidence},payload_scope='historical metadata/source only; no Parquet, i64, native binary or raw archive rehash')
            self.assertEqual(gate.load(index,'receipt'),{'outcome':'passed'})
            changed=b'{"new_key":"passed"}'
            path.write_bytes(changed)
            with self.assertRaisesRegex(ValueError,'metadata pin changed'):
                gate.load(index,'receipt')
            altered=evidence.model_copy(update=gate.identity(changed).model_dump())
            with self.assertRaisesRegex(ValueError,'schema/key order changed'):
                gate.load(index.model_copy(update={'files':{'receipt':altered}}),'receipt')

    def test_incomplete_literal_cannot_be_complete_report(self) -> None:
        with self.assertRaises(ValidationError):
            gate.Report.model_validate({'report_kind':'b8_interim_incomplete','incomplete':False,'all60_done':True})
        with self.assertRaises(ValidationError):
            gate.GraphFailure.model_validate({'qualified':True,'ratio':1.0,'plan_scope':'pre-write relation explain; excludes Parquet sink wrapper','evidence_keys':[]})

    def test_source_guard_checks_actual_head_tree_and_parent(self) -> None:
        values=[b'1'*40+b'\n',b'2'*40+b'\n',b'1'*40+b' '+b'9'*40+b'\n']
        with patch.object(gate,'git',side_effect=values),self.assertRaisesRegex(ValueError,'single parent'):
            gate.source_guard(Path('/tmp/fake-detached'), '1'*40,'2'*40,'3'*40)

    def test_machine_values_refuse_nonfinite_diagnostics(self) -> None:
        value=cell(3,'union',2).model_dump()
        value['engine_child_launch_to_exit_seconds']=float('nan')
        with self.assertRaises(ValidationError):
            gate.Cell.model_validate(value)
        self.assertNotIn('NaN',json.dumps(gate.summarize(cells(),'adjacency').model_dump(),allow_nan=False))


    def test_configured_native_quota_cannot_be_observed_prepayment(self) -> None:
        report_path = Path(gate.__file__).with_name('interim-findings.json')
        report = gate.Report.model_validate_json(report_path.read_bytes())
        self.assertEqual(report.configured_native_quota_bytes, 256*2**20)
        self.assertFalse(report.native_reservation_observed)
        self.assertIsNone(report.actual_native_prepaid_bytes)
        self.assertIn('configured native quota', report.execution)
        for changed in ({'native_reservation_observed': True},
                        {'actual_native_prepaid_bytes': 256*2**20},
                        {'configured_native_quota_bytes': 0},
                        {'execution': report.execution.replace('configured native quota', 'native prepayment')}):
            with self.assertRaises(ValidationError):
                gate.Report.model_validate(report.model_dump() | changed)


if __name__=='__main__':
    unittest.main()
