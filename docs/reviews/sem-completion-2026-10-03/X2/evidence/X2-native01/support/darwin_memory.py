"""macOS per-PID footprint via the SDK rusage_info_v0 contract; no PSS/cgroup."""

import ctypes
import os
import sys

from pydantic import BaseModel, ConfigDict


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resident_size_bytes: int | None = None
    physical_footprint_bytes: int | None = None
    process_start_abstime: int | None = None
    error: str | None = None


class RusageV0(ctypes.Structure):
    _fields_ = [
        ("uuid", ctypes.c_uint8 * 16),
        ("user_time", ctypes.c_uint64),
        ("system_time", ctypes.c_uint64),
        ("pkg_idle_wkups", ctypes.c_uint64),
        ("interrupt_wkups", ctypes.c_uint64),
        ("pageins", ctypes.c_uint64),
        ("wired_size", ctypes.c_uint64),
        ("resident_size", ctypes.c_uint64),
        ("phys_footprint", ctypes.c_uint64),
        ("proc_start_abstime", ctypes.c_uint64),
        ("proc_exit_abstime", ctypes.c_uint64),
    ]


def observe(pid: int) -> Observation:
    if sys.platform != "darwin":
        return Observation(error="macOS proc_pid_rusage unavailable")
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pid_rusage
        function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        function.restype = ctypes.c_int
        value = RusageV0()
        if ctypes.sizeof(value) != 96:
            return Observation(error="rusage_info_v0 ABI size differs")
        if function(pid, 0, ctypes.byref(value)) != 0:
            return Observation(
                error=f"proc_pid_rusage errno={ctypes.get_errno()}: {os.strerror(ctypes.get_errno())}"
            )
        return Observation(
            resident_size_bytes=int(value.resident_size),
            physical_footprint_bytes=int(value.phys_footprint),
            process_start_abstime=int(value.proc_start_abstime),
        )
    except OSError as error:
        return Observation(error=repr(error))
