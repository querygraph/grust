"""Full physical undirected BFS proof, outside all engine timing and processes."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyarrow as pa

import bfs_certificate as cert
import bfs_io as io
import bfs_models as m


def diagnostics(
    batch: pa.RecordBatch,
    config: m.Config,
    receipt: m.Receipt,
    owners: dict[int, m.Owner],
) -> None:
    values: dict[str, cert.I64] = {}
    valid = np.ones(batch.num_rows, dtype=np.bool_)
    for name in m.NATIVE[4:]:
        value, present = io.integers(batch, name, True)
        values[name] = value
        valid &= present
    if receipt.observed_terminal is None and np.any(valid):
        first = int(np.flatnonzero(valid)[0])
        receipt.observed_terminal = m.Terminal(
            **{
                name: int(values[name][first])
                for name in ("levels", "reached", "phase", "converged")
            }
        )
    same = valid.copy()
    if receipt.observed_terminal is not None:
        for name, value in receipt.observed_terminal.model_dump().items():
            same &= values[name] == value
    receipt.failures.raw_diagnostics += int(np.count_nonzero(~same))
    ids, valid_ids = io.integers(batch, "id", True)
    identity_ok = (
        valid
        & valid_ids
        & (values["owner"] == np.remainder(ids, config.partitions))
        & (values["worker_id"] >= 0)
        & (values["pid"] > 0)
        & (values["adjacency_id"] > 0)
        & (values["incoming_adjacency_id"] == 0)
    )
    receipt.failures.owner_identity += int(np.count_nonzero(~identity_ok))
    for owner in np.unique(values["owner"][identity_ok]):
        selected = identity_ok & (values["owner"] == owner)
        first = int(np.flatnonzero(selected)[0])
        identity = (
            int(values["worker_id"][first]),
            int(values["pid"][first]),
            int(values["adjacency_id"][first]),
        )
        key = int(owner)
        if key not in owners:
            owners[key] = m.Owner(
                owner=key,
                worker_id=identity[0],
                pid=identity[1],
                adjacency_id=identity[2],
            )
        recorded = owners[key]
        stable = (
            (values["worker_id"] == recorded.worker_id)
            & (values["pid"] == recorded.pid)
            & (values["adjacency_id"] == recorded.adjacency_id)
        )
        receipt.failures.owner_identity += int(np.count_nonzero(selected & ~stable))
        recorded.rows += int(np.count_nonzero(selected))


def projected_terminal(config: m.Config, deadline: io.Deadline) -> m.Terminal | None:
    if config.projected_terminal_receipt is None:
        return None
    observed = m.ProjectedTerminal.model_validate_json(
        io.read(config.projected_terminal_receipt, deadline)
    )
    if (
        observed.source_id != config.source_id
        or observed.max_levels != config.max_levels
        or observed.partitions != config.partitions
        or observed.result != config.result
        or observed.producer not in config.producer_evidence
    ):
        raise ValueError("projected actual result attributes/producer binding differs")
    return observed.terminal


def outputs(
    config: m.Config, state: cert.State, receipt: m.Receipt, deadline: io.Deadline
) -> None:
    names = m.NATIVE if config.schema_profile == "native13" else m.PROJECTED
    owners: dict[int, m.Owner] = {}
    parquet_names = sorted(
        name for name in config.result.files if name.endswith(".parquet")
    )
    if not parquet_names:
        raise ValueError("full raw Parquet output missing")
    for name in parquet_names:
        file = io.parquet(config.result.directory / name, names)
        physical = m.PhysicalFile(
            name=name,
            fields=list(file.schema_arrow.names),
            types=[str(field.type) for field in file.schema_arrow],
            nullable=[field.nullable for field in file.schema_arrow],
            footer_rows=file.metadata.num_rows,
        )
        receipt.physical_files.append(physical)
        for batch in io.batches(file, config.limits.batch_rows, deadline):
            (
                (ids, valid_id),
                (distance, valid_distance),
                (hops, valid_hops),
                (parent, valid_parent),
            ) = [io.integers(batch, key, True) for key in m.PROJECTED]
            state.result_batch(
                ids,
                distance,
                hops,
                parent,
                valid_id,
                valid_distance,
                valid_hops,
                valid_parent,
            )
            if config.schema_profile == "native13":
                diagnostics(batch, config, receipt, owners)
            physical.rows_examined += batch.num_rows
        if physical.rows_examined != physical.footer_rows:
            raise ValueError("output physical row count differs from footer")
        receipt.output_rows = state.rows
        receipt.progress = f"output:{name}"
        io.save(config.output / "receipt.json", receipt)
    receipt.owners = [owners[key] for key in sorted(owners)]


def edges(
    config: m.Config, state: cert.State, receipt: m.Receipt, deadline: io.Deadline
) -> None:
    names = (config.edge_source, config.edge_target)
    files = [io.edge_parquet(expected.path, config) for expected in config.edges]
    if sum(file.metadata.num_rows for file in files) != config.expected_edges:
        raise ValueError("original edge footer count differs")
    batch_number = 0
    for expected, file in zip(config.edges, files, strict=True):
        physical = m.InputEdgeFile(
            name=expected.path.name,
            input=expected,
            schema_profile=config.edge_schema_profile,
            fields=list(file.schema_arrow.names),
            types=[str(field.type) for field in file.schema_arrow],
            nullable=[field.nullable for field in file.schema_arrow],
            footer_rows=file.metadata.num_rows,
            examined_columns=list(names),
            deliberately_unused_columns=["weight"]
            if config.edge_schema_profile == "original_weight3"
            else [],
        )
        receipt.input_edge_physical_files.append(physical)
        for batch in io.batches(file, config.limits.batch_rows, deadline, names):
            source, _ = io.integers(batch, config.edge_source, False)
            target, _ = io.integers(batch, config.edge_target, False)
            state.edge_batch(source, target)
            physical.rows_examined += batch.num_rows
            batch_number += 1
            if batch_number % 32 == 0:
                receipt.edge_rows = state.edges
                receipt.progress = f"original_edges:{state.edges}"
                io.save(config.output / "receipt.json", receipt)
    if state.edges != config.expected_edges:
        raise ValueError("original edge physical row count differs")
    receipt.all_original_edges_examined = True


def verify(path: Path) -> m.Receipt:
    initial = io.Deadline.after(60)
    configuration = io.pin(path, initial)
    config = m.Config.model_validate_json(io.read(configuration, initial))
    config.output.mkdir(parents=True, exist_ok=False)
    receipt = m.Receipt(started_utc=io.utc(), configuration=configuration)
    io.save(config.output / "receipt.json", receipt)
    pins = [configuration, *config.all_pins()]
    try:
        deadline = io.Deadline.after(config.limits.work_seconds)
        for name, expected in config.helpers.items():
            if expected.path != Path(__file__).parent / name:
                raise ValueError("actual oracle helper origin differs")
        if (
            Path(cert.__file__) != config.helpers["bfs_certificate.py"].path
            or Path(io.__file__) != config.helpers["bfs_io.py"].path
            or Path(m.__file__) != config.helpers["bfs_models.py"].path
        ):
            raise ValueError("actual imported helper origins differ")
        receipt.pins_before = io.snapshot(pins, deadline)
        receipt.raw_files_before = io.inventory(config.result, deadline)
        receipt.source_before = io.source(config.source_contract, deadline)
        state = cert.State(
            io.load_vertices(config, receipt, deadline),
            config.source_id,
            config.limits.batch_rows,
        )
        receipt.failures = state.failures
        receipt.observed_terminal = projected_terminal(config, deadline)
        outputs(config, state, receipt, deadline)
        edges(config, state, receipt, deadline)
        state.finish(
            receipt,
            receipt.observed_terminal,
            config.max_levels,
            config.limits.batch_rows,
        )
        deadline.check()
        receipt.full_physical_certificate_passed = (
            receipt.full_domain_passed
            and receipt.failures.total() == 0
            and receipt.all_original_edges_examined
            and receipt.parent_paths_and_minimum_parent_passed
            and receipt.all_edge_lower_bound_and_reachability_passed
            and receipt.terminal_empty_expansion_cap_passed
        )
        if receipt.full_physical_certificate_passed:
            receipt.outcome = "passed_full_undirected_BFS_certificate"
        elif (
            receipt.failures.missing_ids
            or receipt.output_rows < config.expected_vertices
        ):
            receipt.outcome = "partial_output"
        elif (
            receipt.failures.total() == 0
            and receipt.full_domain_passed
            and not receipt.terminal_empty_expansion_cap_passed
        ):
            receipt.outcome = "cap_unqualified"
        else:
            receipt.outcome = "mismatch"
        receipt.progress = "full_certificate_completed"
    except BaseException as error:  # noqa: BLE001 - retain every failed physical/identity audit
        receipt.outcome = "error"
        receipt.errors.append(repr(error))
    finally:
        try:
            audit = io.Deadline.after(config.limits.audit_seconds)
            receipt.pins_after = io.snapshot(pins, audit)
            receipt.raw_files_after = io.inventory(config.result, audit)
            receipt.source_after = io.source(config.source_contract, audit)
            receipt.own_identity_closure_passed = (
                bool(receipt.pins_before)
                and receipt.pins_before == receipt.pins_after
                and receipt.raw_files_before == receipt.raw_files_after
                and receipt.source_before == receipt.source_after
            )
            if not receipt.own_identity_closure_passed:
                raise ValueError(
                    "before/after input/output/source/client closure incomplete"
                )
        except BaseException as error:  # noqa: BLE001 - late immutable failure cannot preserve pass
            receipt.outcome = "error"
            receipt.errors.append(f"immutable closure: {error!r}")
        receipt.finished_utc = io.utc()
        io.save(config.output / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    result = verify(parser.parse_args().config)
    raise SystemExit(
        0 if result.outcome == "passed_full_undirected_BFS_certificate" else 1
    )


if __name__ == "__main__":
    main()
