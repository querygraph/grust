"""Build and seal dataset-neutral B8 references, outside engine timers."""
from __future__ import annotations

import argparse
import json
import platform
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import numpy as np
import pyarrow as pa
import shape_reference
from shape_reference import (
    InputConfig,
    ReferenceReceipt,
    admit,
    edge_schema,
    input_identities,
    load_pairs,
    read_columns,
    require,
    save,
    sha,
    sorted_ids,
    stream_initial_maps,
    write_adjacency_reference,
    write_pairs,
)

Value = TypeVar('Value')


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def timed(receipt: ReferenceReceipt, name: str, action: Callable[[], Value]) -> Value:
    start = time.perf_counter()
    try:
        return action()
    finally:
        receipt.phases_seconds[name] = time.perf_counter() - start
        save(receipt.config.output / 'receipt.json', receipt)


def prepare(config: InputConfig) -> ReferenceReceipt:
    config.output.mkdir(parents=True, exist_ok=False)
    receipt = ReferenceReceipt(config=config, started_utc=utc(), helper_sha256={
        'prepare_shapes.py': sha(Path(__file__)), 'shape_reference.py': sha(Path(shape_reference.__file__))},
        packages={'python': platform.python_version(), 'numpy': np.__version__, 'pyarrow': pa.__version__})
    path = config.output / 'receipt.json'
    save(path, receipt)
    began = time.perf_counter()
    try:
        receipt.inputs_before = timed(receipt, 'initial_input_pins', lambda: input_identities(config))
        admission = timed(receipt, 'footer_admission', lambda: admit(config))
        receipt.admission = admission
        vertices, vertex_schema = timed(receipt, 'vertex_load', lambda: read_columns(config.vertices, ['id']))
        receipt.input_schemas = [vertex_schema, edge_schema(config.edges)]
        ids = timed(receipt, 'vertex_domain', lambda: sorted_ids(vertices[0]))
        receipt.vertex_rows, receipt.edge_rows = len(ids), admission.edge_rows
        require(len(ids) == admission.vertex_rows, 'vertex physical/footer rows')
        # Build/write each shape sequentially; do not retain the largest pairset
        # while constructing the two smaller vertex maps.
        def write_adjacency() -> None:
            receipt.artifacts['adjacency'] = write_adjacency_reference(config.output, config.edges, admission.edge_rows)
        timed(receipt, 'adjacency_reference', write_adjacency)
        reps, labels, isolates = timed(receipt, 'initial_maps', lambda: stream_initial_maps(ids, config.edges))
        receipt.isolated_vertices = isolates
        receipt.artifacts['representatives'] = timed(receipt, 'representative_write', lambda: write_pairs(config.output, 'representatives', reps))
        receipt.artifacts['min-label-initial-round'] = timed(receipt, 'min_label_write', lambda: write_pairs(config.output, 'min-label-initial-round', labels))
        receipt.inputs_after = timed(receipt, 'final_input_pins', lambda: input_identities(config))
        require(receipt.inputs_before == receipt.inputs_after, 'original input identity changed')
        for shape, artifact in receipt.artifacts.items():
            load_pairs(path, artifact, shape)
        receipt.outcome = 'passed'
    except BaseException as error:  # noqa: BLE001 - retain interrupted/error reference attempts and partial artifacts
        receipt.outcome, receipt.error = 'error', repr(error) + '\n' + traceback.format_exc()
    finally:
        receipt.phases_seconds['whole_reference_phase'] = time.perf_counter() - began
        receipt.finished_utc = utc()
        save(path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    config = InputConfig.model_validate_json(parser.parse_args().config.read_text())
    receipt = prepare(config)
    print(json.dumps({'outcome': receipt.outcome, 'receipt': str(config.output / 'receipt.json')}), flush=True)
    return 0 if receipt.outcome == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
