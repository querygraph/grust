"""Offline controls: adversarial receipts and mock children; never launch Docker."""
from __future__ import annotations

import copy
import json
import signal
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pyarrow as pa
import pyarrow.parquet as pq
import run_pair_queue as queue
import run_shapes_host as host
from pydantic import BaseModel, ValidationError

Json = dict[str, Any]


def write(path: Path, value: BaseModel | Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.model_dump_json() if isinstance(value, BaseModel) else json.dumps(value))


def config_fixture(base: Path) -> tuple[queue.QueueConfig, Path]:
    base.mkdir()
    pins: dict[str, queue.FilePin] = {}
    for name in ('driver', 'campaign', 'plan', 'config_index', 'prerequisites', 'support_manifest'):
        path = base/(name+'.json')
        write(path, {})
        pins[name] = queue.pin(path)
    config = queue.QueueConfig(host_root=base, output=base/'queue-test', python=Path('/offline/python'), **pins)
    path = base/'queue-config.json'
    write(path, config)
    return config, path


def cell_configuration(base: Path, run_id: str, shape: queue.Shape = 'adjacency', variant: queue.Variant = 'union') -> host.CellConfiguration:
    return host.CellConfiguration(dataset='cit-Patents', shape=shape, variant=variant, repo=base/'repo', harness_repo=base/'harness',
        support=base/'support', output=base/'cells'/run_id, vertices=base/'vertices', edges=base/'edges', references=base/'references',
        binary=base/'sail', reference_receipt_sha256='a'*64, support_sha256='b'*64)


