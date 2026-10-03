"""Native Nutmeg extension metadata and a small Spark Connect client.

The host reads manifest() before importing any native FFI object.
"""
TYPE_URL = "type.googleapis.com/nutmeg.v1.NutmegApi"


class Extension:
    def manifest(self):
        import os

        return {
            "name": "nutmeg",
            "version": "0.1.0",
            "api_version": 1,
            "datafusion_version": "55.1.0",
            "arrow_version": "59.3.0",
            "placement": "driver",
            "memory_bytes": int(os.environ.get("SAIL_NUTMEG_MEMORY_BYTES", "268435456")),
            "relation_types": [{
                "type_url": TYPE_URL,
                "accepts_bare": True,
                "min_inputs": 0,
                "max_inputs": 2,
            }],
        }

    def bind(self, session_id):
        raise RuntimeError("Nutmeg requires Sail host memory admission; use bind_with_resources")

    def bind_with_resources(self, session_id, memory_bytes, host_resource):
        from ._native import BoundExtension
        # Each bind allocates fresh state; a recycled session ID inherits nothing.
        # The quota is already admitted by Sail; retain its ABI lease through the
        # session, pinned graph snapshots, in-flight kernels and Arrow outputs.
        return BoundExtension(memory_bytes, host_resource)


def extension():
    return Extension()


def __getattr__(name):
    if name == "Nutmeg":
        from .client import Nutmeg
        return Nutmeg
    raise AttributeError(name)
