"""Offline draft-contract checks; no graph provider, browser or MCP is run."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent


def reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON number: {value}")


def load(path: Path) -> Any:
    return json.loads(path.read_text(), parse_constant=reject_constant)


def finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite number")
    if isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def metadata_checks(value: dict[str, Any], kind: str) -> None:
    """Selected free metadata checks; not runtime admission or graph validation."""
    finite(value)
    if kind == "request":
        command = value["command"]
        params = command["params"]
        if (
            params.get("domain") == "selection"
            and value["context"]["selection"] is None
        ):
            raise ValueError("selection domain requires a membership handle")
        if command["op"] == "graph.degree_filter":
            maximum = params["maximum"]
            if maximum is not None and int(maximum) < int(params["minimum"]):
                raise ValueError("inverted degree interval")
        pose = params.get("pose", params.get("camera"))
        if pose is not None and pose["mode"] == "3d":
            if pose["near"] >= pose["far"]:
                raise ValueError("inverted camera clip interval")
            if pose["eye"] == pose["target"] or all(x == 0 for x in pose["up"]):
                raise ValueError("degenerate camera basis")
    elif kind == "manifest":
        counts = value["counts"]
        budget = value["applied_budget"]
        if int(counts["points"]) > budget["max_points"]:
            raise ValueError("manifest exceeds its point cap")
        if int(counts["links"]) > budget["max_links"]:
            raise ValueError("manifest exceeds its link cap")
        wire_bytes = sum(
            int(value[key]["encoded_bytes"]) for key in ("points", "links")
        )
        if wire_bytes > int(budget["max_wire_bytes"]):
            raise ValueError("manifest exceeds its wire cap")
        if int(value["decoded_bytes"]) > int(budget["max_decoded_bytes"]):
            raise ValueError("manifest exceeds its decode cap")


def main() -> None:
    schemas = {
        path.stem.removesuffix(".schema"): load(path)
        for path in ROOT.glob("*.schema.json")
    }
    resources = [
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    ]
    registry = Registry().with_resources(resources)
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    validators = {
        name: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for name, schema in schemas.items()
    }

    def validate(value: dict[str, Any], kind: str) -> None:
        validators[kind].validate(value)
        metadata_checks(value, kind)

    examples: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "examples").glob("*.json")):
        value = load(path)
        kind = path.name.split(".")[-2]
        validate(value, kind)
        examples[path.name] = value
    request = examples["14-graph-follow.request.json"]
    accepted = examples["accepted.response.json"]
    camera = examples["05-camera-rotate.request.json"]
    degree = examples["18-graph-degree_filter.request.json"]
    manifest = examples["overview.manifest.json"]
    cases: list[tuple[str, str, dict[str, Any]]] = []

    def bad(
        label: str,
        kind: str,
        source: dict[str, Any],
        edit: Callable[[dict[str, Any]], None],
    ) -> None:
        value = copy.deepcopy(source)
        edit(value)
        cases.append((label, kind, value))

    bad(
        "point ceiling",
        "request",
        request,
        lambda x: x["budget"].update(max_points=1000001),
    )
    bad(
        "numeric durable ID",
        "request",
        request,
        lambda x: x["command"]["params"]["seeds"]["ids"][0].update(id=9007199254740993),
    )
    bad(
        "aggregate is not vertex seed",
        "request",
        request,
        lambda x: x["command"]["params"]["seeds"]["ids"][0].update(kind="aggregate"),
    )
    bad(
        "unknown operation",
        "request",
        request,
        lambda x: x["command"].update(op="graph.unspecified"),
    )
    bad("wrong protocol", "request", request, lambda x: x.update(cosmolang="2.0"))
    bad(
        "missing state revision", "request", request, lambda x: x.pop("expect_revision")
    )
    bad(
        "claimed authority",
        "request",
        request,
        lambda x: x["context"].update(authorization="admin"),
    )
    bad("job missing", "response", accepted, lambda x: x.pop("job"))
    bad(
        "camera clip interval",
        "request",
        camera,
        lambda x: x["command"]["params"]["pose"].update(near=2000),
    )
    bad(
        "nonfinite camera",
        "request",
        camera,
        lambda x: x["command"]["params"]["pose"]["eye"].__setitem__(0, math.inf),
    )
    bad(
        "degree interval",
        "request",
        degree,
        lambda x: x["command"]["params"].update(maximum="1"),
    )
    bad(
        "point-count admission",
        "manifest",
        manifest,
        lambda x: x["counts"].update(points="1000001"),
    )
    bad(
        "byte admission",
        "manifest",
        manifest,
        lambda x: x["points"].update(encoded_bytes="999999999"),
    )
    nearest = examples["15-graph-nearest.request.json"]
    bad(
        "spatial ANN unsupported",
        "request",
        nearest,
        lambda x: x["command"]["params"].update(method="ann"),
    )
    layout = examples["20-layout-prepare.request.json"]
    bad(
        "selection handle absent",
        "request",
        layout,
        lambda x: x["context"].update(selection=None),
    )
    zoom = examples["06-camera-zoom.request.json"]
    bad(
        "flat rotation unsupported",
        "request",
        zoom,
        lambda x: x["command"].update(op="camera.rotate"),
    )
    for label, kind, value in cases:
        try:
            validate(value, kind)
        except (ValueError, ValidationError):
            pass
        else:
            raise AssertionError(f"invalid example accepted: {label}")
    print(
        f"C0 PASSED: {len(schemas)} schemas; {len(examples)} examples; {len(cases)} rejection controls"
    )


if __name__ == "__main__":
    main()
