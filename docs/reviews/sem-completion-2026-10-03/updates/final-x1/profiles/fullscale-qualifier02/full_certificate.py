"""Bind the already executed whole-output certificate; never read Parquet."""

import json
from pathlib import Path

from pydantic import JsonValue

import control_io as io
import control_models as c
import full_models as m
import full_native as native
import oracle_models as bfs
import owner_models as o


class Manifest(m.Projection):
    schema_version: int
    family: str
    counts: dict[str, int]
    parameters: dict[str, JsonValue]
    files: dict[str, bfs.Identity]


def as_pin(value: bfs.Pin) -> o.Pin:
    return o.Pin.model_validate_json(value.model_dump_json())


def natural(wait: c.GenericWait) -> None:
    io.require(
        wait.outcome == "passed_actual_direct_child_wait"
        and wait.returncode == 0
        and wait.wait_completed
        and wait.child_group_absent
        and wait.immutable_closure
        and not wait.forced_cleanup
        and not wait.errors
        and wait.finished_utc is not None
        and wait.child_pid is not None
        and wait.child_pid == wait.child_pgid
        and wait.waiter_source_sha256 == c.GENERIC_WAIT_SHA,
        "actual original natural wait0 required",
    )


def command(expected: o.Pin) -> m.DirectWait:
    value = m.DirectWait.model_validate_json(io.read(expected))
    io.require(value.pid == value.pgid, "actual fresh process group differs")
    return value


def original_inputs(
    config: m.Config, producer: o.OwnerReceipt, request: bfs.Config
) -> list[o.Pin]:
    io.require(
        config.original_manifest.sha256 == m.ORIGINAL_SHA,
        "exact original manifest required",
    )
    manifest = Manifest.model_validate_json(io.read(config.original_manifest))
    restore = m.Restore.model_validate_json(io.read(config.restore_closure))
    root = Path(producer.plan.dataset.vertices.removeprefix("file://")).parent
    io.require(
        manifest.schema_version == 1
        and manifest.family == "graph500"
        and manifest.counts == {"vertices": 16777216, "edges": 268435456}
        and manifest.parameters.get("scale") == 24
        and manifest.parameters.get("source") == 13507776
        and manifest.parameters.get("directed") is False,
        "original generated contract differs",
    )
    io.require(
        restore.original_manifest_sha256 == m.ORIGINAL_SHA
        and restore.both_host_copy_root == root
        and not restore.signals_sent,
        "exact closed original restore differs",
    )
    io.require(
        producer.plan.dataset.vertices == (root / "vertices.parquet").as_uri()
        and producer.plan.dataset.edges == (root / "edges.parquet").as_uri(),
        "actual unprojected original dataset paths differ",
    )
    actual = {
        str(pin.path.relative_to(root)): bfs.Identity(
            bytes=pin.bytes, sha256=pin.sha256
        )
        for pin in [*request.vertices, *request.edges]
    }
    io.require(
        len(request.vertices) == 64
        and len(request.edges) == 1024
        and len(actual) == 1088
        and actual == manifest.files,
        "all1088 original Parquet identities, including weights, required",
    )
    io.require(
        all(pin.path.parent == root / "vertices.parquet" for pin in request.vertices)
        and all(pin.path.parent == root / "edges.parquet" for pin in request.edges),
        "original vertex/edge identities assigned to wrong input lists",
    )
    # Only these two small provenance files are read, never the Parquet payload.
    pins = [
        o.Pin.model_validate_json(json.dumps({"path": str(root / name), **identity}))
        for name, identity in m.PROVENANCE.items()
    ]
    for pin in pins:
        io.read(pin)
    return pins


def admitted_flags(oracle: bfs.Receipt) -> None:
    io.require(
        oracle.outcome == "passed_full_undirected_BFS_certificate"
        and oracle.finished_utc is not None
        and not oracle.errors
        and oracle.failures.total() == 0
        and all(
            (
                oracle.full_domain_passed,
                oracle.all_original_edges_examined,
                oracle.parent_paths_and_minimum_parent_passed,
                oracle.all_edge_lower_bound_and_reachability_passed,
                oracle.terminal_empty_expansion_cap_passed,
                oracle.full_physical_certificate_passed,
                oracle.own_identity_closure_passed,
            )
        ),
        "all seven full original certificate flags and zero failures required",
    )


