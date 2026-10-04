"""Durable waited campaign launcher; root detaches this process with Popen/nohup."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field

import f2a_campaign as campaign
import f2a_models as worker


class Receipt(worker.Record):
    outcome: Literal["running", "completed_unvalidated_waited_campaign", "error"] = (
        "running"
    )
    started_utc: str
    finished_utc: str | None = None
    launcher_pid: int
    configuration: worker.FilePin
    argv: list[str]
    owner_pid: int | None = None
    owner_pgid: int | None = None
    returncode: int | None = None
    wait_completed: bool = False
    owner_group_absent: bool = False
    forced_cleanup: bool = False
    producer_receipt: worker.FilePin | None = None
    errors: list[str] = Field(default_factory=list)


def run(path: Path) -> int:
    configuration = campaign.pin(path)
    config = campaign.Config.model_validate_json(path.read_bytes())
    config.root.mkdir(parents=True, exist_ok=True)
    destination = config.root / "launch-receipt.json"
    campaign.require(
        not destination.exists() and not (config.root / "receipt.json").exists(),
        "fresh launch namespace required",
    )
    bootstrap = 'import runpy,sys;r=sys.argv[1];sys.path.insert(0,r);sys.argv=[r+"/f2a_campaign.py"]+sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")'
    argv = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        bootstrap,
        str(config.worker.parent),
        "--config",
        str(path),
    ]
    receipt = Receipt(
        started_utc=campaign.utc(),
        launcher_pid=os.getpid(),
        configuration=configuration,
        argv=argv,
    )
    campaign.save(destination, receipt)
    process: subprocess.Popen[bytes] | None = None
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, campaign.interrupted)
        with (config.root / "owner.log").open("xb") as log:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            receipt.owner_pid = receipt.owner_pgid = process.pid
            campaign.require(
                os.getpgid(process.pid) == process.pid,
                "fresh owner process group required",
            )
            campaign.save(destination, receipt)
            receipt.returncode = process.wait(timeout=config.timeout_seconds + 360)
            receipt.wait_completed = True
        receipt.owner_group_absent = not campaign.members(process.pid)
        producer = campaign.Receipt.model_validate_json(
            (config.root / "receipt.json").read_bytes()
        )
        campaign.require(
            receipt.returncode == 0
            and receipt.owner_group_absent
            and producer.owner_pid == process.pid
            and producer.configuration == configuration
            and producer.outcome == "completed_unvalidated_campaign"
            and producer.finished_utc is not None
            and not producer.errors
            and producer.locks_released
            and producer.all_owned_groups_absent
            and producer.before == producer.after == config.pins()
            and producer.source_before == producer.source_after
            and len(producer.series) == len(config.plans)
            and not producer.skipped_plans,
            "owner did not return closed unvalidated execution",
        )
        campaign.require(
            all(
                s.outcome == "completed_unvalidated"
                and s.wait_completed
                and s.returncode == 0
                and s.driver_group_absent
                and s.server_group_absent
                and not s.forced_cleanup
                and s.worker_receipt is not None
                for s in producer.series
            ),
            "one series failed ownership/exit closure",
        )
        campaign.require(
            campaign.pin(path) == configuration
            and campaign.source(config) == producer.source_after,
            "final launcher configuration/source closure failed",
        )
        campaign.require(
            [campaign.pin(p.path) for p in config.pins()] == config.pins(),
            "final launcher immutable pin closure failed",
        )
        receipt.producer_receipt = campaign.pin(config.root / "receipt.json")
        receipt.outcome = "completed_unvalidated_waited_campaign"
    except BaseException as error:  # noqa: BLE001 - preserve all waited launcher/owned cancellation failures.
        receipt.outcome = "error"
        receipt.errors.append(f"{type(error).__name__}: {error}")
        if process is not None:
            try:
                if process.poll() is None:
                    campaign.require(
                        os.getpgid(process.pid) == process.pid,
                        "live owner ownership cannot be established",
                    )
                    receipt.forced_cleanup = True
                    process.terminate()
                    process.wait(timeout=330)
                receipt.returncode = process.wait(timeout=5)
                receipt.wait_completed = True
                receipt.owner_group_absent = not campaign.members(process.pid)
                campaign.require(
                    receipt.owner_group_absent,
                    "exited owner group remains live; no historical signals permitted",
                )
            except Exception as cleanup:  # noqa: BLE001 - retain failure and locks; signal only a live direct child.
                receipt.errors.append(
                    f"owned cleanup {type(cleanup).__name__}: {cleanup}"
                )
    receipt.finished_utc = campaign.utc()
    campaign.save(destination, receipt)
    print(receipt.outcome + " " + str(destination), flush=True)
    return 0 if receipt.outcome == "completed_unvalidated_waited_campaign" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return run(parser.parse_args().config.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
