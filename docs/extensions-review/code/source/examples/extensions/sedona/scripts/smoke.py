"""Verify the installed wheel manifest and every native capsule without Sail."""

import ctypes
from importlib.metadata import entry_points

from sail_sedona import extension

manifest = extension.manifest()
assert manifest == {
    "name": "sedona",
    "version": "0.1.0",
    "api_version": 1,
    "datafusion_version": "55.1.0",
    "arrow_version": "59.3.0",
    "placement": "any",
    "relation_types": [],
}
entries = [e for e in entry_points(group="pysail.extensions") if e.name == "sedona"]
assert len(entries) == 1
assert entries[0].load().manifest() == manifest
bound = extension.bind("sedona-wheel-smoke")
functions = {f.name(): f for f in bound.scalar_udfs()}
assert len(functions) == 128
assert {"st_point", "st_geomfromwkt", "st_astext", "st_intersects", "st_distance"} <= functions.keys()
assert "st_geomfromtext" in functions["st_geomfromwkt"].aliases()
assert not {"st_asbinary", "st_geomfromwkb", "st_geogfromwkb", "st_setsrid", "st_srid"} & functions.keys()
is_valid = ctypes.pythonapi.PyCapsule_IsValid
is_valid.argtypes = [ctypes.py_object, ctypes.c_char_p]
is_valid.restype = ctypes.c_int
assert all(is_valid(f.__datafusion_scalar_udf__(), b"datafusion_scalar_udf") for f in functions.values())
print({"manifest": manifest, "scalars": len(functions), "capsules": "valid"})