def audit_fixture(base: Path) -> tuple[queue.QueueConfig, host.Campaign, queue.Step, host.CellConfiguration, Json, Json, Json]:
    config, _ = config_fixture(base)
    campaign = host.Campaign(host_root=base, guest_root='/targets/offline')
    step = queue.Step(dataset='cit-Patents', shape='representatives', variant='array-explode', run_id='offline-cell',
                      role='measured', sequence_within_contrast=4, measured_block=1)
    artifacts = base/step.run_id/'container/artifacts'
    result = artifacts/'engine/result/part.parquet'
    result.parent.mkdir(parents=True)
    pq.write_table(pa.table({'id': pa.array([-2**63, 1], pa.int64()), 'representative': pa.array([-3, -3], pa.int64())}), result)
    file = queue.pin(result)
    output_identity = {'bytes': file.bytes, 'sha256': file.sha256}
    reference = {'config': {}, 'artifacts': {'representatives': {'file': 'representatives.i64le', 'rows': 2,
        'columns': ['id', 'representative'], 'identity': {'bytes': 32, 'sha256': 'a'*64}}}}
    reference_path = base/'reference01/container/artifacts/receipt.json'
    write(reference_path, reference)
    reference_pin = queue.pin(reference_path)
    effective = host.CellConfiguration(dataset='cit-Patents', shape=step.shape, variant=step.variant,
        repo=Path(campaign.guest_root)/'repo', harness_repo=Path(host.HARNESS_REPO), support=Path(campaign.guest_root)/'support',
        output=Path(campaign.guest_root)/'cells'/step.run_id, vertices=Path('/targets/offline/vertices'), edges=Path('/targets/offline/edges'),
        references=Path(campaign.guest_root)/'references/reference01', binary=Path(host.SAIL),
        reference_receipt_sha256=reference_pin.sha256, support_sha256=config.support_manifest.sha256,
        minimum_free_bytes=campaign.guest_reserve_bytes)
    write(base/step.run_id/'helper-config.json', effective)
    child_config = {'repo': str(effective.repo), 'harness_repo': str(effective.harness_repo), 'output': str(effective.output/'engine'),
        'vertices': str(effective.vertices), 'edges': str(effective.edges), 'binary': str(effective.binary), 'mode': 'local',
        'partitions': 16, 'pool_bytes': 30*2**30, 'native_quota': 256*2**20, 'shape': step.shape, 'variant': step.variant}
    write(artifacts/'engine-config.json', child_config)
    plans = [{'relation': 'shape-result', 'file': 'plan-shape-result.txt', 'scope': 'raw explain'}]
    plan_path = artifacts/'engine/plan-shape-result.txt'
    plan_path.write_text('actual physical plan fixture')
    plan_pin = queue.pin(plan_path)
    plan_identity = {'bytes': plan_pin.bytes, 'sha256': plan_pin.sha256}
    package = effective.repo/'examples/extensions/graph-algorithms/src/pyspark_pecan'
    benchmark = effective.harness_repo/'examples/extensions/benchmarks'
    engine = {'outcome': 'passed', 'finished_utc': 'observed', 'config': child_config, 'result_exported': True,
        'controller_pin': queue.SOURCE, 'runtime_pin': queue.RUNTIME, 'native_pin': queue.NATIVE,
        'actual_method': queue.actual_method(step.shape, step.variant), 'plans': plans,
        'origins': {**{key: str(path) for key, path in {'algorithms': package/'algorithms.py',
            'wcc_randomized': package/'wcc_randomized.py', 'runtime': benchmark/'runtime.py', 'measurement': benchmark/'measurement.py'}.items()},
            'python_executable': host.PYTHON}, 'output_projection': ['id', 'representative'],
        'output_schema': [{'name': n, 'type': 'bigint'} for n in ('id', 'representative')]}
    write(artifacts/'engine/engine-receipt.json', engine)
    identity = {'controller': queue.SOURCE, 'harness': queue.HARNESS, 'binary': host.SAIL_SHA, 'support': {},
                'reference_phase': reference, 'native': {'files_sha256': {'native.so': host.NATIVE_SHA}}}
    snapshot = {'cpu.max': '1600000 100000', 'memory.max': str(32*2**30), 'memory.swap.max': '0', 'memory.events': 'oom 0\noom_kill 0'}
    producer = {'outcome': 'passed', 'finished_utc': 'observed', 'config': effective.model_dump(mode='json'),
        'engine_returncode': 0, 'engine_wait_completed': True, 'execution_verified': True, 'ownership_admitted': True,
        'launch_to_exit_seconds': 1.5, 'sampled_engine_pss_peak_bytes': 1024, 'sampled_engine_pss_rows': 1,
        'sampled_engine_rows': 1, 'memory': {'execution_sampled': True}, 'identities_before': identity, 'identities_after': identity,
        'cgroups': {n: copy.deepcopy(snapshot) for n in ('before', 'after_engine', 'after_oracle', 'final')},
        'engine_receipt': engine, 'actual_engine_method': engine['actual_method'],
        'command': [host.PYTHON, '-B', str(effective.support/'engine_shapes.py'), '--config', str(effective.output/'engine-config.json')],
        'correctness': {'outcome': 'passed', 'full_oracle': True, 'shape': step.shape, 'rows': 2, 'unique': 2, 'expected_rows': 2,
            'mismatches': 0, 'duplicate_rows': 0, 'reference_artifact': reference['artifacts'][step.shape],
            'reference_receipt': {'bytes': reference_pin.bytes, 'sha256': reference_pin.sha256},
            'result_files': {'part.parquet': output_identity}, 'result_files_after': {'part.parquet': output_identity},
            'physical_schemas': [{'file': 'part.parquet', 'fields': [{'name': n, 'arrow_type': 'int64'} for n in ('id', 'representative')]}]},
        'plans': {'engine/plan-shape-result.txt': {**plan_identity, 'relation': 'shape-result', 'scope': 'raw explain'}}}
    write(artifacts/'receipt.json', producer)
    archive = {'engine/result/part.parquet': output_identity, 'engine/plan-shape-result.txt': plan_identity,
               'memory-samples.jsonl': {'bytes': 100, 'sha256': 'c'*64}, 'archive-manifest.json': {'bytes': 100, 'sha256': 'd'*64}}
    removal = {'certain_closure': True, 'ownership_verified': True, 'errors': [], 'create': {'returncode': 0, 'stdout': 'e'*64},
        'remove': {'returncode': 0}, 'absence_verified': {'returncode': 1, 'stderr': 'No such object'},
        'inspect': {'Id': 'e'*64, 'Image': host.IMAGE, 'State': {'Running': False, 'ExitCode': 0, 'OOMKilled': False},
            'HostConfig': {'NanoCpus': 10**9, 'Memory': 512*2**20, 'MemorySwap': 512*2**20, 'PidsLimit': 32,
                           'PidMode': '', 'ReadonlyRootfs': True, 'NetworkMode': 'none'}},
        'attach': {'returncode': 0, 'stdout': json.dumps({'outcome': 'passed', 'removed': str(effective.output), 'archive_sha256': 'd'*64})}}
    write(base/step.run_id/'payload-removal/orchestration.json', removal)
    return config, campaign, step, effective, reference, {'records': {'payload_removal': removal}}, archive


