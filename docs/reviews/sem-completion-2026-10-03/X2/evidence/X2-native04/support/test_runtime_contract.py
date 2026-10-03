"""Offline boundary checks against the actual native9f startup contract."""

from pathlib import Path
from urllib.parse import unquote, urlparse

import native_probe as n
import probe_models as m
import pytest
from pydantic import BaseModel, ConfigDict


class OriginalReceipt(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    errors: list[str]


def test_existing_directory_and_file_uri_before_session(tmp_path: Path) -> None:
    output = tmp_path.resolve() / "owned-output"
    output.mkdir()
    n.prepare_runtime_directories(output)
    plan_path = Path(__file__).parents[1] / "queue01/x2-reference-p16-01.json"
    plan = m.Plan.model_validate_json(plan_path.read_bytes()).model_copy(
        update={"output": output}
    )
    env = n.environment(plan)
    parsed = urlparse(env["SAIL_GRAPH_UTILS_ROOT"])
    assert parsed.scheme == "file"
    assert Path(unquote(parsed.path)) == output / "staging"
    assert Path(unquote(parsed.path)).is_dir()
    assert env["SAIL_EXPERIMENTAL_EXTENSIONS"] == "1"


def test_missing_owned_parent_is_not_silently_created(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="canonical fresh owned"):
        n.prepare_runtime_directories(tmp_path.resolve() / "missing-output")


def test_actual_rust_requires_uri_and_existing_local_directory() -> None:
    source = n.GRAPH_SOURCE / "crates/sail-session/src/extensions"
    assert 'as_deref() != Ok("1")' in (source / "mod.rs").read_text()
    assert "Url::parse(root)" in (source / "graph_utils/storage.rs").read_text()
    local = (source / "graph_utils/local.rs").read_text()
    assert "to_file_path()" in local and "path.canonicalize()" in local
    assert "precreate the trusted graph staging directory before starting Sail" in local


def test_declared_slots_admit_retained_reference_write_region() -> None:
    original = Path(
        "/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x2-native03/x2-reference-p16-01/receipt.json"
    )
    receipt = OriginalReceipt.model_validate_json(original.read_bytes())
    assert any(
        "task region requires 17 worker task slots" in error
        and "configured maximum is 16" in error
        for error in receipt.errors
    )
    plan = m.Plan.model_validate_json(
        (Path(__file__).parents[1] / "queue01/x2-reference-p16-01.json").read_bytes()
    )
    assert plan.worker_count * plan.worker_task_slots == 18
    assert plan.worker_task_slots < plan.partitions
