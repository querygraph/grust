"""Sem-format metadata reports of the separately named client Arrow bridge."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import JsonValue, TypeAdapter

import f2a_campaign as campaign
import f2a_campaign_launch as launcher
import f2a_models as models
import fourphase_qualification as qualification

BASE = Path("/Volumes/Apo/graph-tests/results/sem-completion-20261003")
PRODUCER = BASE / "F2-fourphase-main03"
JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class Benchmark(models.Record):
    algorithm: Literal["wcc"] = "wcc"
    dataset: str
    size_class: Literal["M"] = "M"
    engine: Literal["Nutmeg/native Arrow bridge"] = "Nutmeg/native Arrow bridge"
    params: dict[str, JsonValue]
    graph: dict[str, JsonValue]
    warmup: dict[str, JsonValue]
    monitor: dict[str, JsonValue]
    runs: list[JsonValue]
    stats: dict[str, JsonValue]
    series: dict[str, JsonValue]
    raw_series: dict[str, JsonValue]
    environment: dict[str, JsonValue]


class Receipt(models.Record):
    observed_utc: str
    outcome: Literal["reported_physically_qualified_bridge_execution"]
    producer: models.FilePin
    waited_producer: models.FilePin
    source: models.FilePin
    files: list[models.FilePin]
    series: int
    completed_full_writes: int
    full_physical_qualification: Literal["eight_main_outputs_passed"]
    oracle_receipts: list[models.FilePin]
    tiny_oracle_receipt: models.FilePin
    retention_receipt: models.FilePin
    scope: str


def pin(path: Path) -> models.FilePin:
    campaign.require(
        path.is_file() and not path.is_symlink(), "regular metadata required"
    )
    data = path.read_bytes()
    campaign.require(len(data) < 1_000_000, "small metadata only")
    return models.FilePin(
        path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()
    )


def value(record: models.Record) -> JsonValue:
    return JSON.validate_json(record.model_dump_json())


def summary(seconds: float) -> JsonValue:
    return {
        "n": 1,
        "mean": seconds,
        "median": seconds,
        "min": seconds,
        "max": seconds,
        "std": None,
    }


def generate(output: Path) -> None:
    campaign.require(
        output.is_absolute() and not output.exists(), "fresh report root required"
    )
    owner_pin, exit_pin = (
        pin(PRODUCER / "receipt.json"),
        pin(PRODUCER / "launch-receipt.json"),
    )
    owner = campaign.Receipt.model_validate_json(owner_pin.path.read_bytes())
    closed = launcher.Receipt.model_validate_json(exit_pin.path.read_bytes())
    admitted = campaign.Config.model_validate_json(
        owner.configuration.path.read_bytes()
    )
    campaign.require(
        owner.outcome == "completed_unvalidated_campaign"
        and not owner.errors
        and not owner.skipped_plans
        and owner.all_owned_groups_absent
        and owner.locks_released
        and owner.before == owner.after == admitted.pins()
        and owner.source_before == owner.source_after,
        "producer closure differs",
    )
    campaign.require(
        closed.outcome == "completed_unvalidated_waited_campaign"
        and closed.returncode == 0
        and closed.wait_completed
        and closed.owner_group_absent
        and not closed.forced_cleanup
        and not closed.errors
        and closed.producer_receipt == owner_pin
        and closed.configuration == owner.configuration,
        "waited producer differs",
    )
    campaign.require(len(owner.series) == 4, "four bridge conditions required")
    output.mkdir(parents=True, exist_ok=False)
    files: list[models.FilePin] = []
    inputs = [owner_pin, exit_pin, owner.configuration]
    oracle_pins: list[models.FilePin] = []
    output_identities: dict[Path, qualification.Identity] = {}
    retention_pin = pin(PRODUCER / "raw-archive-verification01.json")
    retention = qualification.Retention.model_validate_json(
        retention_pin.path.read_bytes()
    )
    tiny_owner = campaign.Receipt.model_validate_json(
        (BASE / "F2-fourphase-smoke03/receipt.json").read_bytes()
    )
    tiny_exit = launcher.Receipt.model_validate_json(
        (BASE / "F2-fourphase-smoke03/launch-receipt.json").read_bytes()
    )
    campaign.require(
        tiny_owner.outcome == "completed_unvalidated_campaign"
        and not tiny_owner.errors
        and tiny_owner.all_owned_groups_absent
        and tiny_owner.locks_released
        and tiny_exit.outcome == "completed_unvalidated_waited_campaign"
        and tiny_exit.returncode == 0
        and tiny_exit.wait_completed
        and tiny_exit.owner_group_absent
        and not tiny_exit.errors
        and tiny_exit.producer_receipt
        == pin(BASE / "F2-fourphase-smoke03/receipt.json")
        and len(tiny_owner.series) == 1,
        "tiny closed producer differs",
    )
    tiny_series = tiny_owner.series[0]
    if tiny_series.worker_receipt is None:
        raise ValueError("tiny worker receipt absent")
    tiny_worker = models.Receipt.model_validate_json(
        tiny_series.worker_receipt.path.read_bytes()
    )
    tiny_oracle, tiny_pin = qualification.qualified(
        BASE / "F2-fourphase-smoke03-oracle01/receipt.json",
        tiny_worker.configuration,
        [
            tiny_series.worker_receipt,
            tiny_series.plan,
            tiny_owner.configuration,
            pin(BASE / "F2-fourphase-smoke03/receipt.json"),
            pin(BASE / "F2-fourphase-smoke03/launch-receipt.json"),
        ],
    )
    campaign.require(
        tiny_oracle.config.expected_rows == 4 and len(tiny_oracle.outputs) == 3,
        "three tiny outputs required",
    )
    inputs.extend([retention_pin, tiny_pin])
    count = 0
    for series in owner.series:
        campaign.require(
            series.worker_receipt is not None and series.launch_to_wait is not None,
            "worker/wall proof absent",
        )
        if series.worker_receipt is None or series.launch_to_wait is None:
            raise ValueError("worker/wall proof absent")
        campaign.require(
            pin(series.worker_receipt.path) == series.worker_receipt
            and pin(series.plan.path) == series.plan,
            "worker/plan bytes differ",
        )
        worker = models.Receipt.model_validate_json(
            series.worker_receipt.path.read_bytes()
        )
        plan = worker.configuration
        campaign.require(
            worker.outcome == "completed_unvalidated"
            and not worker.errors
            and worker.pipeline_completed
            and worker.pipeline is not None
            and worker.pipeline_seconds is not None
            and worker.projection_reused is True
            and series.wait_completed
            and series.returncode == 0
            and series.driver_group_absent
            and series.server_group_absent
            and not series.forced_cleanup,
            "worker execution differs",
        )
        spans = {p.name: p.span.seconds for p in worker.phases}
        campaign.require(
            len(spans) == 4 and all(p.completed for p in worker.phases),
            "four observed bridge phases required",
        )
        if worker.pipeline_seconds is None:
            raise ValueError("continuous pipeline absent")
        stage = worker.stage_receipt
        campaign.require(isinstance(stage, dict), "stage metadata absent")
        if not isinstance(stage, dict):
            raise TypeError("stage metadata absent")
        phases: dict[str, JsonValue] = {
            "read_parquet_s": spans["read_parquet"],
            "csr_and_graph_s": spans["csr_and_graph"],
            "algorithm_s": spans["algorithm_materialize"],
            "write_parquet_s": spans["write_parquet"],
            "wall_in_process_s": worker.pipeline_seconds,
        }
        wall = series.launch_to_wait.seconds
        oracle_path = (
            BASE
            / f"F2-fourphase-main03-oracle-{plan.dataset}-int64-c{plan.calls}-01/receipt.json"
        )
        oracle, oracle_pin = qualification.qualified(
            oracle_path,
            plan,
            [
                owner_pin,
                exit_pin,
                owner.configuration,
                series.worker_receipt,
                series.plan,
            ],
        )
        campaign.require(
            oracle.config.vertices in admitted.expected_inputs,
            "oracle original input does not match admitted input pin",
        )
        campaign.require(
            dt.datetime.fromisoformat(oracle.started_utc)
            >= dt.datetime.fromisoformat(closed.finished_utc or ""),
            "oracle did not follow closed campaign",
        )
        oracle_pins.append(oracle_pin)
        inputs.extend([oracle_pin, oracle.configuration])
        for declared in oracle.config.outputs:
            for name, identity in declared.files.items():
                output_identities[declared.directory / name] = identity
        report = Benchmark(
            dataset=plan.dataset,
            params={
                "execution_profile": worker.execution_profile,
                "ids": plan.ids,
                "calls": plan.calls,
                "order": "asStaged",
                "workers": 16,
                "concurrency": 16,
                "chunk_rows": plan.chunk_rows,
                "runs": 1,
            },
            graph={
                "vertices_reported_by_stage": stage.get("nodeCount"),
                "edges_reported_by_stage": stage.get("edgeCount"),
                "vertices_path": str(plan.vertices),
                "edges_path": str(plan.edges),
            },
            warmup={"count": 0, "performed": False, "cache_flush": False},
            monitor={
                "rss_interval_s": 0.5,
                "samples": series.rss_samples,
                "observed_worker_peak_rss_kib": series.observed_worker_peak_rss_kib,
                "observed_server_peak_rss_kib": series.observed_server_peak_rss_kib,
                "scope": "Direct PID sampled RSS; not OS peak or limit.",
            },
            runs=[
                {
                    "index": 0,
                    "wall_time_s": wall,
                    "returncode": series.returncode,
                    "worker": {
                        "algorithm": "wcc",
                        "phases_s": phases,
                        "calls": plan.calls,
                        "completed_full_writes": len(worker.outputs),
                        "full_physical_qualification": "passed_full_physical_wcc",
                        "oracle_receipt": value(oracle_pin),
                    },
                }
            ],
            stats={
                "parent_launch_to_wait_s": summary(wall),
                "continuous_pipeline_s": summary(worker.pipeline_seconds),
            },
            series={
                "parent_launch_to_wait_s": [wall],
                "continuous_pipeline_s": [worker.pipeline_seconds],
            },
            raw_series={
                "worker": value(worker),
                "parent_series": value(series),
                "full_oracle_receipt": JSON.validate_json(oracle_pin.path.read_bytes()),
            },
            environment={
                "extension_source": plan.extension_source_commit,
                "native_runtime_source": plan.native_runtime_commit,
                "python": worker.python_version,
                "pyspark_version": worker.pyspark_version,
                "binary": value(admitted.binary),
                "wheel": value(admitted.wheel),
                "controlled_environment": JSON.validate_python(worker.environment),
                "scope": "Separate bounded client-Arrow/checkpoint bridge on a shared native host; n1, no dispersion inference. Read is client Parquet-to-Arrow. CSR/graph includes bounded inline IPC encoding, eager unsorted checkpoint jobs, balanced remote-reference unions, asStaged and projectionStats. Algorithm includes all WCC calls plus full Arrow result transport. Write is client Parquet for all materialized results. Continuous total includes phase boundaries/bookkeeping; parent wall also includes imports/setup/status/cleanup. No old native-Parquet baseline, native CSR-only/kernel-only or Sem resource/work parity claim. All full outputs passed separate original-domain and partition oracles after engine closure; oracle time is outside every reported clock.",
            },
        )
        directory = output / f"{plan.dataset}-{plan.ids}-calls{plan.calls}"
        directory.mkdir()
        path = directory / "benchmark.json"
        path.write_text(report.model_dump_json(indent=2) + "\n")
        files.append(pin(path))
        count += len(worker.outputs)
        inputs.extend([series.worker_receipt, series.plan])
    campaign.require(
        count == 8 and all(pin(p.path) == p for p in inputs),
        "final metadata/series closure differs",
    )
    campaign.require(
        len(retention.files) == len(output_identities) == 8
        and len({f.original for f in retention.files}) == 8
        and retention.total_bytes == sum(f.bytes for f in retention.files),
        "retained full output count/total differs",
    )
    for retained in retention.files:
        expected_identity = output_identities.get(retained.original)
        relative = retained.original.relative_to(
            Path(
                "/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/F2-fourphase-main03"
            )
        )
        campaign.require(
            expected_identity is not None
            and retained.bytes == expected_identity.bytes
            and retained.sha256 == expected_identity.sha256
            and retained.archive == PRODUCER / "raw" / relative,
            "root copy verification does not bind oracle output identity",
        )
    receipt = Receipt(
        observed_utc=dt.datetime.now(dt.UTC).isoformat(),
        outcome="reported_physically_qualified_bridge_execution",
        producer=owner_pin,
        waited_producer=exit_pin,
        source=pin(Path(__file__)),
        files=files,
        series=4,
        completed_full_writes=8,
        full_physical_qualification="eight_main_outputs_passed",
        oracle_receipts=oracle_pins,
        tiny_oracle_receipt=tiny_pin,
        retention_receipt=retention_pin,
        scope="Metadata-only truthful four-phase bridge observations; no data/oracle/process/engine action. Worker continuous timer and parent wait timer remain distinct. Root ran the full original-domain WCC oracles and retained all eight main Parquets on Apo with matching SHA; this writer only binds their closed metadata. Earlier bridge failures remain retained.",
    )
    (output / "receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n")
    lines = [
        "# Observed client Arrow bridge phases",
        "",
        "All eight main and three separate tiny outputs passed the closed full physical WCC oracles. The original vertex domain and partitions match the retained references after minimum-original-member normalization. These are separate checks outside every timer; raw labels are not required to be canonical minima. All eight main Parquets were retained on Apo with matching full SHA.",
        "",
        "| Dataset | Calls | Read | CSR/graph | Algorithm + Arrow | Write | Pipeline | Parent wait |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for series in owner.series:
        if series.worker_receipt is None or series.launch_to_wait is None:
            raise ValueError("series proof absent")
        worker = models.Receipt.model_validate_json(
            series.worker_receipt.path.read_bytes()
        )
        spans = {p.name: p.span.seconds for p in worker.phases}
        lines.append(
            f"| {worker.configuration.dataset} | {worker.configuration.calls} | {spans['read_parquet']:.3f} | {spans['csr_and_graph']:.3f} | {spans['algorithm_materialize']:.3f} | {spans['write_parquet']:.3f} | {worker.pipeline_seconds:.3f} | {series.launch_to_wait.seconds:.3f} |"
        )
    lines.extend(
        [
            "",
            "Seconds shown solely to describe each observed phase boundary on this shared host; these are not dedicated-host benchmark results. Each condition has n=1 and standard deviation is null. CSR includes checkpoint/serialization/staging/projection work, algorithm includes full client transport, and three-call phases cover all three calls. Software pools are not an OS memory cap. This separately named profile is not compared with the prior native-Parquet baseline.",
            "",
        ]
    )
    (output / "README.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    generate(parser.parse_args().output)


if __name__ == "__main__":
    main()
