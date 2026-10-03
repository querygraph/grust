"""Argentea's explicit worker role, requiring the new Sail worker runtime.

Older Sail builds reject this wheel's worker manifest during discovery. There
is no driver fallback: distributed state must use the scoped worker contract.
"""
TYPE_URL = "type.googleapis.com/nutmeg.v1.ArgenteaApi"
SSSP_TYPE_URL = "type.googleapis.com/nutmeg.v5.ArgenteaSsspApi"
WCC_TYPE_URL = "type.googleapis.com/nutmeg.v4.ArgenteaWccApi"
BFS_TYPE_URL = "type.googleapis.com/nutmeg.v3.ArgenteaBfsApi"
DELTA_TYPE_URL = "type.googleapis.com/nutmeg.v2.ArgenteaDeltaApi"


class Extension:
    def manifest(self):
        import os

        return {
            "name": "argentea",
            "version": "0.1.0",
            "api_version": 1,
            "datafusion_version": "55.1.0",
            "arrow_version": "59.3.0",
            "placement": "worker",
            "memory_bytes": int(os.environ.get("SAIL_ARGENTEA_MEMORY_BYTES", "268435456")),
            "relation_types": [{
                "type_url": TYPE_URL,
                "accepts_bare": False,
                "min_inputs": 1,
                "max_inputs": 2,
            }, {
                "type_url": SSSP_TYPE_URL,
                "accepts_bare": False,
                "min_inputs": 1,
                "max_inputs": 2,
            }, {
                "type_url": WCC_TYPE_URL,
                "accepts_bare": False,
                "min_inputs": 1,
                "max_inputs": 2,
            }, {
                "type_url": BFS_TYPE_URL,
                "accepts_bare": False,
                "min_inputs": 1,
                "max_inputs": 2,
            }, {
                "type_url": DELTA_TYPE_URL,
                "accepts_bare": False,
                "min_inputs": 1,
                "max_inputs": 2,
            }],
        }

    def plan_worker_relation(self, type_url, payload, inputs):
        from ._native import plan_worker_relation
        return plan_worker_relation(type_url, payload, inputs)

    def bind_with_resources(self, incarnation, memory_bytes, host_resource):
        from ._native import BoundArgentea
        return BoundArgentea(incarnation, memory_bytes, host_resource)


def extension():
    return Extension()
