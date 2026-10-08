"""Optional sampled process RSS; profiling runs are separate from paired timings."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryProfile:
    scope: str
    peak_sampled_rss_bytes: int | None
    samples: int
    interval_ms: int


class Sampler:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stop = threading.Event()
        self.peak: int | None = None
        self.samples = 0
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self) -> None:
        while not self.stop.is_set():
            result = subprocess.run(
                ["ps", "-p", str(self.pid), "-o", "rss="],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                value = int(result.stdout.strip()) * 1024
                self.peak = max(self.peak or 0, value)
                self.samples += 1
            self.stop.wait(0.2)

    def finish(self) -> MemoryProfile:
        self.stop.set()
        self.thread.join(timeout=3)
        return MemoryProfile(
            "Sail server PID; sampled OS resident memory including native allocations; excludes Python harness, preparation, and browser; not an OS memory limit",
            self.peak,
            self.samples,
            200,
        )