def certificate(
    config: m.Config, producer: o.OwnerReceipt, proof: m.Proof, oracle: bfs.Receipt
) -> list[o.Pin]:
    request = bfs.Config.model_validate_json(io.read(as_pin(oracle.configuration)))
    copy = m.WholeCopy.model_validate_json(io.read(config.whole_copy))
    wait = command(copy.actual_wait)
    action = producer.action_receipt
    if action is None:
        raise ValueError("full client action missing")
    io.require(
        copy.producer == config.producer
        and request.result.directory.name == "native13"
        and action.output_uri == producer.plan.output_uri
        and producer.plan.output_uri.endswith("/native13"),
        "full output copy/request prefix differs",
    )
    source_prefix = (
        producer.plan.output_uri.removeprefix("s3://").removesuffix("/native13") + "/"
    )
    io.require(
        source_prefix in " ".join(wait.argv)
        and str(request.result.directory.parent) in " ".join(wait.argv),
        "actual copy command lacks this owned run prefix/destination",
    )
    files = {
        str(pin.path.relative_to(request.result.directory)): bfs.Identity(
            bytes=pin.bytes, sha256=pin.sha256
        )
        for pin in copy.files
        if request.result.directory in pin.path.parents
    }
    io.require(
        len({pin.path for pin in copy.files}) == len(copy.files)
        and all(
            request.result.directory.parent in pin.path.parents for pin in copy.files
        )
        and files == request.result.files,
        "whole recursive copy does not bind the complete native13 inventory",
    )
    admitted_flags(oracle)
    io.require(
        (
            request.dataset,
            request.expected_vertices,
            request.expected_edges,
            request.source_id,
            request.max_levels,
            request.partitions,
            request.edge_source,
            request.edge_target,
            request.edge_schema_profile,
            request.schema_profile,
        )
        == (
            "graph500-generated-scale24",
            16777216,
            268435456,
            13507776,
            8,
            32,
            "src",
            "dst",
            "original_weight3",
            "native13",
        )
        and request.source_contract.head == o.SOURCE
        and request.source_contract.tree == m.TREE
        and request.source_contract.repo == producer.plan.worker1.repo,
        "full oracle contract/source/native13 differs",
    )
    freeze = json.loads(io.read(config.oracle_freeze))
    io.require(
        config.oracle_freeze.sha256 == c.ORACLE_FREEZE_SHA
        and {name: pin.model_dump(mode="json") for name, pin in request.helpers.items()}
        == freeze["production_helpers"],
        "exact frozen oracle02 helper identity required",
    )
    required = [config.producer, config.whole_copy, config.original_wait]
    evidence = [as_pin(pin) for pin in request.producer_evidence]
    io.require(
        all(pin in evidence for pin in required),
        "oracle evidence does not bind this actual producer/copy/wait",
    )
    io.require(
        oracle.vertex_rows == oracle.output_rows == oracle.unique_output_ids == 16777216
        and oracle.edge_rows == 268435456
        and oracle.pins_before == oracle.pins_after
        and oracle.raw_files_before == oracle.raw_files_after == request.result.files
        and bool(oracle.raw_files_before)
        and oracle.source_before == oracle.source_after,
        "full original row/identity closure differs",
    )
    io.require(
        oracle.source_before is not None
        and oracle.source_before.head == o.SOURCE
        and oracle.source_before.tree == m.TREE
        and oracle.source_before.detached
        and oracle.source_before.status == "",
        "oracle actual clean detached source differs",
    )
    before = [as_pin(pin) for pin in oracle.pins_before]
    io.require(
        all(as_pin(pin) in before for pin in request.all_pins())
        and as_pin(oracle.configuration) in before,
        "oracle identity proof omits configured input/source/client/helper pins",
    )
    io.require(
        request.client_files
        == [
            bfs.Pin.model_validate_json(pin.model_dump_json())
            for pin in producer.plan.worker1.client_files
        ],
        "actual math client identity differs from native admitted host",
    )
    io.require(
        oracle.observed_terminal is not None
        and action.levels == proof.terminal_levels == oracle.computed_terminal_levels
        and action.reached == proof.terminal_reached == oracle.reached
        and action.converged is True
        and oracle.max_distance + 1 == oracle.computed_terminal_levels
        and 1 <= proof.terminal_levels <= 8,
        "actual action/native/full mathematical terminal differs",
    )
    terminal = oracle.observed_terminal
    if terminal is None:
        raise ValueError("terminal missing")
    io.require(
        (terminal.levels, terminal.reached, terminal.phase, terminal.converged)
        == (proof.terminal_levels, proof.terminal_reached, 9, 1),
        "physical repeated terminal differs",
    )
    io.require(
        len(oracle.owners) == 32
        and {row.owner for row in oracle.owners} == set(range(32))
        and sum(row.rows for row in oracle.owners) == 16777216
        and {row.worker_id for row in oracle.owners if row.rows} == {1, 2},
        "physical full owner row domain differs",
    )
    for row in oracle.owners:
        actual = proof.owners[row.owner]
        io.require(
            (row.worker_id, row.pid, row.adjacency_id)
            == (actual.worker_id, actual.pid, actual.adjacency_id)
            and row.rows == native.number(actual, "vertices"),
            "physical owner/process/init row map differs",
        )
    io.require(
        len(oracle.input_edge_physical_files) == 1024,
        "all1024 original edge files required",
    )
    # No set of mutable Pydantic pins: compare the explicit path->identity maps.
    physical_edges = {
        row.input.path: as_pin(row.input) for row in oracle.input_edge_physical_files
    }
    io.require(
        physical_edges == {pin.path: as_pin(pin) for pin in request.edges}
        and sum(row.rows_examined for row in oracle.input_edge_physical_files)
        == 268435456
        and all(
            row.fields == ["src", "dst", "weight"]
            and row.types == ["int64", "int64", "double"]
            and row.examined_columns == ["src", "dst"]
            and row.deliberately_unused_columns == ["weight"]
            and row.schema_profile == "original_weight3"
            and row.rows_examined == row.footer_rows
            for row in oracle.input_edge_physical_files
        ),
        "all original weighted physical edge files/endpoints must be examined",
    )
    io.require(
        {row.name for row in oracle.physical_files} == set(request.result.files)
        and sum(row.rows_examined for row in oracle.physical_files) == 16777216
        and all(
            row.fields == list(bfs.NATIVE) and row.rows_examined == row.footer_rows
            for row in oracle.physical_files
        ),
        "all raw native13 output files must be examined",
    )
    math_wait = command(config.oracle_wait)
    io.require(
        str(oracle.configuration.path) in math_wait.argv
        and "--config" in math_wait.argv
        and any(
            str(request.helpers["bfs_oracle.py"].path) in arg for arg in math_wait.argv
        ),
        "actual math wait/entry/configuration differs",
    )
    return [
        as_pin(oracle.configuration),
        copy.actual_wait,
        *original_inputs(config, producer, request),
    ]
