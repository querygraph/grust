"""Metadata conjunction for the original native scale24 case; no runtime actions."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

import control_models as c
import owner_models as o

TREE = "89f3b77f12391de54afbe7c6cdad1e008d1dc702"
ORIGINAL_SHA = "8bad1a94c5a37715ce9320f27b3f13097ef50c2a9bfdfa15c25ed0665007c75c"
PROVENANCE = {
    "generator.stderr": {
        "bytes": 0,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    },
    "preparation.json": {
        "bytes": 3221,
        "sha256": "9df37003666a01f50ef02a6563a97b1874d4cb2ef6933a5373adcb7a889490ae",
    },
}
HELPERS = {
    "owner_models.py",
    "oracle_models.py",
    "control_models.py",
    "control_io.py",
    "control_logs.py",
    "full_models.py",
    "full_admission.py",
    "full_native.py",
    "full_certificate.py",
    "qualify_fullscale.py",
}


class Projection(o.Model):
    """Only named acceptance fields are projected; original JSON remains pinned."""

    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)


class DirectWait(Projection):
    argv: list[str] = Field(min_length=1)
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    returncode: Literal[0]
    actual_wait_completed: Literal[True]
    group_absent: Literal[True]
    forced_cleanup: Literal[False]


class HostObservation(Projection):
    host: Literal["morrobay", "capitola"]
    architecture: Literal["x86_64", "arm64"]
    source_before: dict[str, str]
    source_after: dict[str, str]
    pins_before: list[o.Pin]
    pins_after: list[o.Pin]
    metadata: list[o.Pin]
    recorded_pids: list[int]
    recorded_groups: list[int]
    processes_remaining: list[list[int]]


class Closure(Projection):
    outcome: Literal["passed_independent_twohost_case_closure"]
    producer: o.Pin
    original_wait: o.Pin
    configuration: o.Pin
    source: o.Pin
    owner_pid: int = Field(gt=1)
    owner_pgid: int = Field(gt=1)
    actual_wait_completed: Literal[True]
    owner_group_absent: Literal[True]
    source_unchanged: Literal[True]
    returncode: Literal[0]
    all_recorded_owned_processes_absent: Literal[True]
    immutable_closure: Literal[True]
    locks_released: Literal[True]
    hosts: list[HostObservation]
    observer_steps: list[o.ProcessProof]
    checked_local_pins: list[o.Pin]
    common_marker: o.Pin
    released_markers: list[o.Pin]
    forced_cleanup: Literal[False]
    errors: list[str]
    signals_sent: list[str]
    engine_qualified: Literal[False]
    historical_cause_identified: Literal[False]


class ClosureConfig(Projection):
    producer: o.Pin
    original_wait: o.Pin
    wait_configuration: o.Pin
    launch: o.Pin
    outer_launch_wait: o.Pin
    common_marker: o.Pin
    common_token: str
    helpers: dict[str, o.Pin]
    output: Path


class OuterBinding(Projection):
    original_outer_wait: o.Pin
    original_outer_configuration: o.Pin
    original_inner_wait: o.Pin
    launch: o.Pin
    waiter_source_sha256: str
    waiter_pid: int
    ssh_pid: int
    ssh_pgid: int
    argv: list[str]
    actual_natural_wait0: Literal[True]


class OuterFlat(o.Model):
    observed_utc: str
    pid: int = Field(gt=1)
    pgid: int = Field(gt=1)
    returncode: Literal[0]
    actual_wait_completed: Literal[True]
    group_absent: Literal[True]
    forced_cleanup: Literal[False]
    known_hosts: o.Pin


class OuterCurrentClosure(o.Model):
    observed_utc: str
    original_outer_wait: o.Pin
    original_outer_config: o.Pin
    actual_source: o.Pin
    known_hosts: o.Pin
    observed_ids_absent: list[int] = Field(min_length=1)
    flat_actual_wait: o.Pin
    outer_original_binding: o.Pin
    all_original_outer_ids_currently_absent: Literal[True]
    source_configuration_unchanged: Literal[True]
    scope: str


class WaitConfig(Projection):
    root: Path
    argv: list[str]
    timeout_seconds: int


class WholeCopy(o.Model):
    observed_utc: str
    outcome: Literal["copied_complete_owned_run_prefix_unqualified"]
    producer: o.Pin
    actual_wait: o.Pin
    files: list[o.Pin] = Field(min_length=1)
    full_output_math_or_process_qualified: Literal[False]
    scope: str


class Restore(Projection):
    outcome: Literal["closed_exact_original_twohost_restore"]
    immutable_closure: Literal[True]
    all_recorded_owned_processes_absent: Literal[True]
    locks_released: Literal[True]
    actual_wait_completed: Literal[True]
    returncode: Literal[0]
    original_manifest_sha256: str
    exact_provenance_bytes_preserved: Literal[True]
    exact_all_member_bytes_preserved: Literal[True]
    both_hosts_footer_rows_and_schemas_equal: Literal[True]
    both_host_copy_root: Path
    native_algorithm_run: Literal[False]
    regenerated_inputs: Literal[False]
    signals_sent: list[str]


class Binding(Projection):
    native_pid: int
    native_pgid: int
    supervisor_pid: int
    native_started_utc: str
    normal_waited_native_closure_observed: Literal[True]


class Watch(o.Model):
    name: Literal["driver", "worker1", "worker2", "client"]
    receipt: Path


class MemoryConfig(Projection):
    root: Path
    host: Literal["morrobay", "capitola"]
    architecture: Literal["x86_64", "arm64"]
    watches: list[Watch]
    stop: Path
    helpers: dict[str, o.Pin]
    interval_ms: Literal[500]


class MemoryReceipt(Projection):
    outcome: Literal["stopped_bounded_process_observations_only"]
    observer_pid: int = Field(gt=1)
    configuration: o.Pin
    config: MemoryConfig
    before: list[o.Pin]
    after: list[o.Pin]
    bindings: dict[str, Binding]
    source_closed: Literal[True]
    root_stop: o.Pin
    raw_chunks: list[o.Pin]
    final_native_receipts: dict[str, o.Pin]
    errors: list[str]
    observer_outer_wait_qualified: Literal[False]
    rooted_case_wait_closure_admitted_without_engine_qualification: Literal[True]
    PSS_or_cgroup_or_OS32_or_unique_process_sum_or_native_pool_fit: Literal[False]
    engine_or_historical_cause_qualified: Literal[False]


class RootStop(Projection):
    outcome: Literal["root_explicit_stop_after_closed_x1_case"]
    case_owner_receipt: o.Pin
    case_outer_wait: o.Pin
    case_root_closure: o.Pin
    all_case_owned_processes_closed: Literal[True]


class MemoryProof(o.Model):
    configuration: o.Pin
    original_wait_configuration: o.Pin
    helper_copies: dict[str, o.Pin]
    host: Literal["morrobay", "capitola"]
    receipt: o.Pin
    original_wait: o.Pin
    stop: o.Pin


class MemoryRootHost(Projection):
    original_wait: o.Pin
    producer: o.Pin
    actual_returncode: Literal[0]
    current_all_observer_ids_absent: Literal[True]


class MemoryRootCap(Projection):
    actual_original_wait: c.GenericWait
    producer: MemoryReceipt
    current_all_observer_ids_absent: Literal[True]
    pins: list[o.Pin]


class MemoryRoot(Projection):
    outcome: Literal["closed_natural_twohost_bounded_memory_observations_only"]
    morrobay: MemoryRootHost
    capitola: MemoryRootCap
    actual_cap_current_observation_wait: o.Pin


class Config(o.Model):
    kind: Literal["scale24"] = "scale24"
    producer: o.Pin
    original_wait: o.Pin
    canonical_wait: o.Pin
    outer_wait: o.Pin
    outer_binding: o.Pin
    original_outer_current_closure: o.Pin
    current_closure: o.Pin
    current_closure_wait: o.Pin
    whole_copy: o.Pin
    oracle: o.Pin
    oracle_freeze: o.Pin
    oracle_wait: o.Pin
    original_manifest: o.Pin
    restore_closure: o.Pin
    memory: list[MemoryProof] = Field(min_length=2, max_length=2)
    memory_closure: o.Pin
    helpers: dict[str, o.Pin]
    output: Path

    @model_validator(mode="after")
    def safe(self) -> Config:
        if set(self.helpers) != HELPERS or {p.host for p in self.memory} != {
            "morrobay",
            "capitola",
        }:
            raise ValueError(
                "complete exact helpers and both memory observers required"
            )
        if not self.output.is_absolute() or ".." in self.output.parts:
            raise ValueError("fresh absolute evidence output required")
        if any(
            pin.path == self.output or self.output in pin.path.parents
            for pin in self.inputs()
        ):
            raise ValueError("output must not own original evidence")
        return self

    def inputs(self) -> list[o.Pin]:
        return [
            self.producer,
            self.original_wait,
            self.canonical_wait,
            self.outer_wait,
            self.outer_binding,
            self.original_outer_current_closure,
            self.current_closure,
            self.current_closure_wait,
            self.whole_copy,
            self.oracle,
            self.oracle_freeze,
            self.oracle_wait,
            self.original_manifest,
            self.restore_closure,
            self.memory_closure,
            *(
                p
                for proof in self.memory
                for p in (
                    proof.receipt,
                    proof.original_wait,
                    proof.original_wait_configuration,
                    proof.stop,
                    proof.configuration,
                    *proof.helper_copies.values(),
                )
            ),
            *self.helpers.values(),
        ]


class Proof(c.NativeProof):
    event_count: int
    directed_init_arcs: int
    initialized_vertices: int
    terminal_reached: int
    terminal_levels: int
    worker_successes: dict[int, int]


class Audit(o.Model):
    outcome: Literal[
        "checking", "passed_qualified_current_twohost_original_scale24_BFS", "error"
    ] = "checking"
    observed_utc: str
    configuration: o.Pin
    config: Config
    pins_before: list[o.Pin] = Field(default_factory=list)
    pins_after: list[o.Pin] = Field(default_factory=list)
    native: Proof | None = None
    execution_and_current_process_closure_passed: bool = False
    full_original_mathematical_physical_certificate_passed: bool = False
    bounded_natural_memory_observer_closure_passed: bool = False
    own_metadata_identity_closure_passed: bool = False
    original_producer_physical_flag_preserved: Literal[False] = False
    historical_X1_X2_initiating_cause_identified: Literal[False] = False
    OS32_PSS_unique_host_memory_native_pool_fit_or_timing_claim: Literal[False] = False
    service_and_firewall_lifecycle_qualified_here: Literal[False] = False
    errors: list[str] = Field(default_factory=list)
    scope: str = "Conjunction of closed current native execution/process provenance and independent all-original mathematical/physical certificate. Original producer/oracle scopes stay unchanged. Memory is bounded per-process observation closure only; no history, speed, OS memory or final store/firewall lifecycle claim."