class FakeChild:
    def __init__(self, pid: int, code: int = 0, on_wait: Callable[[], None] | None = None) -> None:
        self.pid, self.code, self.on_wait = pid, code, on_wait
        self.done = False

    def wait(self) -> int:
        if self.on_wait is not None:
            self.on_wait()
        self.done = True
        return self.code

    def poll(self) -> int | None:
        return self.code if self.done else None


class QueueControls(unittest.TestCase):
    def test_actual_schema_and_method_golden_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, campaign, step, effective, reference, recorded_host, archive = audit_fixture(Path(temporary)/'campaign')
            with mock.patch.object(queue, 'audited_archive', return_value=(recorded_host, archive, {})):
                audit = queue.audit_cell(step, config, campaign, effective, reference)
            self.assertTrue(audit['qualified'])
            self.assertEqual(audit['rows'], 2)
            self.assertEqual(audit['actual_method'], 'representatives-array-explode')

    def test_adversarial_cell_receipts_never_qualify(self) -> None:
        cases = ('method', 'reference-size', 'oracle-omit', 'output-changed', 'wrong-type', 'late-oom', 'cleanup', 'sampler', 'plan')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                config, campaign, step, effective, reference, recorded_host, archive = audit_fixture(Path(temporary)/'campaign')
                path = config.host_root/step.run_id/'container/artifacts/receipt.json'
                producer = queue.read(path)
                if case == 'method':
                    producer['actual_engine_method'] = 'another-method'
                elif case == 'reference-size':
                    producer['correctness']['reference_receipt']['bytes'] += 1
                elif case == 'oracle-omit':
                    producer['correctness']['rows'] -= 1
                elif case == 'output-changed':
                    producer['correctness']['result_files_after'] = {}
                elif case == 'wrong-type':
                    producer['correctness']['physical_schemas'][0]['fields'][0]['arrow_type'] = 'double'
                elif case == 'late-oom':
                    producer['cgroups']['final']['memory.events'] = 'oom 1\noom_kill 1'
                elif case == 'cleanup':
                    producer['emergency_cleanup'] = ['forced process stop']
                elif case == 'sampler':
                    producer['sampled_engine_pss_peak_bytes'] = 0
                else:
                    producer['plans']['engine/plan-shape-result.txt']['sha256'] = '0'*64
                write(path, producer)
                with mock.patch.object(queue, 'audited_archive', return_value=(recorded_host, archive, {})), self.assertRaises(ValueError):
                    queue.audit_cell(step, config, campaign, effective, reference)

    def test_independent_dataset_contract_rejects_relabelled_tiny_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'acquisition.json'
            write(path, {'outcome': 'passed'})
            identity = queue.Identity(bytes=32, sha256='a'*64)
            contract = queue.DatasetContract(vertices=identity, edges=identity, vertex_rows=2, edge_rows=1, evidence=queue.pin(path))
            reference = {'inputs_before': {'vertices': identity.model_dump(), 'edges': identity.model_dump()}, 'vertex_rows': 2, 'edge_rows': 1}
            with self.assertRaisesRegex(ValueError, 'cit-Patents'):
                queue.dataset_binding('cit-Patents', contract, reference)
            with self.assertRaisesRegex(ValueError, 'downloaded payload'):
                queue.dataset_binding('graph500-24', contract, reference)

    def test_plan_exact_two_dataset_warmup_and_twice_abba(self) -> None:
        plan = queue.build_plan()
        self.assertEqual(len(plan.steps), 60)
        for dataset in queue.DATASETS:
            for shape in queue.SHAPES:
                steps = [s for s in plan.steps if s.dataset == dataset and s.shape == shape]
                self.assertEqual([s.variant for s in steps], list(queue.ORDER))
                self.assertEqual([s.role for s in steps], ['warmup']*2+['measured']*8)
                self.assertEqual([s.measured_block for s in steps], [None, None, 1, 1, 1, 1, 2, 2, 2, 2])
        for mutation in ('variant', 'run_id', 'role'):
            raw = plan.model_dump(mode='json')
            raw['steps'][4][mutation] = {'variant': 'union', 'run_id': raw['steps'][0]['run_id'], 'role': 'warmup'}[mutation]
            with self.assertRaises(ValidationError):
                queue.Plan.model_validate(raw)

    def test_tiny_physical_highbit_duplicate_loop_and_isolate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            vertices, edges = base/'vertices.parquet', base/'edges.parquet'
            ids = [-2**63, -7694170072594669674, -3, 0, 1, 2, 2**53+1, 2**63-1]
            pq.write_table(pa.table({'id': pa.array(ids, pa.int64())}), vertices)
            sources, targets = [1, 1, 2, 0, -2**63, -3], [2, 2, 2, 0, -3, 2**53+1]
            pq.write_table(pa.table({'source': pa.array(sources, pa.int64()), 'target': pa.array(targets, pa.int64())}), edges)
            inputs = queue.TinyInputs(vertices=queue.pin(vertices), edges=queue.pin(edges))
            observed = queue.tiny_observations(inputs)
            self.assertIn(str(2**53+1), observed['high_magnitude_ids'])
            self.assertEqual(observed['duplicate_edges'], 1)
            self.assertEqual(observed['self_loops'], 2)
            self.assertIn('-7694170072594669674', observed['isolated_ids'])
            # Updating a physical file without updating its contract is rejected first.
            pq.write_table(pa.table({'id': pa.array([float(n) for n in ids], pa.float64())}), vertices)
            with self.assertRaisesRegex(ValueError, 'changed'):
                queue.tiny_observations(inputs)
            inputs.vertices = queue.pin(vertices)
            with self.assertRaisesRegex(ValueError, 'signed64'):
                queue.tiny_observations(inputs)

    def test_prerequisite_coverage_requires_both_references_and_six_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = config_fixture(Path(temporary)/'campaign')
            proof = queue.HostProof(run_id='stage', directory=config.host_root/'stage', files={})
            raw = queue.Prerequisites(stage=proof, references={'cit-Patents': proof}, datasets={}, tiny_inputs=queue.TinyInputs(
                vertices=config.driver, edges=config.driver), tiny_controls=[])
            write(config.prerequisites.path, raw)
            receipt = queue.Receipt(config=config, dataset='cit-Patents', owner_pid=1, token='x', started_utc='x', observed_utc='x')
            with self.assertRaisesRegex(ValueError, 'both full references'):
                queue.prerequisite_audits(config, receipt, host.Campaign(host_root=config.host_root, guest_root='/targets/mock'))
            with self.assertRaisesRegex(ValueError, 'regular pinned'):
                queue.proof_files(proof, config, receipt, 'stage')

    def test_complete_archive_rejects_unlisted_or_changed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            artifacts = base/'container/artifacts'
            artifacts.mkdir(parents=True)
            (artifacts/'result.bin').write_bytes(b'actual bytes')
            write(artifacts/'archive-manifest.json', {'schema_version': 1, 'files': host.collected_inventory(artifacts)})
            actual = host.collected_inventory(artifacts)
            write(base/'collected-manifest.json', actual)
            self.assertEqual(queue.physical_archive(base, {'artifacts': actual}), actual)
            (artifacts/'extra.bin').write_bytes(b'unlisted')
            with self.assertRaisesRegex(ValueError, 'hash/set'):
                queue.physical_archive(base, {'artifacts': actual})

    def test_no_oom_including_final_and_private_envelope(self) -> None:
        snapshot = {'cpu.max': '1600000 100000', 'memory.max': str(32*2**30), 'memory.swap.max': '0',
                    'memory.events': 'oom 0\noom_kill 0\n'}
        cgroups = {name: copy.deepcopy(snapshot) for name in ('before', 'after_engine', 'after_oracle', 'final')}
        queue.no_oom(cgroups)
        cgroups['final']['memory.events'] = 'oom 1\noom_kill 0\n'
        with self.assertRaisesRegex(ValueError, 'OOM'):
            queue.no_oom(cgroups)
        cgroups['final'] = dict(snapshot, **{'memory.swap.max': '1024'})
        with self.assertRaisesRegex(ValueError, 'no-swap'):
            queue.no_oom(cgroups)

    def test_empty_metadata_proof_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, _ = config_fixture(Path(temporary)/'campaign')
            directory = config.host_root/'stage'
            for name in ('result.json', 'support-identities.json', 'stage/orchestration.json', 'stage/stage-receipt.json'):
                write(directory/name, {})
            receipt = queue.Receipt(config=config, dataset='cit-Patents', owner_pid=1, token='x', started_utc='x', observed_utc='x')
            with self.assertRaisesRegex(ValueError, 'complete prerequisite'):
                queue.proof_files(queue.HostProof(run_id='stage', directory=directory, files={}), config, receipt, 'stage')

    def exercise_queue(self, base: Path, failure: str | None = None) -> tuple[int, queue.QueueConfig, list[str]]:
        config, path = config_fixture(base)
        calls: list[str] = []
        changed = base/'future-config.json'
        write(changed, {'phase': 'frozen'})
        selected = [s for s in queue.build_plan().steps if s.dataset == 'cit-Patents']
        configs = {s.run_id: cell_configuration(base, s.run_id, s.shape, s.variant) for s in selected}

        def prepared(actual: queue.QueueConfig, dataset: queue.Dataset, receipt: queue.Receipt) -> tuple[host.Campaign, dict[str, host.CellConfiguration], dict[queue.Dataset, Json]]:
            self.assertEqual(dataset, 'cit-Patents')
            receipt.pins.append(queue.pin(changed))
            for step in selected:
                receipt.cells.append(queue.CellProgress(step=step, command=['mock', step.run_id], log=base/(step.run_id+'.host.log')))
            return host.Campaign(host_root=actual.host_root, guest_root='/targets/mock'), configs, {'cit-Patents': {}}

        def spawn(command: list[str], log: Path) -> queue.Child:
            run_id = command[-1]
            calls.append(run_id)
            log.write_text('offline fake host\n')
            write(base/run_id/'result.json', {'run_id': run_id, 'outcome': 'passed' if failure is None else 'error', 'error': 'retained raw'})
            if failure == 'interrupt':
                def interrupt() -> None:
                    raise InterruptedError('offline interruption')
                return FakeChild(800+len(calls), on_wait=interrupt)
            if failure == 'change-future':
                def mutate() -> None:
                    write(changed, {'phase': 'modified'})
                return FakeChild(800+len(calls), on_wait=mutate)
            return FakeChild(800+len(calls), code=2 if failure == 'exit' else 0)

        with mock.patch.object(queue, 'prepare', side_effect=prepared), mock.patch.object(queue, 'audit_cell', return_value={'qualified': True}):
            code = queue.run(path, 'cit-Patents', spawn)
        return code, config, calls

    def test_serial_all30_pass_release_only_owned_queue_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            code, config, calls = self.exercise_queue(Path(temporary)/'campaign')
            self.assertEqual(code, 0)
            self.assertEqual(calls, [s.run_id for s in queue.build_plan().steps if s.dataset == 'cit-Patents'])
            receipt = queue.read(config.output/'receipt.json')
            self.assertEqual(receipt['outcome'], 'passed')
            self.assertFalse(receipt['lock_retained'])
            self.assertTrue(all(c['outcome'] == 'passed' and c['child_pid'] > 0 for c in receipt['cells']))
            self.assertFalse((config.host_root.parent/'serial-queue.lock').exists())

    def test_failure_stops_no_retry_and_retains_raw_receipt_and_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            code, config, calls = self.exercise_queue(Path(temporary)/'campaign', 'exit')
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            receipt = queue.read(config.output/'receipt.json')
            self.assertEqual(receipt['cells'][0]['raw_receipts']['host']['error'], 'retained raw')
            self.assertTrue(receipt['lock_retained'])
            self.assertTrue((config.host_root.parent/'serial-queue.lock/owner.json').is_file())
            with self.assertRaisesRegex(ValueError, 'fresh queue'):
                queue.run(config.host_root/'queue-config.json', 'cit-Patents')

    def test_mutated_future_config_stops_before_second_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            code, config, calls = self.exercise_queue(Path(temporary)/'campaign', 'change-future')
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            self.assertIn('immutable file changed', queue.read(config.output/'receipt.json')['error'])

    def test_interrupted_child_pid_preserved_without_signalling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(signal, 'raise_signal') as signalling:
            code, config, calls = self.exercise_queue(Path(temporary)/'campaign', 'interrupt')
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            receipt = queue.read(config.output/'receipt.json')
            self.assertEqual(receipt['outcome'], 'interrupted')
            self.assertEqual(receipt['active_child_pid'], 801)
            self.assertEqual(receipt['cells'][0]['outcome'], 'active_child_uncertain')
            self.assertTrue(receipt['lock_retained'])
            signalling.assert_not_called()

    def test_a2_a3_global_lock_refuses_without_touching_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config, path = config_fixture(Path(temporary)/'campaign')
            lock = config.host_root.parent/'serial-queue.lock'
            write(lock/'owner.json', {'pid': 321, 'token': 'other queue'})
            with self.assertRaises(FileExistsError):
                queue.run(path, 'cit-Patents')
            self.assertEqual(queue.read(lock/'owner.json')['token'], 'other queue')
            self.assertFalse(config.output.exists())


if __name__ == '__main__':
    unittest.main()
